#!/usr/bin/env python3
"""Builds ``enemy_states.vs2behavior.json`` and regenerates
``enemy_states.py`` from it.

Run from the repo root: ``python3
games/vs2_examples/vasura_states_demo/code/build_enemy_states.py``

This is the T17 Phase 2 "state hats" proving case, in miniature, against
real game logic: a shrunk, original recreation of
``games/vsjam-may25/vasura_espacial``'s own hand-rolled state machine
(``vasura_scripts/estado.py``'s ``Estado`` subclasses --
``Deshabilitado``/``Explotando``/``Vulnerable``/``Bajando``/
``ChillerBajando``/``Orbitando``/``Persiguiendo``/``YendoDerecho``/
``BajandoEnEspiral``, one ``Estado`` per real enemy state, dispatched by
``entities/enemigos/enemigo.py``), authored entirely through
``tools/vs2_behavior_gen``'s state-hat schema instead of that hand-rolled
dispatch. This is a small, focused *recreation of the shape*, not a port
of the whole ~1815-line game (that is a different card's job; see this
task's report) -- four of the real game's nine named states, enough to
show a real multi-state cycle with two ``hold()``-based timed transitions
and one ``Collide``-driven interrupt.

**The cycle, and how it maps onto the real game's own state graph.**

- ``orbiting`` <-> the real ``Orbitando``: holds for ``orbit_ticks`` ticks
  (``enter_orbiting``'s own ``hold()``, mirroring ``Orbitando.on_enter``'s
  ``self.frames_left = 128``), then hands off to ``chiller_falling``.
  (The real ``Orbitando.step`` also drifts the sprite sideways every
  tick -- dropped here: this schema's per-sprite expression vocabulary has
  no addition operator, only ``accumulate``'s own ``+=``, which is
  deliberately restricted to *declared* per-sprite state fields, not the
  built-in ``x``/``y`` Move/MoveTo already own -- see model.py's own
  ``set_state`` docstring comment. Not needed for what this proving case
  demonstrates.)
- ``chiller_falling`` <-> the real ``ChillerBajando``: holds for
  ``chiller_ticks`` ticks (mirroring ``ChillerBajando.on_enter``'s
  ``self.frames_left = 40``), then hands off to ``falling``.
- ``falling`` <-> the real ``Bajando``: descends at ``fall_speed`` every
  tick, transitioning to ``exploding`` the tick it reaches ``ground_y``
  (mirroring ``Bajando.step``'s own ground check).
- ``exploding`` <-> the real ``Explotando``: plays a sound, spawns into
  the declared explosion pool and calls ``on_death``, all on entry, then
  despawns on its own next tick (mirroring ``Explotando.on_enter``'s sound
  + disable, and its ``step`` eventually calling ``self.entidad.morir()``
  -- simplified to "despawn one tick later" rather than counting real
  animation frames, since this demo's explosion pool drives its own frame
  animation via the real, hand-written ``Transient`` Behavior instead;
  see ``vasura_states_demo.py``).
- Every one of ``orbiting``/``chiller_falling``/``falling`` also checks
  the bound ``Collide`` action every tick and jumps straight to
  ``exploding`` on a hit -- mirroring the real ``Vulnerable.step``'s own
  "check collision with a bullet, and with the player ship" (trimmed here
  to just the bullet pool, this demo's whole "player" surface).

**One deliberate departure from the real game's own transition graph,
flagged plainly.** The real ``ChillerBajando.step`` returns to
``Orbitando`` after its 40-tick timer (a back-and-forth cycle that never
terminates on its own); this demo instead sends ``chiller_falling`` on to
``falling`` -- matching this task's own dispatch card, which names exactly
this cycle ("Orbitando -> ChillerBajando -> Bajando") as the intended
demonstration shape. A single forward-flowing lifecycle (spawn -> orbit ->
chiller-fall -> fall -> explode -> despawn) is also easier to drive
deterministically from a test than a cycle with no natural end.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.vs2_behavior_gen import build_behavior  # noqa: E402

CODE_DIR = Path(__file__).resolve().parent
MODEL_PATH = CODE_DIR / "enemy_states.vs2behavior.json"


def _literal(value):
    return {"kind": "literal", "value": value}


def _param(name):
    return {"kind": "param", "name": name}


def _state(name):
    return {"kind": "state", "name": name}


def _check_for_a_hit(then_name):
    """"if the bound Collide action found a bullet this tick, jump
    straight to <then_name>" -- shared by all three vulnerable states."""
    return {"kind": "if_action", "bind": "hit",
            "then": [{"kind": "goto_state", "name": then_name}], "else": []}


def build_model():
    return {
        "version": 1,
        "class_name": "EnemyStates",
        "subject_kind": "pool",
        "params": [
            {"name": "hits", "type": "pool", "default": None, "label": "Player shots"},
            {"name": "orbit_ticks", "type": "number", "default": 80,
             "min": 1, "max": 255, "step": 1, "label": "Orbit duration", "unit": "tick"},
            {"name": "chiller_ticks", "type": "number", "default": 30,
             "min": 1, "max": 255, "step": 1, "label": "Chiller-fall duration", "unit": "tick"},
            {"name": "fall_speed", "type": "number", "default": 2,
             "min": 0, "max": 8, "step": 0.25, "label": "Fall speed", "unit": "led/tick"},
            {"name": "ground_y", "type": "number", "default": 100,
             "min": 0, "max": 255, "step": 1, "label": "Ground", "unit": "led"},
            {"name": "explosion", "type": "pool", "default": None, "label": "Explosion pool"},
            {"name": "sound", "type": "sound", "default": None, "label": "Explosion sound"},
            {"name": "on_death", "type": "callback", "default": None, "label": "On death"},
        ],
        "state": [],
        "actions": [
            {"bind": "hit", "action_class": "Collide", "args": {"targets": _param("hits")}},
        ],
        "apply_to_all": [],
        "per_sprite": [],
        "state_machine": {
            "states": ["orbiting", "chiller_falling", "falling", "exploding"],
            "initial": "orbiting",
            "bodies": {
                "orbiting": {
                    "enter": [
                        {"kind": "hold", "ticks": _param("orbit_ticks"), "then": "chiller_falling"},
                    ],
                    "step": [
                        _check_for_a_hit("exploding"),
                    ],
                },
                "chiller_falling": {
                    "enter": [
                        {"kind": "hold", "ticks": _param("chiller_ticks"), "then": "falling"},
                    ],
                    "step": [
                        _check_for_a_hit("exploding"),
                    ],
                },
                "falling": {
                    "step": [
                        {"kind": "accumulate", "state": "y", "amount": _param("fall_speed")},
                        {"kind": "if_else",
                         "condition": {"kind": "compare", "op": ">=",
                                        "left": _state("y"), "right": _param("ground_y")},
                         "then": [{"kind": "goto_state", "name": "exploding"}],
                         "else": [_check_for_a_hit("exploding")]},
                    ],
                },
                "exploding": {
                    "enter": [
                        {"kind": "play_sound", "name": "sound"},
                        {"kind": "spawn", "pool": "explosion", "x": _state("x"), "y": _state("y")},
                        {"kind": "call_callback", "name": "on_death", "args": []},
                    ],
                    "step": [
                        {"kind": "despawn"},
                    ],
                },
            },
        },
    }


def main():
    model = build_model()
    MODEL_PATH.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n")
    # Delegate the actual JSON -> .py write to the generic CLI's own
    # build_one() -- the same path tools/vs2_behavior_gen/build_behavior.py
    # invoked directly from a shell would take, so this script's only real
    # job is constructing the model dict (this phase's stand-in for a
    # Blockly panel -- see build_behavior.py's own docstring).
    result = build_behavior.build_one(MODEL_PATH)
    print(result)


if __name__ == "__main__":
    main()
