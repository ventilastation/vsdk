#!/usr/bin/env python3
"""Builds ``boss_orbit.vs2behavior.json`` and regenerates ``boss_orbit.py``
from it.

Run from the repo root: ``python3
games/vs2_examples/vixeous/code/build_boss_orbit.py``

Ports part of ``vixeous.py``'s own hand-written boss motion (inside
``update_entities()``) to a real, block-representable Behavior, using the
``binary_op`` expression kind added alongside this task's other work.

**Why the boss, not the enemies pool.** Scoping "port vixeous to blocks"
found the ``enemies`` pool's own per-tick phase/theta oscillation
(`enemy.phase`/`enemy.theta`, the exact same shape this Behavior covers
for the boss) looks portable at first glance, but isn't, for a real
structural reason discovered while trying: ``vixeous_scene.vs2model.json``
already declares ``self.enemies.var('phase', ...)``/``.var('theta', ...)``
(``SpritePool.var()``) for those exact names, and a Behavior's own
``state = (...)`` tuple *cannot* re-declare a name a pool already owns --
``apps/micropython/vs2/__init__.py``'s ``_prime_pool_state`` raises
``StateConflictError`` at attach time precisely to protect the
zero-allocation guarantee priming exists for. Fixing this for real would
mean either extending the block schema to let a Behavior read/write a
field it does not itself own and prime (a real, un-built capability), or
removing the pool's own ``.var()`` declarations in favour of the
Behavior's (losing the kinds-table/live-tune editing those provide) --
neither is a small change, and forcing either through under time
pressure is exactly the "don't force a mismatched shape" mistake this
whole porting effort has repeatedly avoided elsewhere. Documented, not
solved, here and in the handoff doc.

The boss is a *lone sprite* (``self.boss = self.world.sprite(...)``, no
pool, no ``.var()`` at all), so this exact collision does not apply to
it -- a real, if smaller, still-portable piece.

**What this ports, and what stays hand-written.** The original, inside
``update_entities()``::

    self.boss.phase = (self.boss.phase + 1) % 192
    self.boss.theta = (self.boss.theta + (2 if self.boss.phase < 96 else -2)) % vs2.display.width
    if self.boss.y > BOSS_STOP_Y:
        self.boss.y -= 1
    self.boss.x = screen_x(self.boss.theta, self.camera_theta, self.boss.width)
    self.boss.frame = (self.boss.phase // 8) & 1

This Behavior owns theta/phase motion (the per-sprite ``theta``/``phase``
fields below) and the approach toward ``BOSS_STOP_Y`` (a plain bounded
``y`` accumulate). ``self.boss.x`` stays hand-written for the reason
every other sprite's own ``x`` line in ``update_entities()`` already
does: the camera rotates independently every tick and nothing in the
Behavior catalog knows about that reprojection.

**``self.boss.frame`` also stays hand-written -- a second, real,
previously-undiscovered catalog mismatch found while building this.**
``(phase // 8) & 1`` with `phase` wrapping every 192 ticks is exactly the
square wave the real ``Animate(first=0, last=1, ticks=8, mode="loop")``
action already produces -- the natural, sanctioned tool, tried first
here. It does not work for a *lone-sprite* subject, though: ``Animate``'s
clock is explicitly pool-shaped (its own docstring: "every live sprite
driven by one Animate instance shares one clock... advanced exactly once
per :meth:`run` call... :meth:`run_one` never advances the clock"), and
the generator's own ``apply_to_all`` rendering always calls ``run_one()``
for ``subject_kind="sprite"`` (``tools/vs2_behavior_gen/generator.py``'s
``_render_apply_to_all``: ``method = "run" if pool else "run_one"``) --
correct for every *other* Action (``Move``/``MoveTo``/``Collide``, whose
``run_one()`` is a complete, self-sufficient single-sprite operation with
no shared clock), wrong specifically for ``Animate``. Verified directly:
attaching ``Animate`` this way to a lone sprite leaves ``frame`` frozen
at ``first`` forever, silently -- no exception, no warning, `just never
changes`. Nothing in this port works around that; it is a genuine gap in
how the *real* ``Animate`` class composes with a lone-sprite subject, not
specific to the block schema, and belongs on the same list as
``vixeous.py``'s own already-documented mismatches (Patrolling's bipolar
wave, ``Animated.bank`` rejecting a ``Var`` binding, Projectile's
unconditional despawn).

**Not yet wired into the live game.** This builds and would need its own
tick-by-tick parity test (mirroring
``tests/test_vyruss_vs2_baddie_formation.py``'s approach) plus attaching
in an ``on_build_N`` hook and trimming the corresponding lines out of
``update_entities()`` -- a smaller version of the same integration
``vyruss_vs2``'s own ``BaddieFormation`` needed, left for a follow-up
pass rather than rushed alongside discovering the design.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.vs2_behavior_gen import build_behavior  # noqa: E402

CODE_DIR = Path(__file__).resolve().parent
MODEL_PATH = CODE_DIR / "boss_orbit.vs2behavior.json"


def _literal(value):
    return {"kind": "literal", "value": value}


def _param(name):
    return {"kind": "param", "name": name}


def _state(name):
    return {"kind": "state", "name": name}


def _binop(op, left, right):
    return {"kind": "binary_op", "op": op, "left": left, "right": right}


def build_model():
    return {
        "version": 1,
        "class_name": "BossOrbit",
        "subject_kind": "sprite",
        "params": [
            {"name": "cycle_ticks", "type": "number", "default": 192,
             "min": 2, "max": 1024, "step": 2, "label": "Orbit cycle", "unit": "tick"},
            {"name": "theta_speed", "type": "number", "default": 2,
             "min": 0, "max": 16, "step": 1, "label": "Theta speed", "unit": "col/tick"},
            {"name": "width", "type": "number", "default": 256,
             "min": 1, "max": 512, "step": 1, "label": "Display width", "unit": "col"},
            {"name": "stop_y", "type": "number", "default": 107,
             "min": 0, "max": 255, "step": 1, "label": "Approach stop", "unit": "led"},
        ],
        "state": ["theta", "phase"],
        "actions": [],
        "apply_to_all": [],
        "per_sprite": [
            {"kind": "set_state", "state": "phase",
             "value": _binop("%", _binop("+", _state("phase"), _literal(1)), _param("cycle_ticks"))},
            {"kind": "if_else",
             "condition": {"kind": "compare", "op": "<", "left": _state("phase"),
                            "right": _binop("//", _param("cycle_ticks"), _literal(2))},
             "then": [{"kind": "set_state", "state": "theta",
                       "value": _binop("%", _binop("+", _state("theta"), _param("theta_speed")),
                                       _param("width"))}],
             "else": [{"kind": "set_state", "state": "theta",
                       "value": _binop("%", _binop("-", _state("theta"), _param("theta_speed")),
                                       _param("width"))}]},
            {"kind": "if_else",
             "condition": {"kind": "compare", "op": ">", "left": _state("y"),
                            "right": _param("stop_y")},
             "then": [{"kind": "accumulate", "state": "y", "amount": _literal(-1)}],
             "else": []},
        ],
    }


def main():
    model = build_model()
    MODEL_PATH.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n")
    result = build_behavior.build_one(MODEL_PATH)
    print(result)


if __name__ == "__main__":
    main()
