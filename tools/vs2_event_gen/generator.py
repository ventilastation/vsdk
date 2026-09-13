"""Model -> generated ``<name>_events.py`` mixin source, and the safe write
path.

**A mixin, not a scene.** Per this package's docstring, this generator does
not produce a ``vs2.Scene`` subclass -- it produces a plain class carrying
``on_enter(self)`` and ``update(self)``, meant to sit first in a hand-
written scene's bases (``class Title(TitleSceneEvents, vs2.Scene):``) so
``super().on_enter()``/``super().update()`` inside the generated methods
reach the real ``vs2.Scene`` implementation through cooperative MRO --
exactly the shape every hand-written ``on_enter`` override in this repo
already uses.

**Why ``goto_scene`` imports its target module lazily, inside the method
body, instead of at the top of the generated file.** Three scenes that
transition to each other in a cycle (title -> playing -> game-over ->
title, exactly this package's proving game) produce hand-written scene
modules that import each other in a cycle too, one hop later: if
``gameover_scene_events.py`` imported ``title_scene`` at module scope,
loading ``title_scene`` (which imports ``playing_scene``, which imports
generated ``playing_scene_events``, which would import ``gameover_scene``,
which imports ``gameover_scene_events``, which imports ``title_scene``
again -- still mid-import) breaks with a partially-initialized module.
Deferring the ``import ... as _scene`` line to the exact point inside
``on_enter``/``update`` where the target is actually constructed sidesteps
this entirely: by the time that line executes, the whole game has long
since finished importing, so there is nothing partial left to hit, and
Python's module cache makes the repeated ``import`` on every tick a cheap
dict lookup, not a re-execution. This is a standard, deliberate Python
idiom for breaking import cycles, not a workaround the model format
should have to know about.

**Why ``goto_scene`` propagates ``_vs_api_slug``/``_vs_declared_api``.**
``ventilastation.director.Director._enter_scene`` re-reads
``getattr(scene, "_vs_api_slug", None)`` and re-establishes the current-app
context via ``api_guard.begin_app(...)`` on *every* scene entry, including a
``Scene.switch()``. ``vs2.project`` variables are keyed to that same
current-app slug (``_Project._ensure_current_app``) and are wiped the
moment the slug changes. A freshly constructed target scene has neither
attribute set, so a naive ``self.switch(TargetScene())`` would read back as
"a different app just started" on the very next tick and silently drop
every project variable -- including the score this whole proving case
exists to carry across a transition. Copying both attributes from ``self``
onto the target before switching is therefore not a style choice: without
it, ``goto_scene`` breaks the one property (score survives a scene
transition) this package's proving game is built to demonstrate. Every
game in this repo that only ever pushes/switches within a single app never
hits this because ``app_loader.load_app`` sets the attributes once, on the
*first* scene only -- multi-scene VS2 games did not exist yet when that
codepath was written.

**Sequential same-tick evaluation.** Multiple ``on_tick`` entries compile,
in model order, into a straight-line sequence of ``if`` blocks inside one
``update()`` method -- not a dispatch table, not early-exit. A later
entry's action can and does observe an earlier entry's effect from the same
tick (see :mod:`model`'s docstring for why the proving game relies on
exactly this to fake "increment" without arithmetic).
"""

from tools.vs2_scene_gen.blob import encode_blob

from . import checksum
from . import model as model_module

INDENT = "        "  # inside a method body: 4 (class) + 4 (def) spaces


class GeneratorError(ValueError):
    """Raised when a file exists on disk but is not safe to overwrite --
    see :func:`write_events_file`'s ``"hand_edited"`` status, the normal way
    this surfaces; this exception is for callers that want a hard failure
    instead."""


# ---------------------------------------------------------------------------
# Expression / condition / action rendering
# ---------------------------------------------------------------------------

def render_expr(expr, imports):
    """``expr`` (a value in :mod:`model`'s three-form expression grammar)
    -> Python source. Adds to ``imports`` (a set) any name the rendered
    source needs imported (currently only ``"randrange"``, for
    ``random``)."""
    kind = expr["kind"]
    if kind == "literal":
        return repr(expr["value"])
    if kind == "var":
        return "vs2.project.%s" % (expr["name"],)
    # kind == "random": inclusive both ends (the Blockly "random integer
    # from A to B" convention), via urandom.randrange's exclusive-stop
    # semantics -- randrange(a, b + 1).
    imports.add("randrange")
    a_src = render_expr(expr["a"], imports)
    b_src = render_expr(expr["b"], imports)
    return "randrange(%s, (%s) + 1)" % (a_src, b_src)


def render_condition(condition, imports):
    """``condition`` -> a Python boolean expression source string."""
    if condition["kind"] == "compare":
        left = render_expr(condition["left"], imports)
        right = render_expr(condition["right"], imports)
        return "%s %s %s" % (left, condition["op"], right)
    # kind == "timer_elapsed"
    return "self._vs2_events_ticks >= %d" % (condition["ticks"],)


def render_action(action, indent, imports):
    """``action`` -> a list of source lines, each already prefixed with
    ``indent``."""
    kind = action["kind"]

    if kind == "set_variable":
        value_src = render_expr(action["value"], imports)
        return ["%svs2.project.%s = %s" % (indent, action["name"], value_src)]

    if kind == "set_label_text":
        text_src = render_expr(action["text"], imports)
        return ["%sself.%s.text = %s" % (indent, action["label_attr"], text_src)]

    # kind == "goto_scene": the import is local to this action's own block,
    # not module-level -- see this module's docstring for why.
    return [
        "%simport %s as _scene" % (indent, action["module"]),
        "%s_target = _scene.%s()" % (indent, action["class_name"]),
        "%s_target._vs_api_slug = self._vs_api_slug" % (indent,),
        "%s_target._vs_declared_api = self._vs_declared_api" % (indent,),
        "%sself.switch(_target)" % (indent,),
    ]


# ---------------------------------------------------------------------------
# Pre-pass: every project variable this model ever sets, in first-seen order
# ---------------------------------------------------------------------------

def _collect_declared_vars(model):
    names = []
    seen = set()
    for event in model["events"]:
        for action in event.get("actions", []):
            if action["kind"] == "set_variable" and action["name"] not in seen:
                seen.add(action["name"])
                names.append(action["name"])
    return names


# ---------------------------------------------------------------------------
# Method-body assembly
# ---------------------------------------------------------------------------

def _render_event_block(event, imports):
    conditions = event.get("conditions", [])
    if conditions:
        cond_src = " and ".join(render_condition(c, imports) for c in conditions)
        lines = ["%sif %s:" % (INDENT, cond_src)]
        action_indent = INDENT + "    "
    else:
        lines = []
        action_indent = INDENT
    for action in event["actions"]:
        lines.extend(render_action(action, action_indent, imports))
    return lines


def _render_on_enter(model, imports, declared_vars):
    lines = ["%ssuper().on_enter()" % (INDENT,)]
    lines.append("%sself._vs2_events_ticks = 0" % (INDENT,))
    for name in declared_vars:
        lines.append("%svs2.project.var(%r, 0)" % (INDENT, name))
    for event in model["events"]:
        if event["kind"] == "on_start":
            lines.extend(_render_event_block(event, imports))
    return lines


def _render_update(model, imports):
    lines = ["%ssuper().update()" % (INDENT,)]
    lines.append("%sself._vs2_events_ticks += 1" % (INDENT,))
    for event in model["events"]:
        if event["kind"] == "on_tick":
            lines.extend(_render_event_block(event, imports))
    return lines


def render_body(model):
    """The generated file's body -- everything except the banner and the
    trailing blob line. Deterministic: the same model always renders the
    same body, byte for byte. ``goto_scene`` needs no header-level import
    at all -- see this module's docstring for why its ``import`` line is
    local to the action's own block instead."""
    imports = set()
    declared_vars = _collect_declared_vars(model)

    on_enter_lines = _render_on_enter(model, imports, declared_vars)
    update_lines = _render_update(model, imports)

    lines = ["import vs2"]
    if "randrange" in imports:
        lines.append("from urandom import randrange")
    lines.append("")
    lines.append("")
    lines.append("class %s:" % (model["class_name"],))
    lines.append("    def on_enter(self):")
    lines.extend(on_enter_lines)
    lines.append("")
    lines.append("    def update(self):")
    lines.extend(update_lines)
    return "\n".join(lines)


def generate_source(model, basename):
    """The full generated file text: banner, body, blank line, blob.
    ``basename`` (e.g. ``"playing_scene_events.py"``) is recorded in the
    banner only -- it plays no role in the checksum or the blob."""
    model_module.validate_model(model)
    body = render_body(model)
    sha = checksum.body_sha(body)
    banner_line = checksum.make_banner(basename, sha)
    blob_line = checksum.make_blob_line(encode_blob(model))
    return checksum.join_generated_file(banner_line, body, blob_line)


class WriteResult:
    """Outcome of :func:`write_events_file`. ``status`` is one of
    ``"created"``, ``"updated"``, ``"unchanged"``, ``"hand_edited"`` or
    ``"detached"`` -- exactly the five outcomes
    ``tools.vs2_scene_gen.generator.WriteResult`` documents, applied to an
    event-sheet mixin file instead of a scene file."""

    def __init__(self, status, path, message):
        self.status = status
        self.path = path
        self.message = message

    def __repr__(self):
        return "WriteResult(%r, %r, %r)" % (self.status, str(self.path), self.message)


def write_events_file(model, output_path):
    """Regenerate ``output_path`` from ``model`` if it is safe to do so.
    Never raises for any of the five normal outcomes above -- only a
    malformed ``model`` (a :class:`~model.ModelError`) or an unwritable
    path can raise."""
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
