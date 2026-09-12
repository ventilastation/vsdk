"""Model -> generated ``<Name>Scene.py`` source, and the safe write path.

**Numbered ``on_build()`` hooks, exactly.** Per the proposal: "Because
drawables created [in a hand-written ``on_build()``] are invisible to the
editor's model but still consume the sprite budget and take a place in
draw order, the generator emits numbered hook points in draw order rather
than one hook at the end."

This module's convention: flatten every layer's drawables, in the order
layers and drawables appear in the model (which is draw order -- "layers
paint bottom to top in the order they are created", and a layer's own
drawables paint in the order they were created on it). If there are ``N``
drawable-creating statements (``sprite``/``sprite_pool``/``tilemap``/
``label`` -- a plain ``layer()`` call does not count: a layer is a
container, not something that itself consumes the sprite budget or a
draw-order slot) in that flattened order, the generator emits ``N + 1``
hooks, ``on_build_0`` through ``on_build_N``:

- every ``layer()`` call is emitted first, unconditionally, in model
  order -- a hand-written override can always reach ``self.<layer_attr>``
  from any hook, since every layer exists before the first hook fires;
- ``on_build_0`` fires right after the last ``layer()`` call and before
  the first drawable;
- ``on_build_k`` (``1 <= k <= N``) fires right after drawable-statement
  ``k - 1`` (and that drawable's own ``var()``/``kinds()``/``behave()``
  lines, which are never split away from it) and before drawable-
  statement ``k``;
- ``on_build_N`` is therefore also the *last* line ``build()`` runs
  before ``families``/``scene_behaviors`` -- the generalisation of "one
  hook at the end" for a model with no drawables at all (``N == 0``:
  exactly one hook, ``on_build_0``, right after the layers).

Every hook gets a trivial ``pass``-bodied method **on the generated class
itself**, so a scene built directly from the generated class (no
hand-written subclass at all) works standalone; a hand-written subclass
overrides whichever hooks it needs. This mirrors the proposal's "a hook
where a hand-written subclass does post-construction work needing the
graph" -- unlike an event-hook reference (``on_death=self.enemy_died``),
which the generated file deliberately leaves undefined, a hook *method*
must exist so plain instantiation never raises ``AttributeError``.

Scene-level ``vars`` are emitted first, before any layer -- they are
independent of the drawable graph and untouched by hook numbering.
Families and scene-level behaviors are emitted last, after the final
hook -- neither creates a drawable, so neither participates in draw
order.
"""

import re

from . import blob as blob_module
from . import checksum
from . import model as model_module
from .values import render_value

INDENT = "        "  # inside Scene.build(): 4 (class) + 4 (def) spaces
_ATTR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class GeneratorError(ValueError):
    """Raised when a file exists on disk but is not safe to overwrite --
    see :func:`write_scene_file`'s ``"hand_edited"`` status, which is the
    normal, expected way this condition surfaces; this exception is for
    callers (like the CLI) that want a hard failure instead."""


# ---------------------------------------------------------------------------
# Argument rendering per drawable/behavior kind
# ---------------------------------------------------------------------------

def _kwarg(parts, imports, name, container, key, default):
    """Append ``name=<rendered value>`` to ``parts`` iff ``key`` is
    **present** in ``container`` and its value differs from ``default``.

    Presence, not ``dict.get(key) is None``, is what distinguishes "the
    model didn't say" from "the model explicitly wants ``None``" -- several
    real vs2 defaults (``view_width``, ``text``, ``on_end``, ...) *are*
    ``None``, and several are not (``frame=0``, ``visible=True``) while a
    missing key's ``.get()`` would still read back as ``None`` either way.
    Collapsing that distinction is exactly the kind of bug this generator
    must not ship: emitting ``frame=None`` where vs2 expects ``frame=0``
    is a real ``TypeError`` at ``build()``, not a cosmetic difference.
    """
    if key not in container:
        return
    value = container[key]
    if value == default:
        return
    parts.append("%s=%s" % (name, render_value(value, imports)))


def _render_projection(projection, imports):
    if isinstance(projection, str):
        return "vs2.%s" % (projection,)
    params = projection["tunnel"]
    kwargs = []
    _kwarg(kwargs, imports, "gamma", params, "gamma", 0.28)
    _kwarg(kwargs, imports, "near", params, "near", 0)
    _kwarg(kwargs, imports, "far", params, "far", 53)
    return "vs2.tunnel(%s)" % (", ".join(kwargs),)


def _render_layer_call(layer, imports):
    attr = layer["attr"]
    args = []
    name = layer["name"] if "name" in layer else attr
    if name is not None:
        args.append("name=%r" % (name,))
    projection = layer.get("projection", "TUNNEL")
    if projection != "TUNNEL":
        args.append("projection=%s" % (_render_projection(projection, imports),))
    if layer.get("visible", True) is not True:
        args.append("visible=%s" % (render_value(layer["visible"], imports),))
    return "%sself.%s = self.layer(%s)" % (INDENT, attr, ", ".join(args))


def _render_sprite_call(owner, drawable, imports):
    args = [repr(drawable["image"])]
    _kwarg(args, imports, "x", drawable, "x", 0)
    _kwarg(args, imports, "y", drawable, "y", 0)
    _kwarg(args, imports, "frame", drawable, "frame", 0)
    _kwarg(args, imports, "visible", drawable, "visible", True)
    _kwarg(args, imports, "flip_x", drawable, "flip_x", False)
    _kwarg(args, imports, "flip_y", drawable, "flip_y", False)
    return "%s.sprite(%s)" % (owner, ", ".join(args))


def _render_sprite_pool_call(owner, drawable, imports):
    args = [repr(drawable["image"]), str(int(drawable["count"]))]
    _kwarg(args, imports, "frame", drawable, "frame", 0)
    on_empty = drawable.get("on_empty")
    if on_empty == "RECYCLE":
        args.append("on_empty=vs2.RECYCLE")
    return "%s.sprite_pool(%s)" % (owner, ", ".join(args))


def _render_tilemap_call(owner, drawable, imports):
    args = [repr(drawable["image"]), "columns=%d" % (drawable["columns"],),
            "rows=%d" % (drawable["rows"],)]
    _kwarg(args, imports, "x", drawable, "x", 0)
    _kwarg(args, imports, "y", drawable, "y", 0)
    _kwarg(args, imports, "view_width", drawable, "view_width", None)
    _kwarg(args, imports, "view_height", drawable, "view_height", None)
    _kwarg(args, imports, "view_x", drawable, "view_x", 0)
    _kwarg(args, imports, "view_y", drawable, "view_y", 0)
    _kwarg(args, imports, "visible", drawable, "visible", True)
    _kwarg(args, imports, "flip_x", drawable, "flip_x", False)
    _kwarg(args, imports, "flip_y", drawable, "flip_y", False)
    return "%s.tilemap(%s)" % (owner, ", ".join(args))


def _render_label_call(owner, drawable, imports):
    args = [repr(drawable["image"]), "columns=%d" % (drawable["columns"],)]
    _kwarg(args, imports, "rows", drawable, "rows", 1)
    _kwarg(args, imports, "x", drawable, "x", 0)
    _kwarg(args, imports, "y", drawable, "y", 0)
    _kwarg(args, imports, "text", drawable, "text", None)
    _kwarg(args, imports, "glyphs", drawable, "glyphs", None)
    _kwarg(args, imports, "visible", drawable, "visible", True)
    _kwarg(args, imports, "flip_x", drawable, "flip_x", False)
    _kwarg(args, imports, "flip_y", drawable, "flip_y", False)
    return "%s.label(%s)" % (owner, ", ".join(args))


_DRAWABLE_RENDERERS = {
    "sprite": _render_sprite_call,
    "sprite_pool": _render_sprite_pool_call,
    "tilemap": _render_tilemap_call,
    "label": _render_label_call,
}


def _render_var_call(owner_expr, var, imports):
    args = [repr(var["name"]), render_value(var["default"], imports)]
    for key in ("min", "max", "step", "label", "unit", "options"):
        if var.get(key) is not None:
            args.append("%s=%s" % (key, render_value(var[key], imports)))
    return "%s%s.var(%s)" % (INDENT, owner_expr, ", ".join(args))


def _render_kinds_call(owner_expr, kinds, imports):
    rows = kinds["rows"]
    parts = []
    for kind_name in sorted(rows.keys()):
        row = rows[kind_name]
        rendered_row = ", ".join(render_value(v, imports) for v in row)
        if len(row) == 1:
            rendered_row += ","
        parts.append("%s=(%s)" % (kind_name, rendered_row))
    return "%s%s.kinds(%s)" % (INDENT, owner_expr, ", ".join(parts))


def _render_behave_call(owner_expr, behavior, imports):
    params = behavior.get("params", {})
    ctor_args = ", ".join(
        "%s=%s" % (key, render_value(params[key], imports)) for key in sorted(params))
    ctor = "%s(%s)" % (behavior["class"], ctor_args)
    name = behavior.get("name")
    name_kwarg = ", name=%r" % (name,) if name else ""
    return "%s%s.behave(%s%s)" % (INDENT, owner_expr, ctor, name_kwarg)


# ---------------------------------------------------------------------------
# Build-body assembly
# ---------------------------------------------------------------------------

def _render_drawable_block(layer_attr, drawable, imports):
    owner = "self.%s" % (layer_attr,)
    attr = drawable["attr"]
    renderer = _DRAWABLE_RENDERERS[drawable["kind"]]
    lines = ["%sself.%s = %s" % (INDENT, attr, renderer(owner, drawable, imports))]
    if drawable["kind"] == "sprite_pool":
        for var in drawable.get("vars", []):
            lines.append(_render_var_call("self.%s" % (attr,), var, imports))
        if "kinds" in drawable:
            lines.append(_render_kinds_call("self.%s" % (attr,), drawable["kinds"], imports))
    for behavior in drawable.get("behaviors", []):
        lines.append(_render_behave_call("self.%s" % (attr,), behavior, imports))
    return lines


def _render_build_body(model, imports):
    lines = []
    for var in model.get("vars", []):
        lines.append(_render_var_call("self", var, imports))

    for layer in model["layers"]:
        lines.append(_render_layer_call(layer, imports))

    hook_index = 0
    lines.append("%sself.on_build_%d()" % (INDENT, hook_index))
    for layer in model["layers"]:
        for drawable in layer.get("drawables", []):
            lines.extend(_render_drawable_block(layer["attr"], drawable, imports))
            hook_index += 1
            lines.append("%sself.on_build_%d()" % (INDENT, hook_index))
    hook_count = hook_index

    for family in model.get("families", []):
        members = ", ".join("self.%s" % (m,) for m in family["members"])
        lines.append("%sself.%s = self.family(%s)" % (INDENT, family["attr"], members))

    for behavior in model.get("scene_behaviors", []):
        lines.append(_render_behave_call("self", behavior, imports))

    return lines, hook_count


def _collect_behavior_classes(model, classes):
    for behavior in model.get("scene_behaviors", []):
        classes.add(behavior["class"])
    for layer in model["layers"]:
        for drawable in layer.get("drawables", []):
            for behavior in drawable.get("behaviors", []):
                classes.add(behavior["class"])


def render_body(model):
    """The generated file's body -- everything except the banner and the
    trailing blob line (see :mod:`checksum`'s file-shape docstring).
    Deterministic: the same model always renders the same body, byte for
    byte (behavior-class imports and ``kinds()`` rows are emitted in
    sorted order for exactly this reason)."""
    imports = set()
    behavior_classes = set()
    _collect_behavior_classes(model, behavior_classes)

    build_lines, hook_count = _render_build_body(model, imports)

    lines = ["import vs2"]
    if behavior_classes:
        lines.append("from vs2.behaviors import %s" % (", ".join(sorted(behavior_classes)),))
    if "Var" in imports:
        lines.append("from vs2.params import Var")
    lines.append("")
    lines.append("")
    lines.append("class %s(vs2.Scene):" % (model["class_name"],))
    lines.append("    def build(self):")
    lines.extend(build_lines)
    lines.append("")
    for hook_index in range(hook_count + 1):
        lines.append("    def on_build_%d(self):" % (hook_index,))
        lines.append("        pass")
        if hook_index != hook_count:
            lines.append("")
    return "\n".join(lines)


def generate_source(model, basename):
    """The full generated file text: banner, body, blank line, blob.
    ``basename`` (e.g. ``"vixeous_scene.py"``) is recorded in the banner
    only -- it plays no role in the checksum or the blob."""
    model_module.validate_model(model)
    body = render_body(model)
    sha = checksum.body_sha(body)
    banner_line = checksum.make_banner(basename, sha)
    blob_line = checksum.make_blob_line(blob_module.encode_blob(model))
    return checksum.join_generated_file(banner_line, body, blob_line)


def hook_count(model):
    """The number of drawable-creating statements in ``model`` -- the
    generated file carries ``hook_count(model) + 1`` ``on_build_N``
    methods, ``N`` from 0 to this value inclusive."""
    model_module.validate_model(model)
    count = 0
    for layer in model["layers"]:
        count += len(layer.get("drawables", []))
    return count


class WriteResult:
    """Outcome of :func:`write_scene_file`.

    ``status`` is one of:

    - ``"created"`` -- the file did not exist; written fresh.
    - ``"updated"`` -- the file existed, was still generator-managed and
      un-hand-edited, and the model produced different content; rewritten.
    - ``"unchanged"`` -- as above, but the newly generated content is
      byte-identical to what was already on disk; the file is not
      rewritten (so its mtime is left alone).
    - ``"hand_edited"`` -- the file exists, has the generator-managed
      banner+blob shape, but its body no longer matches its own recorded
      checksum. Refused: nothing is written.
    - ``"detached"`` -- the file exists but does not have the generator-
      managed shape at all (no banner, no blob, or both stripped by
      :func:`detach.detach`). Skipped, silently as far as the file goes:
      this is exactly what makes ``Detach`` one-way.
    """

    def __init__(self, status, path, message):
        self.status = status
        self.path = path
        self.message = message

    def __repr__(self):
        return "WriteResult(%r, %r, %r)" % (self.status, str(self.path), self.message)


def write_scene_file(model, output_path):
    """Regenerate ``output_path`` from ``model`` if it is safe to do so.
    See :class:`WriteResult` for the possible outcomes. Never raises for
    any of the four normal outcomes above -- only a malformed ``model``
    (a :class:`~model.ModelError`) or an unwritable path can raise.
    """
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
