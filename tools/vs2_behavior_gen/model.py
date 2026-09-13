"""The behavior-block-program schema: plain JSON, validated procedurally.

Spec: ``docs/vs2-behaviors-proposal.md``, ``## The block editor`` (tier 5:
the Action palette) and ``### The tick skeleton makes the fast shape
unavoidable``. Work-breakdown card: ``docs/vs2-behaviors-implementation.md``
T17, Phase 1.

**What this format expresses.** One :class:`~vs2.behaviors.Behavior`
subclass, authored as the proposal's two-zone tick skeleton: a subject kind
(``"pool"`` or ``"sprite"`` -- see below for why ``"scene"`` is not
supported yet), a set of declared parameters (the same
``vs2.params.Parameter`` vocabulary every hand-written Behavior uses), a set
of Actions composed once in ``attached()``, an *apply to all* list (Actions
run uniformly, column-wise) and a *for each sprite* list of per-sprite
decisions (state bookkeeping, comparisons, and branching on whether an
Action found something).

Shape, in one picture (this is exactly ``Projectile``, expressed as a block
program -- see ``tools/vs2_behavior_gen/generator.py``'s module docstring
for the generated source this produces)::

    {
      "version": 1,
      "class_name": "GeneratedProjectile",
      "subject_kind": "pool",
      "params": [
        {"name": "speed_x", "type": "angle", "default": 0,
         "min": -32, "max": 32, "step": 0.25,
         "label": "Angular speed", "unit": "col/tick"},
        {"name": "speed_y", "type": "number", "default": 8,
         "min": -32, "max": 32, "step": 0.25,
         "label": "Radial speed", "unit": "led/tick"},
        {"name": "range", "type": "number", "default": 180,
         "min": 1, "max": 255, "step": 1, "label": "Range", "unit": "led"},
        {"name": "hits", "type": "pool", "default": None, "label": "Hits what"}
      ],
      "state": ["shot_flown"],
      "actions": [
        {"bind": "move", "action_class": "Move",
         "args": {"speed_x": {"kind": "param", "name": "speed_x"},
                   "speed_y": {"kind": "param", "name": "speed_y"}}},
        {"bind": "hit", "action_class": "Collide",
         "args": {"targets": {"kind": "param", "name": "hits"}}}
      ],
      "apply_to_all": ["move"],
      "per_sprite": [
        {"kind": "accumulate", "state": "shot_flown",
         "amount": {"kind": "param", "name": "speed_y"}},
        {"kind": "if_else",
         "condition": {"kind": "compare", "op": ">",
                        "left": {"kind": "state", "name": "shot_flown"},
                        "right": {"kind": "param", "name": "range"}},
         "then": [{"kind": "despawn"}],
         "else": [
           {"kind": "if_action", "bind": "hit",
            "then": [{"kind": "despawn_hit"}, {"kind": "despawn"}],
            "else": []}
         ]}
      ]
    }

**Why ``"pool"``/``"sprite"`` only, not ``"scene"``.** The proposal's own
``### Subjects`` text: a scene-subject Behavior "may not use
``run(sprites)`` -- there is no pool to sweep -- so it is per-tick work of
fixed, tiny size", a genuinely different shape (no per-sprite loop, no
``apply_to_all``/``per_sprite`` split at all) than the two-zone skeleton this
schema models. Building a *third*, scene-shaped skeleton is not needed by
this phase's proving case (``Projectile`` is pool-shaped) and is left for a
future phase rather than guessed at here.

**Why ``"family"`` is not a subject kind here either.** A family dispatches
each member to whichever of ``step``/``step_one`` fits its own kind (see
``apps/micropython/vs2/__init__.py``'s ``Scene._run_behaviors``) -- the
*generated class* itself only ever needs to define ``step``/``step_one``,
exactly like every hand-written catalog Behavior already does (see
``apps/micropython/vs2/behaviors.py``: every catalog entry except
``Projectile`` defines both). A block program that declares subject_kind
``"pool"`` produces a class attachable to a pool, a sprite, *or* a family
of pools (and one declaring ``"sprite"`` likewise attaches to a sprite or a
family of sprites) -- "family" was never a third *code shape*, only a third
*attachment site*, so it does not need its own schema branch.

**What this format cannot express, on purpose** (Phase 1 scope, see this
package's docstring): no state hats, no ``StateMachine``, no ``Var``-bound
parameters, no ``Spawn``/``PlaySound``/damage Actions (they do not exist in
the shipped catalog yet -- see ``apps/micropython/vs2/behaviors.py``'s own
``Projectile`` docstring for why its real hand-written form is trimmed the
same way). ``if_action``/``despawn_hit`` exist because ``Projectile``'s real
``step()`` needs exactly this ("if Collide finds something, despawn it and
myself") and nothing richer.
"""

import keyword
import re

SCHEMA_VERSION = 1

SUBJECT_KINDS = ("pool", "sprite")

#: The Phase-1 Action catalog, and the constructor-level field each accepts.
#: Mirrors ``tools/vs2_behavior_gen/catalog.py``'s ``ACTION_FIELDS`` --
#: duplicated here, deliberately, so this module never has to import the
#: real ``vs2`` package just to validate a model (matching
#: ``tools.vs2_scene_gen.model``/``tools.vs2_event_gen.model``'s own
#: hardcoded-vocabulary convention). See ``catalog.py``'s module docstring
#: for *why* these fields are hand-listed rather than purely introspected --
#: ``Collide``'s ``targets``/``radius``/``space`` and ``Animate``'s
#: ``field`` are plain constructor keywords, not declared
#: ``vs2.params.Parameter`` attributes, so ``vs2.params.introspect()`` alone
#: cannot see them.
ACTION_FIELDS = {
    "Move": {"speed_x", "speed_y", "accel_x", "accel_y"},
    "MoveTo": {"x", "y", "speed_x", "speed_y"},
    "Animate": {"first", "last", "ticks", "mode", "field"},
    "Collide": {"targets", "radius", "space"},
}

#: Fields every action *requires* an explicit arg for (no default a
#: generated ``attached()`` could silently fall back to). Only ``Collide``'s
#: ``targets`` -- a plain required positional parameter on the real class.
ACTION_REQUIRED_FIELDS = {
    "Move": set(),
    "MoveTo": set(),
    "Animate": set(),
    "Collide": {"targets"},
}

EXPR_KINDS = ("literal", "param", "state")
CONDITION_KINDS = ("compare",)
COMPARE_OPS = ("==", "!=", "<", ">", "<=", ">=")
PER_SPRITE_KINDS = ("accumulate", "if_else", "if_action", "despawn", "despawn_hit")

#: One entry per ``vs2.params`` parameter type this schema accepts on a
#: Behavior's own ``params`` list (see ``apps/micropython/vs2/params.py``).
#: ``callback``/``frames``/``sound``/``image``/``points`` are declarable
#: (a generated Behavior may need one to match a real catalog entry's
#: parameter set) even though nothing in Phase 1's ``per_sprite``/``actions``
#: vocabulary reads one back out again.
PARAM_TYPES = (
    "number", "angle", "flag", "choice", "frames", "sound", "image",
    "pool", "points", "callback",
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Reserved on every generated Behavior: the framework's own accumulator
#: and state-machine byte names (see ``docs/vs2-behaviors-proposal.md``,
#: "### Per-instance state") plus this schema's own method names.
_RESERVED_STATE_NAMES = {
    "dx", "dy", "fsm_state", "fsm_hold", "fsm_then", "enabled",
}


class ModelError(ValueError):
    """Raised by :func:`validate_model` with a message naming the exact
    offending path, matching ``tools.vs2_scene_gen.model``/
    ``tools.vs2_event_gen.model``'s own convention."""


def _check_identifier(value, where, reserved=()):
    if not isinstance(value, str) or not _IDENTIFIER_RE.match(value):
        raise ModelError("%s: %r is not a valid Python identifier" % (where, value))
    if keyword.iskeyword(value):
        raise ModelError("%s: %r is a Python keyword" % (where, value))
    if value.startswith("_"):
        raise ModelError("%s: %r may not start with an underscore" % (where, value))
    if value in reserved:
        raise ModelError("%s: %r is reserved" % (where, value))


def _check_param(param, where):
    if not isinstance(param, dict):
        raise ModelError("%s: must be an object" % (where,))
    allowed = {"name", "type", "default", "min", "max", "step", "label", "unit", "options"}
    extra = set(param.keys()) - allowed
    if extra:
        raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
    _check_identifier(param.get("name"), where + ".name")
    type_name = param.get("type")
    if type_name not in PARAM_TYPES:
        raise ModelError("%s.type: %r is not one of %s" % (where, type_name, PARAM_TYPES))
    if "default" not in param:
        raise ModelError("%s: missing 'default'" % (where,))
    options = param.get("options")
    if options is not None and not isinstance(options, list):
        raise ModelError("%s.options: must be a list" % (where,))


def _check_expr(expr, where, param_names, state_names):
    if not isinstance(expr, dict):
        raise ModelError("%s: must be an object with a 'kind'" % (where,))
    kind = expr.get("kind")
    if kind not in EXPR_KINDS:
        raise ModelError("%s.kind: %r is not one of %s" % (where, kind, EXPR_KINDS))
    if kind == "literal":
        extra = set(expr.keys()) - {"kind", "value"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        value = expr.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float, str, type(None))):
            raise ModelError("%s.value: must be a number, string or null" % (where,))
        return
    if kind == "param":
        name = expr.get("name")
        if name not in param_names:
            raise ModelError(
                "%s.name: %r is not a declared parameter (%s)"
                % (where, name, ", ".join(sorted(param_names)) or "none declared"))
        return
    # kind == "state"
    name = expr.get("name")
    if name not in state_names:
        raise ModelError(
            "%s.name: %r is not a declared state field (%s)"
            % (where, name, ", ".join(sorted(state_names)) or "none declared"))


def _check_condition(condition, where, param_names, state_names):
    if not isinstance(condition, dict):
        raise ModelError("%s: must be an object with a 'kind'" % (where,))
    kind = condition.get("kind")
    if kind not in CONDITION_KINDS:
        raise ModelError("%s.kind: %r is not one of %s" % (where, kind, CONDITION_KINDS))
    extra = set(condition.keys()) - {"kind", "op", "left", "right"}
    if extra:
        raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
    op = condition.get("op")
    if op not in COMPARE_OPS:
        raise ModelError("%s.op: %r is not one of %s" % (where, op, COMPARE_OPS))
    if "left" not in condition or "right" not in condition:
        raise ModelError("%s: 'compare' needs both 'left' and 'right'" % (where,))
    _check_expr(condition["left"], where + ".left", param_names, state_names)
    _check_expr(condition["right"], where + ".right", param_names, state_names)


def _check_action_decl(action, where, param_names):
    if not isinstance(action, dict):
        raise ModelError("%s: must be an object" % (where,))
    extra = set(action.keys()) - {"bind", "action_class", "args"}
    if extra:
        raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
    _check_identifier(action.get("bind"), where + ".bind")
    action_class = action.get("action_class")
    if action_class not in ACTION_FIELDS:
        raise ModelError(
            "%s.action_class: %r is not one of %s"
            % (where, action_class, sorted(ACTION_FIELDS)))
    args = action.get("args", {})
    if not isinstance(args, dict):
        raise ModelError("%s.args: must be an object" % (where,))
    valid_fields = ACTION_FIELDS[action_class]
    unknown_fields = set(args.keys()) - valid_fields
    if unknown_fields:
        raise ModelError(
            "%s.args: %s has no field(s) %r; valid: %s"
            % (where, action_class, sorted(unknown_fields), sorted(valid_fields)))
    missing = ACTION_REQUIRED_FIELDS[action_class] - set(args.keys())
    if missing:
        raise ModelError(
            "%s.args: %s needs %r" % (where, action_class, sorted(missing)))
    for field_name, expr in args.items():
        _check_expr(expr, "%s.args.%s" % (where, field_name), param_names, ())


def _check_per_sprite_list(nodes, where, param_names, state_names, action_binds):
    if not isinstance(nodes, list):
        raise ModelError("%s: must be a list" % (where,))
    for index, node in enumerate(nodes):
        _check_per_sprite_node(node, "%s[%d]" % (where, index),
                                param_names, state_names, action_binds)


def _check_per_sprite_node(node, where, param_names, state_names, action_binds):
    if not isinstance(node, dict):
        raise ModelError("%s: must be an object with a 'kind'" % (where,))
    kind = node.get("kind")
    if kind not in PER_SPRITE_KINDS:
        raise ModelError("%s.kind: %r is not one of %s" % (where, kind, PER_SPRITE_KINDS))

    if kind == "accumulate":
        extra = set(node.keys()) - {"kind", "state", "amount"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        state = node.get("state")
        if state not in state_names:
            raise ModelError("%s.state: %r is not a declared state field" % (where, state))
        if "amount" not in node:
            raise ModelError("%s: missing 'amount'" % (where,))
        _check_expr(node["amount"], where + ".amount", param_names, state_names)
        return

    if kind == "despawn":
        extra = set(node.keys()) - {"kind"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        return

    if kind == "despawn_hit":
        extra = set(node.keys()) - {"kind"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        return

    if kind == "if_else":
        extra = set(node.keys()) - {"kind", "condition", "then", "else"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        if "condition" not in node:
            raise ModelError("%s: missing 'condition'" % (where,))
        _check_condition(node["condition"], where + ".condition", param_names, state_names)
        if "then" not in node:
            raise ModelError("%s: missing 'then'" % (where,))
        _check_per_sprite_list(node["then"], where + ".then", param_names, state_names,
                                action_binds)
        _check_per_sprite_list(node.get("else", []), where + ".else", param_names,
                                state_names, action_binds)
        return

    # kind == "if_action": "if <bound Action>.run_one(sprite) found something, do..."
    extra = set(node.keys()) - {"kind", "bind", "then", "else"}
    if extra:
        raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
    bind = node.get("bind")
    if bind not in action_binds:
        raise ModelError(
            "%s.bind: %r is not a declared action (%s)"
            % (where, bind, ", ".join(sorted(action_binds)) or "none declared"))
    if "then" not in node:
        raise ModelError("%s: missing 'then'" % (where,))
    _check_per_sprite_list(node["then"], where + ".then", param_names, state_names,
                            action_binds)
    _check_per_sprite_list(node.get("else", []), where + ".else", param_names,
                            state_names, action_binds)


def validate_model(model):
    """Raise :class:`ModelError` naming the exact offending path if
    ``model`` does not match the schema this module documents. Returns
    ``None`` on success."""
    if not isinstance(model, dict):
        raise ModelError("model: must be an object")
    allowed = {"version", "class_name", "subject_kind", "params", "state",
               "actions", "apply_to_all", "per_sprite"}
    extra = set(model.keys()) - allowed
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

    subject_kind = model.get("subject_kind")
    if subject_kind not in SUBJECT_KINDS:
        raise ModelError(
            "model.subject_kind: %r is not one of %s" % (subject_kind, SUBJECT_KINDS))

    params = model.get("params", [])
    if not isinstance(params, list):
        raise ModelError("model.params: must be a list")
    param_names = set()
    for index, param in enumerate(params):
        _check_param(param, "model.params[%d]" % (index,))
        name = param["name"]
        if name in param_names:
            raise ModelError("model.params: duplicate parameter name %r" % (name,))
        param_names.add(name)

    state = model.get("state", [])
    if not isinstance(state, list):
        raise ModelError("model.state: must be a list")
    state_names = set()
    for index, name in enumerate(state):
        _check_identifier(name, "model.state[%d]" % (index,), reserved=_RESERVED_STATE_NAMES)
        if name in param_names:
            raise ModelError(
                "model.state[%d]: %r collides with a declared parameter of the same name"
                % (index, name))
        if name in state_names:
            raise ModelError("model.state: duplicate state name %r" % (name,))
        state_names.add(name)

    actions = model.get("actions", [])
    if not isinstance(actions, list):
        raise ModelError("model.actions: must be a list")
    action_binds = set()
    for index, action in enumerate(actions):
        _check_action_decl(action, "model.actions[%d]" % (index,), param_names)
        bind = action["bind"]
        if bind in action_binds:
            raise ModelError("model.actions: duplicate bind name %r" % (bind,))
        action_binds.add(bind)

    apply_to_all = model.get("apply_to_all", [])
    if not isinstance(apply_to_all, list):
        raise ModelError("model.apply_to_all: must be a list")
    for index, bind in enumerate(apply_to_all):
        if bind not in action_binds:
            raise ModelError(
                "model.apply_to_all[%d]: %r is not a declared action" % (index, bind))

    per_sprite = model.get("per_sprite", [])
    _check_per_sprite_list(per_sprite, "model.per_sprite", param_names, state_names,
                            action_binds)
