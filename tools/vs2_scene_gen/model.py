"""The scene-model schema: plain JSON, validated procedurally.

Shape, in one picture (a synthetic example -- see
``games/vs2_examples/vixeous/code/vixeous_scene.model.json`` for a real
one)::

    {
      "version": 1,
      "class_name": "DemoScene",
      "vars": [{"name": "score", "default": 0, "min": 0}],
      "layers": [
        {"attr": "world", "projection": "TUNNEL", "drawables": [
          {"kind": "sprite_pool", "attr": "enemies", "image": "enemy.png",
           "count": 6, "on_empty": "RECYCLE",
           "vars": [{"name": "kind", "default": 0, "min": 0, "max": 2}],
           "kinds": {"rows": {"basic": [0], "tough": [2]}},
           "behaviors": [
             {"class": "Moving", "params": {"speed_y": -1}},
             {"class": "Transient", "name": "burn",
              "params": {"ticks": 18, "on_end": {"handler": "enemy_died"}}}
           ]}
        ]}
      ],
      "families": [{"attr": "hostiles", "members": ["enemies"]}],
      "scene_behaviors": []
    }

This deliberately mirrors what
``apps/micropython/ventilastation/behavior_control.py``'s ``_build_registry``
walks at runtime (layers -> pools/sprites -> vars/behaviors -> params) --
that module describes a *built* scene; this one describes a scene *to
build*, so the two shapes read as inverses of each other by design.

**What this format cannot express, on purpose.** Per the proposal,
``build()`` is a flat declarative sequence with literal values, ``Var()``
bindings and cross-references -- "nothing in build() branches or loops
over game state" -- so this schema has no ``if``, no loop, no expression
grammar beyond the four value forms in :mod:`values`. Anything with
control flow (event handling, scene transitions, per-tick game logic)
belongs in ``update()``, a separate hand-written or (eventually, T16)
generated file -- see this package's docstring.

**Scope note.** ``Layer.camera_x``/``camera_y`` are runtime properties set
imperatively (typically once per tick, in ``update()``, per the proposal's
own ``self.world.camera_x = self.camera_theta``) -- they are not
``layer()`` constructor arguments, so they have no place in a model that
only describes ``build()``. Likewise ``vs2.project.var(persist=True)``
is not modeled: neither ``Scene.var()`` nor ``SpritePool.var()`` (the two
forms this schema does support) take a ``persist=`` argument at all, and
nothing in this task's proving case needs project-level persistence --
the same declaration mechanics are already exercised by scene/pool
``vars``.
"""

import keyword
import re

SCHEMA_VERSION = 1

DRAWABLE_KINDS = ("sprite", "sprite_pool", "tilemap", "label")
PROJECTIONS = ("TUNNEL", "HUD", "FULLSCREEN", "VS1_TUNNEL")

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Reserved on every generated class: the hook methods themselves, plus the
#: two methods every ``vs2.Scene`` subclass already defines.
_RESERVED_ATTRS = {"build", "update", "on_enter", "on_exit"}


class ModelError(ValueError):
    """Raised by :func:`validate_model` with a message naming the exact
    offending path (e.g. ``"layers[0].drawables[2].attr"``), the same
    convention T1/T3's own build-time errors use."""


def _check_identifier(value, where):
    if not isinstance(value, str) or not _IDENTIFIER_RE.match(value):
        raise ModelError("%s: %r is not a valid Python identifier" % (where, value))
    if keyword.iskeyword(value):
        raise ModelError("%s: %r is a Python keyword" % (where, value))
    if value in _RESERVED_ATTRS or value.startswith("on_build_") or value.startswith("_"):
        raise ModelError(
            "%s: %r is reserved (on_build_* hooks, build/update, or a "
            "leading underscore)" % (where, value))


def _check_value(value, where, known_attrs=None):
    """A value in the grammar :mod:`values` renders: ``None``, ``bool``,
    ``int``/``float``, ``str``, a list/tuple (rendered as a Python tuple,
    recursively validated), or a single-key dict tagging a ``var``,
    ``ref``, ``handler`` or ``expr`` -- see :mod:`values` for what each
    renders to. A ``ref`` is checked against ``known_attrs`` (the pools/
    sprites/families declared earlier in the model, in generated-code
    order) when given; ``handler`` is deliberately *not* checked -- the
    spec's own worked example (``on_death=self.enemy_died``) references a
    method the generated file never defines on purpose (see this
    package's docstring and ``regenerate.ensure_companion_stub``)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _check_value(item, "%s[%d]" % (where, index), known_attrs)
        return
    if isinstance(value, dict):
        if len(value) != 1:
            raise ModelError(
                "%s: a value dict must have exactly one of var/ref/handler/expr; "
                "got keys %r" % (where, sorted(value.keys())))
        key, inner = next(iter(value.items()))
        if key not in ("var", "ref", "handler", "expr"):
            raise ModelError("%s: unknown value tag %r" % (where, key))
        if not isinstance(inner, str) or not inner:
            raise ModelError("%s.%s: must be a non-empty string" % (where, key))
        if key == "ref" and known_attrs is not None and inner not in known_attrs:
            raise ModelError(
                "%s.ref: %r is not a pool/sprite/family declared earlier in "
                "this model" % (where, inner))
        return
    raise ModelError("%s: %r is not a value this generator can render" % (where, value))


def _check_params(params, where, known_attrs):
    if not isinstance(params, dict):
        raise ModelError("%s: params must be an object" % (where,))
    for key, value in params.items():
        if not isinstance(key, str) or not key:
            raise ModelError("%s: param name %r is not a string" % (where, key))
        _check_value(value, "%s.%s" % (where, key), known_attrs)


def _check_behavior(behavior, where, known_attrs):
    if not isinstance(behavior, dict):
        raise ModelError("%s: must be an object" % (where,))
    class_name = behavior.get("class")
    if not isinstance(class_name, str) or not _IDENTIFIER_RE.match(class_name):
        raise ModelError("%s.class: %r is not a valid class name" % (where, class_name))
    name = behavior.get("name")
    if name is not None and (not isinstance(name, str) or not name):
        raise ModelError("%s.name: must be a non-empty string or null" % (where,))
    _check_params(behavior.get("params", {}), where + ".params", known_attrs)
    extra = set(behavior.keys()) - {"class", "name", "params"}
    if extra:
        raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))


def _check_var(var, where):
    if not isinstance(var, dict):
        raise ModelError("%s: must be an object" % (where,))
    name = var.get("name")
    _check_identifier(name, where + ".name")
    if "default" not in var:
        raise ModelError("%s: missing 'default'" % (where,))
    _check_value(var["default"], where + ".default")  # a var default is always literal
    for key in ("min", "max", "step", "label", "unit"):
        if key in var and var[key] is not None:
            if key in ("label", "unit") and not isinstance(var[key], str):
                raise ModelError("%s.%s: must be a string" % (where, key))
    if "options" in var and var["options"] is not None:
        if not isinstance(var["options"], list):
            raise ModelError("%s.options: must be a list" % (where,))
    extra = set(var.keys()) - {"name", "default", "min", "max", "step", "label", "unit", "options"}
    if extra:
        raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))


def _check_kinds(kinds, where, declared_var_names):
    if not isinstance(kinds, dict):
        raise ModelError("%s: must be an object" % (where,))
    rows = kinds.get("rows")
    if not isinstance(rows, dict) or not rows:
        raise ModelError("%s.rows: must be a non-empty object" % (where,))
    for kind_name, row in rows.items():
        if not isinstance(kind_name, str) or not kind_name:
            raise ModelError("%s.rows: kind name %r is not a string" % (where, kind_name))
        if not isinstance(row, list):
            raise ModelError("%s.rows.%s: must be a list" % (where, kind_name))
        if len(row) != len(declared_var_names):
            raise ModelError(
                "%s.rows.%s: has %d value(s); this pool declares %d "
                "variable(s) (%s)" % (where, kind_name, len(row),
                                      len(declared_var_names), ", ".join(declared_var_names)))
        for index, value in enumerate(row):
            _check_value(value, "%s.rows.%s[%d]" % (where, kind_name, index))
    extra = set(kinds.keys()) - {"rows"}
    if extra:
        raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))


def _check_projection(projection, where):
    if isinstance(projection, str):
        if projection not in PROJECTIONS:
            raise ModelError(
                "%s: %r is not one of %s" % (where, projection, ", ".join(PROJECTIONS)))
        return
    if isinstance(projection, dict) and list(projection.keys()) == ["tunnel"]:
        params = projection["tunnel"]
        if not isinstance(params, dict):
            raise ModelError("%s.tunnel: must be an object" % (where,))
        extra = set(params.keys()) - {"gamma", "near", "far"}
        if extra:
            raise ModelError("%s.tunnel: unknown key(s) %r" % (where, sorted(extra)))
        return
    raise ModelError(
        "%s: must be one of %s, or {\"tunnel\": {...}}" % (where, ", ".join(PROJECTIONS)))


def _check_drawable(drawable, where, seen_attrs):
    if not isinstance(drawable, dict):
        raise ModelError("%s: must be an object" % (where,))
    kind = drawable.get("kind")
    if kind not in DRAWABLE_KINDS:
        raise ModelError("%s.kind: %r is not one of %s" % (where, kind, DRAWABLE_KINDS))
    attr = drawable.get("attr")
    _check_identifier(attr, where + ".attr")
    if attr in seen_attrs:
        raise ModelError("%s.attr: %r is already used elsewhere in this model" % (where, attr))
    seen_attrs.add(attr)

    image = drawable.get("image")
    if not isinstance(image, str) or not image:
        raise ModelError("%s.image: must be a non-empty string" % (where,))

    if kind == "sprite":
        allowed = {"kind", "attr", "image", "x", "y", "frame", "visible", "flip_x", "flip_y",
                   "behaviors"}
    elif kind == "sprite_pool":
        allowed = {"kind", "attr", "image", "count", "frame", "on_empty",
                   "vars", "kinds", "behaviors"}
        count = drawable.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ModelError("%s.count: must be a positive integer" % (where,))
        on_empty = drawable.get("on_empty")
        if on_empty is not None and on_empty != "RECYCLE":
            raise ModelError(
                "%s.on_empty: must be null or \"RECYCLE\"" % (where,))
    elif kind == "tilemap":
        allowed = {"kind", "attr", "image", "columns", "rows", "x", "y",
                   "view_width", "view_height", "view_x", "view_y",
                   "visible", "flip_x", "flip_y", "behaviors"}
        for field in ("columns", "rows"):
            value = drawable.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ModelError("%s.%s: must be a positive integer" % (where, field))
    else:  # "label"
        allowed = {"kind", "attr", "image", "columns", "rows", "x", "y",
                   "text", "glyphs", "visible", "flip_x", "flip_y", "behaviors"}
        columns = drawable.get("columns")
        if not isinstance(columns, int) or isinstance(columns, bool) or columns < 1:
            raise ModelError("%s.columns: must be a positive integer" % (where,))

    extra = set(drawable.keys()) - allowed
    if extra:
        raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))

    for key in ("x", "y", "view_x", "view_y", "frame"):
        if key in drawable:
            _check_value(drawable[key], "%s.%s" % (where, key), seen_attrs)

    if kind == "sprite_pool":
        var_names = []
        for index, var in enumerate(drawable.get("vars", [])):
            _check_var(var, "%s.vars[%d]" % (where, index))
            name = var["name"]
            if name in var_names:
                raise ModelError("%s.vars: %r declared twice" % (where, name))
            var_names.append(name)
        if "kinds" in drawable:
            _check_kinds(drawable["kinds"], where + ".kinds", var_names)

    for index, behavior in enumerate(drawable.get("behaviors", [])):
        _check_behavior(behavior, "%s.behaviors[%d]" % (where, index), seen_attrs)


def validate_model(model):
    """Raise :class:`ModelError` naming the exact offending path if
    ``model`` does not match the schema this module documents. Returns
    ``None`` on success (called for its side effect, like the runtime's
    own build-time validation)."""
    if not isinstance(model, dict):
        raise ModelError("model: must be an object")
    extra = set(model.keys()) - {"version", "class_name", "vars", "layers",
                                  "families", "scene_behaviors"}
    if extra:
        raise ModelError("model: unknown key(s) %r" % (sorted(extra),))

    version = model.get("version")
    if version != SCHEMA_VERSION:
        raise ModelError("model.version: expected %r, got %r" % (SCHEMA_VERSION, version))

    class_name = model.get("class_name")
    if not isinstance(class_name, str) or not _IDENTIFIER_RE.match(class_name):
        raise ModelError("model.class_name: %r is not a valid class name" % (class_name,))
    if keyword.iskeyword(class_name):
        raise ModelError("model.class_name: %r is a Python keyword" % (class_name,))

    seen_attrs = set()

    for index, var in enumerate(model.get("vars", [])):
        _check_var(var, "model.vars[%d]" % (index,))

    scene_var_names = {v["name"] for v in model.get("vars", [])}
    if len(scene_var_names) != len(model.get("vars", [])):
        raise ModelError("model.vars: a name is declared twice")

    layers = model.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ModelError("model.layers: must be a non-empty list")
    for layer_index, layer in enumerate(layers):
        where = "model.layers[%d]" % (layer_index,)
        if not isinstance(layer, dict):
            raise ModelError("%s: must be an object" % (where,))
        attr = layer.get("attr")
        _check_identifier(attr, where + ".attr")
        if attr in seen_attrs:
            raise ModelError("%s.attr: %r is already used elsewhere in this model" % (where, attr))
        seen_attrs.add(attr)
        if "name" in layer and layer["name"] is not None and not isinstance(layer["name"], str):
            raise ModelError("%s.name: must be a string or null" % (where,))
        _check_projection(layer.get("projection", "TUNNEL"), where + ".projection")
        if "visible" in layer and not isinstance(layer["visible"], bool):
            raise ModelError("%s.visible: must be a boolean" % (where,))
        extra = set(layer.keys()) - {"attr", "name", "projection", "visible", "drawables"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        drawables = layer.get("drawables", [])
        if not isinstance(drawables, list):
            raise ModelError("%s.drawables: must be a list" % (where,))
        for drawable_index, drawable in enumerate(drawables):
            _check_drawable(drawable, "%s.drawables[%d]" % (where, drawable_index), seen_attrs)

    for index, family in enumerate(model.get("families", [])):
        where = "model.families[%d]" % (index,)
        if not isinstance(family, dict):
            raise ModelError("%s: must be an object" % (where,))
        attr = family.get("attr")
        _check_identifier(attr, where + ".attr")
        if attr in seen_attrs:
            raise ModelError("%s.attr: %r is already used elsewhere in this model" % (where, attr))
        seen_attrs.add(attr)
        members = family.get("members")
        if not isinstance(members, list) or not members:
            raise ModelError("%s.members: must be a non-empty list" % (where,))
        for member in members:
            if member not in seen_attrs:
                raise ModelError(
                    "%s.members: %r is not a pool/sprite declared earlier in this "
                    "model" % (where, member))
        extra = set(family.keys()) - {"attr", "members"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))

    for index, behavior in enumerate(model.get("scene_behaviors", [])):
        _check_behavior(behavior, "model.scene_behaviors[%d]" % (index,), seen_attrs)
