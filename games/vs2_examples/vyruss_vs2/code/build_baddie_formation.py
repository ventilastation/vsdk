#!/usr/bin/env python3
"""Builds ``baddie_formation.vs2behavior.json`` and regenerates
``baddie_formation.py`` from it.

Run from the repo root: ``python3
games/vs2_examples/vyruss_vs2/code/build_baddie_formation.py``

Ports the fixed part of ``vyruss_vs2.py``'s own hand-written
``add_baddie()``/``update_one_baddie()`` choreography -- the module-level
``TravelTo``/``TravelBy`` classes and the ``baddie.movements`` queue they
drive -- into a real, block-representable ``StateMachine`` Behavior, using
the ``binary_op`` expression kind added alongside this task (arithmetic and
``min``/``max``, needed here for ``distance = min(speed, remaining)`` and
the signed x-step ``direction * distance``, neither expressible before).

**What this ports, and what it deliberately does not (yet).** The original
queues six heterogeneous movement objects per baddie:
``TravelCloser(85), TravelX(±112), TravelCloser(34), TravelX(∓96),
TravelAway(45), TravelTo(final_x, final_y)``. The first five are a *fixed*
sequence of "move a fixed total distance at a fixed speed" segments --
exactly the shape a state machine's ``hold``-free, counter-and-compare
transition already covers (see ``closer1``/``xmove1``/``closer2``/
``xmove2``/``away`` below). The sixth, ``TravelTo``, is a genuinely
different primitive -- "move *toward* a destination" with wraparound
angular math (``move_toward_angle``/``move_toward_depth`` in
``vyruss_vs2.py``), not a fixed-distance walk -- and is not attempted
here; a baddie reaching the end of ``away`` enters a terminal ``formed``
state (matching the original's own ``baddie.finished = True`` the moment
its queue empties) and hand-written code keeps doing the final
approach-to-formation-position move exactly as it does today. This
mirrors ``vyruss_vs2.py``'s own module docstring's precedent for why
``player_explosion``/collision resolution stay hand-written: forcing a
mismatched shape into the catalog would not honestly represent the
choreography.

**Not yet wired into the live game.** This builds and proves the
Behavior in isolation (see
``tests/test_vyruss_vs2_baddie_formation.py``'s tick-by-tick parity
check against the original ``TravelCloser``/``TravelX``/``TravelAway``
classes) but does not yet replace ``add_baddie()``/
``update_one_baddie()``'s own hand-written dispatch, or get declared on
the real ``baddies`` pool in ``vyruss_vs2_scene.vs2model.json`` -- that
integration (plus the runtime ``force_state()`` hookup the attack-run
reassignment needs, and hardware reverification) is the natural next
step, deliberately left for a follow-up pass rather than rushed
alongside proving the Behavior itself is correct.

**Per-sprite fields this Behavior reads that hand-written code must set
before ``attached()``'s Behavior ever ticks a baddie**, the same
externally-set-then-read seam ``vasura_states_demo``'s own
``enemy.kind``/``enemy.hp`` already establishes: ``x_dir`` (``1`` or
``-1``, matching the original's own ``odd`` branch -- a single flag per
baddie, not one per x-phase; see ``_x_phase``'s own docstring for why
xmove1 and xmove2 derive *opposite* signs from the same flag, mirroring
the original's ``odd``-branch queue literally writing ``TravelX(112), ...,
TravelX(-96)`` for one baddie). ``finished`` starts implicitly falsy
(never explicitly initialized by this Behavior) and is set ``True`` only
on entering ``formed`` -- matching the original's own
``baddie.finished = False`` default at spawn.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.vs2_behavior_gen import build_behavior  # noqa: E402

CODE_DIR = Path(__file__).resolve().parent
MODEL_PATH = CODE_DIR / "baddie_formation.vs2behavior.json"


def _literal(value):
    return {"kind": "literal", "value": value}


def _param(name):
    return {"kind": "param", "name": name}


def _state(name):
    return {"kind": "state", "name": name}


def _binop(op, left, right):
    return {"kind": "binary_op", "op": op, "left": left, "right": right}


def _moved(speed_param):
    """``min(<speed_param>, remaining)`` -- the exact ``distance = min(SPEED,
    self.remaining)`` line every one of the original's ``TravelBy``
    subclasses shares."""
    return _binop("min", _param(speed_param), _state("remaining"))


def _decrement_remaining(speed_param):
    return {"kind": "accumulate", "state": "remaining",
            "amount": _binop("-", _literal(0), _moved(speed_param))}


def _advance_or_stay(next_state):
    return {"kind": "if_else",
            "condition": {"kind": "compare", "op": "<=",
                           "left": _state("remaining"), "right": _literal(0)},
            "then": [{"kind": "goto_state", "name": next_state}], "else": []}


def _y_phase(distance_param, speed_param, sign, next_state):
    """closer1/closer2/away: move ``sprite.y`` by a fixed total distance at
    a fixed speed, one direction only (``sign`` +1 away from the rim, -1
    toward it -- matching ``TravelCloser``/``TravelAway``'s own opposite
    ``sprite.y -=``/``sprite.y +=``)."""
    amount = _moved(speed_param)
    if sign < 0:
        amount = _binop("-", _literal(0), amount)
    return {
        "enter": [{"kind": "set_state", "state": "remaining", "value": _param(distance_param)}],
        "step": [
            {"kind": "accumulate", "state": "y", "amount": amount},
            _decrement_remaining(speed_param),
            _advance_or_stay(next_state),
        ],
    }


def _x_phase(distance_param, next_state, sign):
    """xmove1/xmove2: move ``sprite.x`` by a fixed total distance at
    ``x_speed``, signed by the per-sprite ``x_dir`` field (times ``sign``)
    and wrapped modulo ``width`` -- matching the original ``TravelX.step``'s
    own ``sprite.x = (sprite.x + distance * self.direction) %
    vs2.display.width`` exactly, including the wrap (some formation
    starting columns do cross the 0/width seam during this phase).

    ``sign``: the original's odd-baddie branch is ``TravelX(112),
    TravelX(-96)`` and its even-baddie branch is ``TravelX(-112),
    TravelX(96)`` -- xmove1 and xmove2 always run in *opposite* directions
    for the same baddie, a zigzag, not a fixed per-baddie direction. A
    single per-sprite ``x_dir`` field (matching the original's own single
    ``odd`` flag) gives xmove1's sign directly (+1 odd/-1 even) and
    xmove2's sign as its negation -- xmove1 passes ``sign=1``, xmove2
    passes ``sign=-1``."""
    direction = _state("x_dir") if sign > 0 else _binop("-", _literal(0), _state("x_dir"))
    signed = _binop("*", direction, _moved("x_speed"))
    wrapped = _binop("%", _binop("+", _state("x"), signed), _param("width"))
    return {
        "enter": [{"kind": "set_state", "state": "remaining", "value": _param(distance_param)}],
        "step": [
            {"kind": "set_state", "state": "x", "value": wrapped},
            _decrement_remaining("x_speed"),
            _advance_or_stay(next_state),
        ],
    }


def build_model():
    return {
        "version": 1,
        "class_name": "BaddieFormation",
        "subject_kind": "pool",
        "params": [
            {"name": "x_speed", "type": "number", "default": 3,
             "min": 0, "max": 16, "step": 1, "label": "X speed", "unit": "col/tick"},
            {"name": "y_speed", "type": "number", "default": 2,
             "min": 0, "max": 16, "step": 1, "label": "Y speed", "unit": "led/tick"},
            {"name": "closer1_distance", "type": "number", "default": 85,
             "min": 1, "max": 255, "step": 1, "label": "Phase 1 (closer)", "unit": "led"},
            {"name": "x1_distance", "type": "number", "default": 112,
             "min": 1, "max": 255, "step": 1, "label": "Phase 2 (sideways)", "unit": "col"},
            {"name": "closer2_distance", "type": "number", "default": 34,
             "min": 1, "max": 255, "step": 1, "label": "Phase 3 (closer)", "unit": "led"},
            {"name": "x2_distance", "type": "number", "default": 96,
             "min": 1, "max": 255, "step": 1, "label": "Phase 4 (sideways)", "unit": "col"},
            {"name": "away_distance", "type": "number", "default": 45,
             "min": 1, "max": 255, "step": 1, "label": "Phase 5 (away)", "unit": "led"},
            {"name": "width", "type": "number", "default": 256,
             "min": 1, "max": 512, "step": 1, "label": "Display width", "unit": "col"},
        ],
        "state": ["remaining", "x_dir", "finished"],
        "actions": [],
        "apply_to_all": [],
        "per_sprite": [],
        "state_machine": {
            "states": ["closer1", "xmove1", "closer2", "xmove2", "away", "formed"],
            "initial": "closer1",
            "bodies": {
                "closer1": _y_phase("closer1_distance", "y_speed", -1, "xmove1"),
                "xmove1": _x_phase("x1_distance", "closer2", sign=1),
                "closer2": _y_phase("closer2_distance", "y_speed", -1, "xmove2"),
                "xmove2": _x_phase("x2_distance", "away", sign=-1),
                "away": _y_phase("away_distance", "y_speed", 1, "formed"),
                "formed": {
                    "enter": [{"kind": "set_state", "state": "finished", "value": _literal(True)}],
                    "step": [],
                },
            },
        },
    }


def main():
    model = build_model()
    MODEL_PATH.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n")
    result = build_behavior.build_one(MODEL_PATH)
    print(result)


if __name__ == "__main__":
    main()
