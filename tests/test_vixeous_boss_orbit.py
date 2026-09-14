"""Tick-by-tick parity: games/vs2_examples/vixeous's generated
``BossOrbit`` Behavior (games/vs2_examples/vixeous/code/
build_boss_orbit.py) against a verbatim copy of the original hand-written
boss motion it ports (the ``boss.phase``/``boss.theta``/``boss.y`` lines
inside ``vixeous.py``'s own ``update_entities()`` -- not ``boss.x`` or
``boss.frame``, both of which stay hand-written; see
build_boss_orbit.py's own module docstring for why, including a second
real catalog mismatch (``Animate`` vs. a lone-sprite subject) found while
scoping ``frame``.

Not yet wired into the live game -- this proves the generated Behavior in
isolation, the same harness shape
tests/test_vyruss_vs2_baddie_formation.py already established.

Run: ``python3 tests/test_vixeous_boss_orbit.py``
"""

import importlib.util
import os
import random
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
sys.path.insert(0, ROOT)
sys.modules.setdefault("uos", os)
sys.modules.setdefault("urandom", random)
if "utime" not in sys.modules:
    class _Utime:
        @staticmethod
        def ticks_ms():
            return int(time.time() * 1000)

        @staticmethod
        def ticks_add(value, delta):
            return value + delta

        @staticmethod
        def ticks_diff(end, start):
            return end - start

    sys.modules["utime"] = _Utime

import vs2  # noqa: E402
from ventilastation import api_guard  # noqa: E402
from ventilastation.director import configure_runtime, director, reset_runtime, stripes  # noqa: E402

from tools.vs2_behavior_gen import generator  # noqa: E402
from games.vs2_examples.vixeous.code.build_boss_orbit import build_model  # noqa: E402

BOSS_STOP_Y = 107
CYCLE_TICKS = 192
THETA_SPEED = 2
WIDTH = 256


class _RefBoss:
    """A verbatim copy of the original per-tick boss motion this Behavior
    ports (excluding boss.x's own camera-dependent reprojection and
    boss.frame, neither of which BossOrbit ports -- see
    build_boss_orbit.py's own module docstring)."""

    def __init__(self, theta, phase, y):
        self.theta = theta
        self.phase = phase
        self.y = y

    def step(self):
        self.phase = (self.phase + 1) % CYCLE_TICKS
        self.theta = (
            self.theta + (THETA_SPEED if self.phase < CYCLE_TICKS // 2 else -THETA_SPEED)
        ) % WIDTH
        if self.y > BOSS_STOP_Y:
            self.y -= 1


class BossOrbitParityTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="vixeous_boss_orbit_test_")
        reset_runtime()
        api_guard.reset()
        self.runtime = configure_runtime("headless")
        stripes.clear()
        stripes["boss.png"] = 0
        self.runtime.platform.sprites.stripes[0] = {
            "width": 32, "height": 32, "frames": 2, "palette": 0,
        }
        api_guard.begin_app("games.test_vixeous_boss_orbit", "vs2")

        model = build_model()
        path = Path(self.tmpdir) / "boss_orbit.py"
        generator.write_behavior_file(model, path)
        module_name = "vixeous_boss_orbit_test_module"
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.BossOrbit = module.BossOrbit

    def tearDown(self):
        reset_runtime()
        api_guard.reset()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _generated_trajectory(self, theta0, phase0, y0, ticks):
        cls = self.BossOrbit

        class Game(vs2.Scene):
            idle_timeout = None
            back_button = False

            def build(self):
                self.world = self.layer("world", projection=vs2.TUNNEL)
                self.boss = self.world.sprite("boss.png", y=y0)
                # behave() primes every declared state name to 0 at attach
                # time (see apps/micropython/vs2/__init__.py's
                # _prime_sprite_state) -- setting theta/phase before this
                # would just get overwritten; set them after instead.
                self.boss.behave(cls())
                self.boss.theta = theta0
                self.boss.phase = phase0

            def update(self):
                pass

        game = Game()
        director.push(game)
        behavior = game.boss.behavior(cls)
        trajectory = []
        for _ in range(ticks):
            behavior.step_one(game.boss)
            trajectory.append((game.boss.theta, game.boss.phase, game.boss.y))
        return trajectory

    def _reference_trajectory(self, theta0, phase0, y0, ticks):
        ref = _RefBoss(theta0, phase0, y0)
        trajectory = []
        for _ in range(ticks):
            ref.step()
            trajectory.append((ref.theta, ref.phase, ref.y))
        return trajectory

    def test_matches_the_original_over_a_full_cycle_and_a_half(self):
        ticks = CYCLE_TICKS + CYCLE_TICKS // 2
        expected = self._reference_trajectory(theta0=40, phase0=0, y0=143, ticks=ticks)
        actual = self._generated_trajectory(theta0=40, phase0=0, y0=143, ticks=ticks)
        self.assertEqual(actual, expected)

    def test_matches_the_original_when_theta_wraps_past_the_seam(self):
        expected = self._reference_trajectory(theta0=254, phase0=0, y0=143, ticks=10)
        actual = self._generated_trajectory(theta0=254, phase0=0, y0=143, ticks=10)
        self.assertEqual(actual, expected)

    def test_y_stops_exactly_at_stop_y_and_no_further(self):
        expected = self._reference_trajectory(theta0=0, phase0=0, y0=BOSS_STOP_Y + 3, ticks=10)
        actual = self._generated_trajectory(theta0=0, phase0=0, y0=BOSS_STOP_Y + 3, ticks=10)
        self.assertEqual(actual, expected)
        self.assertEqual(actual[-1][2], BOSS_STOP_Y)


if __name__ == "__main__":
    unittest.main()
