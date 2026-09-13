"""Model -> generated ``Behavior`` subclass source, and the safe write path.

Spec: ``docs/vs2-behaviors-proposal.md``, ``## The block editor`` and ``###
Round-trip: one embedded blob and one one-way door``, applied at
Behavior-file granularity (one generated ``.py`` per custom Behavior, per
the proposal's own file tree: ``code/behaviors/chasing.py GENERATED from
blocks. One file per custom behavior.``).

**A whole class, not a mixin.** T16's event-sheet generator emits a mixin
because a scene already has a hand-written base to combine with. A
``Behavior`` has no such counterpart -- every hand-written entry in
``apps/micropython/vs2/behaviors.py`` (``Projectile`` included) *is* the
whole class, subclassing ``Behavior`` directly. So this generator emits a
complete ``Behavior`` subclass: parameter declarations, ``state = (...)``,
``attached()`` composing the declared Actions, and ``step()``/``step_one()``
(chosen by ``subject_kind`` -- see :mod:`model`) carrying the two-zone
tick body.

**The pool-shaped loop is copied verbatim from the real ``Projectile``,
deliberately.** ``apps/micropython/vs2/behaviors.py``'s ``Projectile.step()``
walks ``sprites._live`` with a downward indexed ``while`` specifically so a
``despawn()`` mid-loop (which swaps the freed slot's sprite in from the
tail -- see that class's own comments) never skips or double-visits a
sprite. Inventing a different loop shape here -- even one that "looks"
equivalent -- would risk exactly the despawn-safety bug the real class's
comments exist to prevent, for a generator whose whole job is producing
code indistinguishable in *behavior* from what a careful author would
write by hand. So :func:`_render_step_pool` emits that exact shape,
statement for statement, and only the per-sprite body inside it varies by
model.

**Why every rendered expression is a plain string, not a value type.**
Matching ``tools/vs2_event_gen/generator.py``'s own ``render_expr``: the
generator's whole job is producing readable Python text, so there is
nothing to gain from a richer intermediate representation the way a real
compiler would want one.
"""

from tools.vs2_scene_gen.blob import encode_blob

from . import checksum
from . import model as model_module

INDENT = "        "  # inside a method body: 4 (class) + 4 (def) spaces


class GeneratorError(ValueError):
    """Raised when a file exists on disk but is not safe to overwrite --
    see :func:`write_behavior_file`'s ``"hand_edited"`` status, the normal
    way this surfaces; this exception is for callers that want a hard
    failure instead."""


# ---------------------------------------------------------------------------
# Parameter declarations
# ---------------------------------------------------------------------------

#: model param "type" -> (vs2.params class name, constructor kwargs this
#: generator sets explicitly). Every ``vs2.params.Parameter`` subclass
#: accepts ``default`` positionally and ``label``/``unit`` by keyword;
#: ``Number``/``Angle`` additionally take ``min``/``max``/``step``;
#: ``Choice`` takes ``options`` instead. See
#: ``apps/micropython/vs2/params.py`` for the real signatures this mirrors.
_PARAM_CLASS_BY_TYPE = {
    "number": "Number", "angle": "Angle", "flag": "Flag", "choice": "Choice",
    "frames": "Frames", "sound": "Sound", "image": "Image", "pool": "PoolRef",
    "points": "Points", "callback": "Callback",
}

_NUMERIC_KWARGS = ("min", "max", "step")
_COMMON_KWARGS = ("label", "unit")


def _render_param_decl(param):
    """One ``name = ParamClass(default, ...)`` line's right-hand side,
    given one ``model.params[i]`` entry."""
    param_class = _PARAM_CLASS_BY_TYPE[param["type"]]
    args = [repr(param["default"])]
    if param["type"] == "choice":
        args.append("options=%r" % (tuple(param.get("options") or ()),))
    else:
        for key in _NUMERIC_KWARGS:
            if key in param:
                args.append("%s=%r" % (key, param[key]))
    for key in _COMMON_KWARGS:
        if key in param:
            args.append("%s=%r" % (key, param[key]))
    return param_class, "%s(%s)" % (param_class, ", ".join(args))


# ---------------------------------------------------------------------------
# Expression / condition rendering (pure: no side effects, always inline-able)
# ---------------------------------------------------------------------------

def render_expr(expr):
    kind = expr["kind"]
    if kind == "literal":
        return repr(expr["value"])
    if kind == "param":
        return "self.%s" % (expr["name"],)
    # kind == "state"
    return "sprite.%s" % (expr["name"],)


def render_condition(condition):
    # kind == "compare" (the only condition kind Phase 1 supports)
    return "%s %s %s" % (render_expr(condition["left"]), condition["op"],
                          render_expr(condition["right"]))


# ---------------------------------------------------------------------------
# Action declarations (attached()) and apply-to-all (step's uniform prologue)
# ---------------------------------------------------------------------------

def _render_action_call(action_decl):
    action_class = action_decl["action_class"]
    args = action_decl.get("args", {})
    parts = ["%s=%s" % (name, render_expr(args[name])) for name in sorted(args)]
    return "actions.%s(%s)" % (action_class, ", ".join(parts))


def _render_attached(model):
    lines = ["%sdef attached(self, subject):" % (INDENT[:4],)]
    actions = model.get("actions", [])
    if not actions:
        lines.append("%spass" % (INDENT,))
        return lines
    for action_decl in actions:
        lines.append("%sself.%s = self.action(%s)"
                      % (INDENT, action_decl["bind"], _render_action_call(action_decl)))
    return lines


def _render_apply_to_all(model, sprites_expr, indent):
    """The uniform prologue's lines, calling ``run(sprites)`` for a pool
    subject or ``run_one(sprite)`` for a lone-sprite subject -- see
    :mod:`model`'s docstring on why ``subject_kind`` decides this."""
    method = "run" if model["subject_kind"] == "pool" else "run_one"
    lines = []
    for bind in model.get("apply_to_all", []):
        lines.append("%sself.%s.%s(%s)" % (indent, bind, method, sprites_expr))
    return lines


# ---------------------------------------------------------------------------
# Per-sprite statement rendering (recursive; runs inside the per-sprite loop
# for a pool subject, or directly against ``sprite`` for a lone-sprite one).
# ---------------------------------------------------------------------------

def _render_per_sprite_list(nodes, indent, hit_var):
    lines = []
    for node in nodes:
        lines.extend(_render_per_sprite_node(node, indent, hit_var))
    if not lines:
        lines.append("%spass" % (indent,))
    return lines


def _render_per_sprite_node(node, indent, hit_var):
    kind = node["kind"]

    if kind == "accumulate":
        return ["%ssprite.%s += %s" % (indent, node["state"], render_expr(node["amount"]))]

    if kind == "despawn":
        return ["%ssprite.despawn()" % (indent,)]

    if kind == "despawn_hit":
        # Only reachable inside an "if_action" node's own then/else stack --
        # see model.py's PER_SPRITE_KINDS docstring and this function's
        # "if_action" branch below, which is the only place `hit_var` is
        # ever set to anything but None.
        if hit_var is None:
            raise GeneratorError(
                "despawn_hit used outside an if_action's then/else stack")
        return ["%s%s.despawn()" % (indent, hit_var)]

    if kind == "if_else":
        lines = ["%sif %s:" % (indent, render_condition(node["condition"]))]
        lines.extend(_render_per_sprite_list(node["then"], indent + "    ", hit_var))
        else_nodes = node.get("else", [])
        if else_nodes:
            lines.append("%selse:" % (indent,))
            lines.extend(_render_per_sprite_list(else_nodes, indent + "    ", hit_var))
        return lines

    # kind == "if_action": bind a fresh local for this Action's run_one()
    # result, branch on "found something" (not None -- vs2.DONE included,
    # matching every Action's own "result is None means nothing notable
    # happened" contract), and make that local visible to any nested
    # despawn_hit as this node's own `hit_var`.
    bind = node["bind"]
    local = "_" + bind + "_result"
    lines = ["%s%s = self.%s.run_one(sprite)" % (indent, local, bind)]
    lines.append("%sif %s is not None:" % (indent, local))
    lines.extend(_render_per_sprite_list(node["then"], indent + "    ", local))
    else_nodes = node.get("else", [])
    if else_nodes:
        lines.append("%selse:" % (indent,))
        lines.extend(_render_per_sprite_list(else_nodes, indent + "    ", local))
    return lines


# ---------------------------------------------------------------------------
# step()/step_one() assembly
# ---------------------------------------------------------------------------

def _render_step_pool(model):
    """``def step(self, sprites):`` -- the uniform prologue, then the exact
    downward-indexed despawn-safe loop ``Projectile.step()`` uses (see this
    module's docstring)."""
    lines = ["    def step(self, sprites):"]
    lines.extend(_render_apply_to_all(model, "sprites", INDENT))
    per_sprite = model.get("per_sprite", [])
    if not per_sprite:
        return lines
    lines.append("%slive = sprites._live" % (INDENT,))
    lines.append("%sindex = len(live) - 1" % (INDENT,))
    lines.append("%swhile index >= 0:" % (INDENT,))
    lines.append("%s    sprite = live[index]" % (INDENT,))
    lines.extend(_render_per_sprite_list(per_sprite, INDENT + "    ", None))
    lines.append("%s    index -= 1" % (INDENT,))
    return lines


def _render_step_one(model):
    """``def step_one(self, sprite):`` -- the lone-sprite subject form:
    the uniform prologue calls ``run_one`` directly (no pool to sweep), and
    the per-sprite statements apply to ``sprite`` with no loop at all."""
    lines = ["    def step_one(self, sprite):"]
    lines.extend(_render_apply_to_all(model, "sprite", INDENT))
    per_sprite = model.get("per_sprite", [])
    lines.extend(_render_per_sprite_list(per_sprite, INDENT, None))
    return lines


# ---------------------------------------------------------------------------
# Full-file assembly
# ---------------------------------------------------------------------------

def render_body(model):
    """The generated file's body -- everything except the banner and the
    trailing blob line. Deterministic: the same model always renders the
    same body, byte for byte."""
    params = model.get("params", [])
    param_classes = set()
    param_lines = []
    for param in params:
        param_class, decl_src = _render_param_decl(param)
        param_classes.add(param_class)
        param_lines.append("    %s = %s" % (param["name"], decl_src))

    state = model.get("state", [])

    lines = []
    if model.get("actions"):
        lines.append("from vs2 import actions")
    lines.append("from vs2.behaviors import Behavior")
    if param_classes:
        lines.append("from vs2.params import %s" % (", ".join(sorted(param_classes)),))
    lines.append("")
    lines.append("")
    lines.append("class %s(Behavior):" % (model["class_name"],))
    if param_lines:
        lines.extend(param_lines)
        lines.append("")
    if state:
        lines.append("    state = %r" % (tuple(state),))
        lines.append("")
    lines.extend(_render_attached(model))
    lines.append("")
    if model["subject_kind"] == "pool":
        lines.extend(_render_step_pool(model))
    else:
        lines.extend(_render_step_one(model))
    return "\n".join(lines)


def generate_source(model, basename):
    """The full generated file text: banner, body, blank line, blob.
    ``basename`` (e.g. ``"generated_projectile.py"``) is recorded in the
    banner only."""
    model_module.validate_model(model)
    body = render_body(model)
    sha = checksum.body_sha(body)
    banner_line = checksum.make_banner(basename, sha)
    blob_line = checksum.make_blob_line(encode_blob(model))
    return checksum.join_generated_file(banner_line, body, blob_line)


class WriteResult:
    """Outcome of :func:`write_behavior_file`. ``status`` is one of
    ``"created"``, ``"updated"``, ``"unchanged"``, ``"hand_edited"`` or
    ``"detached"`` -- the same five outcomes
    ``tools.vs2_scene_gen.generator.WriteResult``/
    ``tools.vs2_event_gen.generator.WriteResult`` document, applied to a
    generated Behavior file instead."""

    def __init__(self, status, path, message):
        self.status = status
        self.path = path
        self.message = message

    def __repr__(self):
        return "WriteResult(%r, %r, %r)" % (self.status, str(self.path), self.message)


def write_behavior_file(model, output_path):
    """Regenerate ``output_path`` from ``model`` if it is safe to do so.
    Never raises for any of the five normal outcomes above -- only a
    malformed ``model`` (:class:`~model.ModelError`) or an unwritable path
    can raise."""
    basename = output_path.name
    new_text = generate_source(model, basename)

    if not output_path.exists():
        output_path.write_text(new_text)
        return WriteResult("created", output_path, "wrote new file")

    existing = output_path.read_text()
    parsed = checksum.split_generated_file(existing)
    if parsed is None:
        return WriteResult(
            "detached", output_path,
            "file exists but is not generator-managed (no banner+blob); left untouched")

    banner_line, body, _blob_line = parsed
    if checksum.recorded_sha(banner_line) != checksum.body_sha(body):
        return WriteResult(
            "hand_edited", output_path,
            "recorded body-sha does not match the file's actual body; "
            "refusing to overwrite a hand-edited generated file")

    if existing == new_text:
        return WriteResult("unchanged", output_path, "regenerated content is byte-identical")

    output_path.write_text(new_text)
    return WriteResult("updated", output_path, "model changed; file regenerated")
