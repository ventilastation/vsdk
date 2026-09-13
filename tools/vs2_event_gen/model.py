"""The event-sheet schema: plain JSON, validated procedurally.

Shape, in one picture (a synthetic example)::

    {
      "version": 1,
      "class_name": "PlayingSceneEvents",
      "events": [
        {"kind": "on_start", "conditions": [],
         "actions": [
           {"kind": "set_variable", "name": "score",
            "value": {"kind": "literal", "value": 0}}
         ]},
        {"kind": "on_tick",
         "conditions": [{"kind": "timer_elapsed", "ticks": 60}],
         "actions": [
           {"kind": "set_variable", "name": "score",
            "value": {"kind": "random",
                       "a": {"kind": "literal", "value": 25},
                       "b": {"kind": "literal", "value": 35}}}
         ]},
        {"kind": "on_tick",
         "conditions": [{"kind": "compare",
                          "left": {"kind": "var", "name": "score"},
                          "op": ">=",
                          "right": {"kind": "literal", "value": 25}}],
         "actions": [
           {"kind": "goto_scene",
            "module": "games.vs2_examples.event_sheet_demo.code.gameover_scene",
            "class_name": "GameOverScene"}
         ]}
      ]
    }

**One flat list of events, not one event with many rule-groups.** Two
``on_tick`` entries (as above) are two independent condition/action groups,
both evaluated -- in list order -- every ``update()`` call. That ordering is
load-bearing, not incidental: a later ``on_tick`` entry's actions run after
an earlier one's in the *same* tick, so a later entry's ``set_variable`` on
a name an earlier entry also wrote wins for that tick. This is how this
package's own proving game (``games/vs2_examples/event_sheet_demo``) fakes
"increment" without arithmetic (explicitly out of scope -- see this
package's docstring): successive ``on_tick`` entries at increasing
``timer_elapsed`` thresholds, each a plain literal ``set_variable``, read as
a staged step function once you know later-wins-same-tick.

**What this format cannot express, on purpose** (see this package's own
docstring for the full out-of-scope list): no arithmetic in expressions, no
sprite/pool Action blocks, no state hats, exactly the two condition kinds
and three action kinds enumerated below -- nothing else.
"""

import keyword
import re

SCHEMA_VERSION = 1

EVENT_KINDS = ("on_start", "on_tick")
CONDITION_KINDS = ("compare", "timer_elapsed")
EXPR_KINDS = ("literal", "var", "random")
ACTION_KINDS = ("set_variable", "goto_scene", "set_label_text")
COMPARE_OPS = ("==", "!=", "<", ">", "<=", ">=")

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DOTTED_MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")

#: Reserved on every generated mixin: the two methods it defines, plus the
#: private tick counter it keeps for ``timer_elapsed``.
_RESERVED_ATTRS = {"on_enter", "update", "_vs2_events_ticks"}


class ModelError(ValueError):
    """Raised by :func:`validate_model` with a message naming the exact
    offending path (e.g. ``"events[1].actions[0].value.a"``), the same
    convention :mod:`tools.vs2_scene_gen.model` uses."""


def _check_identifier(value, where):
    if not isinstance(value, str) or not _IDENTIFIER_RE.match(value):
        raise ModelError("%s: %r is not a valid Python identifier" % (where, value))
    if keyword.iskeyword(value):
        raise ModelError("%s: %r is a Python keyword" % (where, value))
    if value in _RESERVED_ATTRS or value.startswith("_"):
        raise ModelError(
            "%s: %r is reserved (on_enter/update/_vs2_events_ticks, or a "
            "leading underscore)" % (where, value))


def _check_expr(expr, where):
    if not isinstance(expr, dict):
        raise ModelError("%s: must be an object with a 'kind'" % (where,))
    kind = expr.get("kind")
    if kind not in EXPR_KINDS:
        raise ModelError("%s.kind: %r is not one of %s" % (where, kind, EXPR_KINDS))

    if kind == "literal":
        value = expr.get("value")
        extra = set(expr.keys()) - {"kind", "value"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ModelError(
                "%s.value: must be a number or string literal, got %r" % (where, value))
        return

    if kind == "var":
        name = expr.get("name")
        _check_identifier(name, where + ".name")
        extra = set(expr.keys()) - {"kind", "name"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        return

    # kind == "random"
    if "a" not in expr or "b" not in expr:
        raise ModelError("%s: 'random' needs both 'a' and 'b'" % (where,))
    extra = set(expr.keys()) - {"kind", "a", "b"}
    if extra:
        raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
    _check_expr(expr["a"], where + ".a")
    _check_expr(expr["b"], where + ".b")


def _check_condition(condition, where):
    if not isinstance(condition, dict):
        raise ModelError("%s: must be an object with a 'kind'" % (where,))
    kind = condition.get("kind")
    if kind not in CONDITION_KINDS:
        raise ModelError("%s.kind: %r is not one of %s" % (where, kind, CONDITION_KINDS))

    if kind == "compare":
        extra = set(condition.keys()) - {"kind", "left", "op", "right"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        op = condition.get("op")
        if op not in COMPARE_OPS:
            raise ModelError("%s.op: %r is not one of %s" % (where, op, COMPARE_OPS))
        if "left" not in condition or "right" not in condition:
            raise ModelError("%s: 'compare' needs both 'left' and 'right'" % (where,))
        _check_expr(condition["left"], where + ".left")
        _check_expr(condition["right"], where + ".right")
        return

    # kind == "timer_elapsed"
    extra = set(condition.keys()) - {"kind", "ticks"}
    if extra:
        raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
    ticks = condition.get("ticks")
    if not isinstance(ticks, int) or isinstance(ticks, bool) or ticks < 1:
        raise ModelError("%s.ticks: must be a positive integer" % (where,))


def _check_action(action, where):
    if not isinstance(action, dict):
        raise ModelError("%s: must be an object with a 'kind'" % (where,))
    kind = action.get("kind")
    if kind not in ACTION_KINDS:
        raise ModelError("%s.kind: %r is not one of %s" % (where, kind, ACTION_KINDS))

    if kind == "set_variable":
        extra = set(action.keys()) - {"kind", "name", "value"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        _check_identifier(action.get("name"), where + ".name")
        if "value" not in action:
            raise ModelError("%s: missing 'value'" % (where,))
        _check_expr(action["value"], where + ".value")
        return

    if kind == "goto_scene":
        extra = set(action.keys()) - {"kind", "module", "class_name"}
        if extra:
            raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
        module = action.get("module")
        if not isinstance(module, str) or not _DOTTED_MODULE_RE.match(module):
            raise ModelError("%s.module: %r is not a dotted module path" % (where, module))
        class_name = action.get("class_name")
        if not isinstance(class_name, str) or not _IDENTIFIER_RE.match(class_name):
            raise ModelError("%s.class_name: %r is not a valid class name" % (where, class_name))
        if keyword.iskeyword(class_name):
            raise ModelError("%s.class_name: %r is a Python keyword" % (where, class_name))
        return

    # kind == "set_label_text"
    extra = set(action.keys()) - {"kind", "label_attr", "text"}
    if extra:
        raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))
    _check_identifier(action.get("label_attr"), where + ".label_attr")
    if "text" not in action:
        raise ModelError("%s: missing 'text'" % (where,))
    _check_expr(action["text"], where + ".text")


def _check_event(event, where):
    if not isinstance(event, dict):
        raise ModelError("%s: must be an object" % (where,))
    extra = set(event.keys()) - {"kind", "conditions", "actions"}
    if extra:
        raise ModelError("%s: unknown key(s) %r" % (where, sorted(extra)))

    kind = event.get("kind")
    if kind not in EVENT_KINDS:
        raise ModelError("%s.kind: %r is not one of %s" % (where, kind, EVENT_KINDS))

    conditions = event.get("conditions", [])
    if not isinstance(conditions, list):
        raise ModelError("%s.conditions: must be a list" % (where,))
    for index, condition in enumerate(conditions):
        _check_condition(condition, "%s.conditions[%d]" % (where, index))

    actions = event.get("actions", [])
    if not isinstance(actions, list) or not actions:
        raise ModelError("%s.actions: must be a non-empty list" % (where,))
    for index, action in enumerate(actions):
        _check_action(action, "%s.actions[%d]" % (where, index))


def validate_model(model):
    """Raise :class:`ModelError` naming the exact offending path if
    ``model`` does not match the schema this module documents. Returns
    ``None`` on success, the same "called for its side effect" convention
    ``tools.vs2_scene_gen.model.validate_model`` uses."""
    if not isinstance(model, dict):
        raise ModelError("model: must be an object")
    extra = set(model.keys()) - {"version", "class_name", "events"}
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

    events = model.get("events")
    if not isinstance(events, list) or not events:
        raise ModelError("model.events: must be a non-empty list")
    for index, event in enumerate(events):
        _check_event(event, "model.events[%d]" % (index,))
