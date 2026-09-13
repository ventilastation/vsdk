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
package's docstring): no ``Var``-bound parameters, no ``Spawn``/damage
Actions as *Action classes* (they do not exist in the shipped catalog yet --
see ``apps/micropython/vs2/behaviors.py``'s own ``Projectile`` docstring for
why its real hand-written form is trimmed the same way). ``if_action``/
``despawn_hit`` exist because ``Projectile``'s real ``step()`` needs exactly
this ("if Collide finds something, despawn it and myself") and nothing
richer.

**Phase 2: state hats.** A model may additionally carry a top-level
``"state_machine"`` key -- see the ``## State hats`` section below -- which
switches the *generated base class* from :class:`~vs2.behaviors.Behavior` to
:class:`~vs2.behaviors.StateMachine` and replaces the flat
``per_sprite``/``apply_to_all`` zones with one method per declared state.
Phase 2 also adds four new per-sprite node kinds usable in *either* shape
(a plain Behavior's ``per_sprite`` list, or a state's own body): ``set_state``
(a plain assignment, the ``accumulate`` node's non-accumulating sibling),
``call_callback`` (invoke a declared ``Callback`` parameter), ``spawn``
(spawn into a declared ``PoolRef`` parameter -- e.g. an explosion pool) and
``play_sound`` (play a declared ``Sound`` parameter, honouring the real
:class:`~vs2.params.Sound`'s "tuple of names picked from at random" contract
via the same ``vs2.behaviors._choose_sound`` helper ``Transient`` already
uses). None of these needed a *new* expression kind: ``spawn``'s ``x``/``y``
arguments read ``sprite.x``/``sprite.y`` through the existing ``"state"``
expression kind, extended to accept the two built-in Sprite fields
(:data:`BUILTIN_SPRITE_FIELDS`) alongside a Behavior's own declared
``state`` names -- from the renderer's point of view both already mean
"read ``sprite.<name>``", so there was nothing to add there.

## State hats

Shape, one state cycle from ``games/vs2_examples/vasura_states_demo`` (see
that game's own model.json for the real thing)::

    {
      ...,
      "apply_to_all": [], "per_sprite": [],   # unused in this shape
      "state_machine": {
        "states": ["orbiting", "chiller_falling", "falling", "exploding"],
        "initial": "orbiting",
        "bodies": {
          "orbiting": {
            "enter": [{"kind": "hold", "ticks": {"kind": "literal", "value": 128},
                       "then": "chiller_falling"}],
            "step": [{"kind": "accumulate", "state": "theta",
                      "amount": {"kind": "param", "name": "speed_x"}}]
          },
          "chiller_falling": {
            "enter": [{"kind": "hold", "ticks": {"kind": "literal", "value": 40},
                       "then": "falling"}],
            "step": []
          },
          "falling": {
            "step": [
              {"kind": "accumulate", "state": "y", "amount": {"kind": "param", "name": "speed_y"}},
              {"kind": "if_else",
               "condition": {"kind": "compare", "op": ">=",
                              "left": {"kind": "state", "name": "y"},
                              "right": {"kind": "param", "name": "ground_y"}},
               "then": [{"kind": "goto_state", "name": "exploding"}], "else": []}
            ]
          },
          "exploding": {
            "enter": [{"kind": "play_sound", "name": "sound"}],
            "step": [{"kind": "despawn"}]
          }
        }
      }
    }

**Why one ``"state_machine"`` object, not flat top-level keys.** Everything
a state-hat program needs (``states``, ``initial``, each state's body) is
its own namespace, exactly the way ``actions``/``per_sprite`` already keep
the two-zone skeleton's own concerns visibly separate -- and it makes "is
this a state-hat program at all" a single ``model.get("state_machine")``
truthiness check, both here and in :mod:`generator`.

**Why ``apply_to_all``/``per_sprite`` are mutually exclusive with
``state_machine``.** The generated class does not override ``step``/
``step_one`` at all -- see :mod:`generator`'s docstring -- so there is no
"uniform prologue" phase left to hang ``apply_to_all`` off of, and no flat
per-sprite zone outside a state's own body for ``per_sprite`` to describe.
A model declaring both is almost certainly an authoring mistake (dragging
a per-sprite block outside any state hat), so it is rejected outright
rather than silently ignored.

**Each declared state needs a ``"step"`` body** (matching
:class:`~vs2.behaviors.StateMachine`'s own "every declared state needs its
own method, even a no-op one" rule) **but ``"enter"``/``"exit"`` are
optional**, generated only when the model actually supplies one -- the
same "optional hooks, matched by name, skipped when absent" contract the
real class documents. A state body's node list ends either in a
``goto_state`` node (rendered as ``return "<name>"``, matching "a per-state
method... returns the next state's name") or simply runs out (falls off the
end, rendered as an implicit ``None`` return -- "stay").

**``hold`` and ``goto_state`` are new node kinds, valid *only* inside a
state's own ``enter``/``step``/``exit`` body** (see
:data:`STATE_BODY_EXTRA_KINDS`) -- ``self.hold(sprite, ...)`` only exists on
:class:`~vs2.behaviors.StateMachine`, and "return this state's name" only
means anything inside a per-state method. Both name their target state by a
plain string checked against the model's own declared ``states``, not
through the ``EXPR_KINDS`` vocabulary (there is no "literal vs. param vs.
state" choice for *which state to enter next* the way there is for a
numeric amount).
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

#: Built-in :class:`~vs2.Sprite` fields a ``"state"``-kind expression may
#: also *read*, and a ``set_state``/``accumulate`` node may also *write*,
#: alongside a Behavior's own declared ``state`` names -- see this module's
#: docstring on why reading did not need a new expression kind. Three
#: fields, deliberately: ``x``/``y`` (Phase 2's ``spawn`` node needs them,
#: to spawn at the dying sprite's own position) and ``visible`` (the
#: ``Damageable`` reference model's own "hide while invulnerable" toggle
#: needs to write it, and vs2.behaviors.Blinking/Transient/DespawnBeyond
#: all treat it as an ordinary, safe, game-facing field to flip) -- not
#: every ``Sprite`` attribute, which would let a block program reach into
#: framework internals (``frame``, layer membership, ...) this schema has
#: never otherwise exposed.
BUILTIN_SPRITE_FIELDS = ("x", "y", "visible")

#: Per-sprite node kinds valid in *either* shape: a plain Behavior's flat
#: ``per_sprite`` list, or one state's own ``enter``/``step``/``exit`` body
#: (see :data:`STATE_BODY_EXTRA_KINDS` for the two kinds valid only in the
#: latter). ``set_state``/``call_callback``/``spawn``/``play_sound`` are
#: Phase 2 additions -- see this module's docstring for why each exists and
#: why none of them needed a new expression kind.
PER_SPRITE_KINDS = ("accumulate", "if_else", "if_action", "despawn", "despawn_hit",
                     "set_state", "call_callback", "spawn", "play_sound")

#: Node kinds valid *only* inside a state's own body -- see this module's
#: docstring's "## State hats" section for why ``hold``/``goto_state`` make
#: no sense outside one.
STATE_BODY_EXTRA_KINDS = ("goto_state", "hold")
STATE_BODY_KINDS = PER_SPRITE_KINDS + STATE_BODY_EXTRA_KINDS

#: Method names a state-hat model's own machinery already claims on the
#: generated class (everything :class:`~vs2.behaviors.StateMachine` itself
#: defines, plus ``states``/``initial``, the two structural class
#: attributes -- not ``vs2.params.Parameter`` declarations, see
#: :mod:`generator`) -- a declared state name colliding with one of these
#: would silently shadow real framework machinery instead of failing loudly
#: at build time.
_RESERVED_STATEMACHINE_NAMES = {
    "attached", "action", "actions", "step", "step_one", "step_scene",
    "hold", "state_name", "force_state", "recycle", "states", "initial",
}

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
        # Phase 1 never needed a bool literal (Projectile's own condition
        # is a plain numeric compare). Phase 2's Damageable reference model
        # needs one -- comparing its own "blink" Flag parameter against a
        # literal true/false, to gate a set_state node on a runtime
        # configuration value the model itself cannot know ahead of time
        # (a Parameter's actual value is only fixed at construction,
        # e.g. ``Damageable(blink=True)`` vs. ``Damageable(blink=False)``
        # for the very same generated class) -- so bool is now allowed
        # alongside number/string/null.
        if not isinstance(value, (int, float, str, bool, type(None))):
            raise ModelError("%s.value: must be a number, string, bool or null" % (where,))
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
    if name not in state_names and name not in BUILTIN_SPRITE_FIELDS:
        raise ModelError(
            "%s.name: %r is not a declared state field, and not one of "
            "the built-in sprite fields %s (%s declared)"
            % (where, name, BUILTIN_SPRITE_FIELDS,
               ", ".join(sorted(state_names)) or "none"))


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


def _check_per_sprite_list(nodes, where, param_names, state_names, action_binds,
                            allowed_kinds=PER_SPRITE_KINDS, declared_states=None):
    if not isinstance(nodes, list):
        raise ModelError("%s: must be a list" % (where,))
    for index, node in enumerate(nodes):
        _check_per_sprite_node(node, "%s[%d]" % (where, index),
                                param_names, state_names, action_binds,
                                allowed_kinds, declared_states)


def _check_per_sprite_node(node, where, param_names, state_names, action_binds,
                            allowed_kinds=PER_SPRITE_KINDS, declared_states=None):
    """Validate one per-sprite (or state-body) node. ``allowed_kinds`` is
    :data:`PER_SPRITE_KINDS` for a plain Behavior's flat ``per_sprite`` list,
    or :data:`STATE_BODY_KINDS` inside a state hat's own body (see
    :func:`_check_state_machine`) -- the two extra kinds that set enables,
    ``goto_state``/``hold``, need ``declared_states`` (the enclosing state
    machine's own ``states``, as a set) to validate the state name they
    name against."""
    if not isinstance(node, dict):
        raise ModelError("%s: must be an object with a 'kind'" % (where,))
    kind = node.get("kind")
    if kind not in allowed_kinds:
        raise ModelError("%s.kind: %r is not one of %s" % (where, kind, allowed_kinds))

    if kind == "accumulate":
        # Also accepts the built-in sprite fields (x/y), alongside a
        # declared per-sprite state field -- a state-hat body driving a
        # sprite's own descent directly (this package's own
        # games/vs2_examples/vasura_states_demo reference game: "falling"
        # accumulates straight into sprite.y) is exactly as legitimate as
        # vs2.behaviors.Recycling's own direct ``sprite.x = ...``
        # teleport: neither is trying to *compose* with a separate
        # Move/MoveTo Action on the same subject the way the dx/dy
        # accumulator exists for. A model that *does* also want Move/
        # MoveTo on the same field should prefer those instead -- this
        # schema does not force that choice either way, matching the real
        # catalog's own precedent of Behaviors reaching directly into x/y
        # when the effect is not meant to compose.
        extra = set(node.keys()) - {"kind", "state", "amount"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        state = node.get("state")
        if state not in state_names and state not in BUILTIN_SPRITE_FIELDS:
            raise ModelError(
                "%s.state: %r is not a declared state field, and not one "
                "of the built-in sprite fields %s"
                % (where, state, BUILTIN_SPRITE_FIELDS))
        if "amount" not in node:
            raise ModelError("%s: missing 'amount'" % (where,))
        _check_expr(node["amount"], where + ".amount", param_names, state_names)
        return

    if kind == "set_state":
        extra = set(node.keys()) - {"kind", "state", "value"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        state = node.get("state")
        if state not in state_names and state not in BUILTIN_SPRITE_FIELDS:
            raise ModelError(
                "%s.state: %r is not a declared state field, and not one "
                "of the built-in sprite fields %s"
                % (where, state, BUILTIN_SPRITE_FIELDS))
        if "value" not in node:
            raise ModelError("%s: missing 'value'" % (where,))
        _check_expr(node["value"], where + ".value", param_names, state_names)
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

    if kind == "call_callback":
        extra = set(node.keys()) - {"kind", "name", "args"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        name = node.get("name")
        if name not in param_names:
            raise ModelError("%s.name: %r is not a declared parameter" % (where, name))
        args = node.get("args", [])
        if not isinstance(args, list):
            raise ModelError("%s.args: must be a list" % (where,))
        for index, arg in enumerate(args):
            _check_expr(arg, "%s.args[%d]" % (where, index), param_names, state_names)
        return

    if kind == "spawn":
        extra = set(node.keys()) - {"kind", "pool", "x", "y"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        pool = node.get("pool")
        if pool not in param_names:
            raise ModelError("%s.pool: %r is not a declared parameter" % (where, pool))
        if "x" not in node or "y" not in node:
            raise ModelError("%s: 'spawn' needs both 'x' and 'y'" % (where,))
        _check_expr(node["x"], where + ".x", param_names, state_names)
        _check_expr(node["y"], where + ".y", param_names, state_names)
        return

    if kind == "play_sound":
        extra = set(node.keys()) - {"kind", "name"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        name = node.get("name")
        if name not in param_names:
            raise ModelError("%s.name: %r is not a declared parameter" % (where, name))
        return

    if kind == "goto_state":
        extra = set(node.keys()) - {"kind", "name"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        name = node.get("name")
        if name not in declared_states:
            raise ModelError(
                "%s.name: %r is not one of this state machine's states (%s)"
                % (where, name, ", ".join(sorted(declared_states)) or "none"))
        return

    if kind == "hold":
        extra = set(node.keys()) - {"kind", "ticks", "then"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        if "ticks" not in node:
            raise ModelError("%s: missing 'ticks'" % (where,))
        _check_expr(node["ticks"], where + ".ticks", param_names, state_names)
        then = node.get("then")
        if then not in declared_states:
            raise ModelError(
                "%s.then: %r is not one of this state machine's states (%s)"
                % (where, then, ", ".join(sorted(declared_states)) or "none"))
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
                                action_binds, allowed_kinds, declared_states)
        _check_per_sprite_list(node.get("else", []), where + ".else", param_names,
                                state_names, action_binds, allowed_kinds, declared_states)
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
                            action_binds, allowed_kinds, declared_states)
    _check_per_sprite_list(node.get("else", []), where + ".else", param_names,
                            state_names, action_binds, allowed_kinds, declared_states)


def _check_state_machine(state_machine, where, param_names, state_names, action_binds):
    """Validate ``model.state_machine`` -- see this module's docstring's
    "## State hats" section for the shape. ``state_names`` here is the
    model's own ordinary per-sprite ``state`` list (e.g. a counter a state
    body accumulates into), a different set from the state machine's own
    ``states`` (the named FSM states themselves, checked separately)."""
    if not isinstance(state_machine, dict):
        raise ModelError("%s: must be an object" % (where,))
    allowed = {"states", "initial", "bodies"}
    extra = set(state_machine.keys()) - allowed
    if extra:
        raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))

    states = state_machine.get("states")
    if not isinstance(states, list) or not states:
        raise ModelError("%s.states: must be a non-empty list" % (where,))

    declared_states = set()
    generated_names = set()
    for index, name in enumerate(states):
        state_where = "%s.states[%d]" % (where, index)
        _check_identifier(name, state_where, reserved=_RESERVED_STATEMACHINE_NAMES)
        if name in param_names:
            raise ModelError(
                "%s: %r collides with a declared parameter of the same name"
                % (state_where, name))
        if name in state_names:
            raise ModelError(
                "%s: %r collides with a declared (ordinary) state field"
                % (state_where, name))
        if name in declared_states:
            raise ModelError("%s.states: duplicate state name %r" % (where, name))
        declared_states.add(name)
        generated_names.add(name)

    initial = state_machine.get("initial")
    if initial not in declared_states:
        raise ModelError(
            "%s.initial: %r is not one of its own states: %s"
            % (where, initial, ", ".join(sorted(declared_states))))

    bodies = state_machine.get("bodies")
    if not isinstance(bodies, dict):
        raise ModelError("%s.bodies: must be an object" % (where,))
    unknown_bodies = set(bodies.keys()) - declared_states
    if unknown_bodies:
        raise ModelError(
            "%s.bodies: %r is not one of this state machine's states"
            % (where, sorted(unknown_bodies)))
    missing_bodies = declared_states - set(bodies.keys())
    if missing_bodies:
        raise ModelError(
            "%s.bodies: missing a body for state(s) %r -- every declared "
            "state needs one, even an empty 'step' list"
            % (where, sorted(missing_bodies)))

    for name in states:
        body = bodies[name]
        body_where = "%s.bodies.%s" % (where, name)
        if not isinstance(body, dict):
            raise ModelError("%s: must be an object" % (body_where,))
        allowed_hooks = {"enter", "step", "exit"}
        extra_hooks = set(body.keys()) - allowed_hooks
        if extra_hooks:
            raise ModelError("%s: unknown key(s) %r" % (body_where, sorted(extra_hooks)))
        if "step" not in body:
            raise ModelError("%s: missing 'step'" % (body_where,))
        for hook, method_name in (("enter", "enter_" + name), ("step", name),
                                   ("exit", "exit_" + name)):
            if hook not in body:
                continue
            if method_name in generated_names and method_name != name:
                raise ModelError(
                    "%s.bodies: generated method name %r collides with "
                    "another state's own method" % (where, method_name))
            generated_names.add(method_name)
            _check_per_sprite_list(
                body[hook], "%s.%s" % (body_where, hook), param_names, state_names,
                action_binds, STATE_BODY_KINDS, declared_states)


def validate_model(model):
    """Raise :class:`ModelError` naming the exact offending path if
    ``model`` does not match the schema this module documents. Returns
    ``None`` on success."""
    if not isinstance(model, dict):
        raise ModelError("model: must be an object")
    allowed = {"version", "class_name", "subject_kind", "params", "state",
               "actions", "apply_to_all", "per_sprite", "state_machine"}
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

    state_machine = model.get("state_machine")
    if state_machine is not None:
        # See model.py's own docstring ("Why apply_to_all/per_sprite are
        # mutually exclusive with state_machine") -- the generated class
        # never overrides step()/step_one(), so neither zone has anywhere
        # to render into once a model is state-hat shaped.
        if apply_to_all:
            raise ModelError(
                "model.apply_to_all: not allowed together with "
                "model.state_machine -- the generated class inherits "
                "step()/step_one() unchanged, so there is no uniform "
                "prologue to run these against")
        if per_sprite:
            raise ModelError(
                "model.per_sprite: not allowed together with "
                "model.state_machine -- put per-sprite decisions inside "
                "the relevant state's own body instead")
        _check_state_machine(state_machine, "model.state_machine", param_names,
                              state_names, action_binds)
    else:
        _check_per_sprite_list(per_sprite, "model.per_sprite", param_names, state_names,
                                action_binds)
