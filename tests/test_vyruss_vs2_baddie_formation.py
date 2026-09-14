"""Tick-by-tick parity: games/vs2_examples/vyruss_vs2's generated
``BaddieFormation`` Behavior (games/vs2_examples/vyruss_vs2/code/
build_baddie_formation.py) against ``_RefTravelCloser``/``_RefTravelX``/
``_RefTravelAway`` below -- a verbatim, self-contained copy of the
original hand-written queue those classes replaced in vyruss_vs2.py
itself (see build_baddie_formation.py's own module docstring for exactly
what is and is not ported; the sixth phase, ``TravelTo``, stays
hand-written in vyruss_vs2.py, not attempted here or by BaddieFormation).
Kept here rather than imported from production code specifically so this
regression test still has an independent oracle once vyruss_vs2.py no
longer calls them for anything.

Runs the generated Behavior standalone against a real
vs2.Scene/SpritePool, the same harness shape
tests/test_vs2_behavior_gen_generator.py's own
GeneratedProjectileBehaviorTests uses.

Run: ``python3 tests/test_vyruss_vs2_baddie_formation.py``
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
from games.vs2_examples.vyruss_vs2.code.build_baddie_formation import build_model  # noqa: E402
from games.vs2_examples.vyruss_vs2.code.vyruss_vs2 import X_SPEED, Y_SPEED  # noqa: E402


class _ReferenceSprite:
    """Just enough of a real vs2.Sprite for _RefTravelCloser/_RefTravelX/
    _RefTravelAway's own step()/finished() (they only ever touch .x/.y)."""

    def __init__(self, x, y):
        self.x = x
        self.y = y


# -- The original TravelBy/TravelX/TravelCloser/TravelAway classes, kept
# here verbatim as this test's own reference oracle, now that
# BaddieFormation has replaced their use in vyruss_vs2.py itself (see that
# module's own build_baddie_formation.py docstring). Not imported from
# production code on purpose: once nothing in the live game calls them,
# leaving them there would be dead code, and this test needs an
# independent, unmodified copy of the *original* behaviour to compare
# against regardless of what vyruss_vs2.py itself does from here on.
class _RefTravelBy:
    def __init__(self, count):
        self.remaining = abs(count)
        self.direction = -1 if count < 0 else 1

    def finished(self, _sprite):
        return self.remaining <= 0


class _RefTravelX(_RefTravelBy):
    def step(self, sprite):
        distance = min(X_SPEED, self.remaining)
        sprite.x = (sprite.x + distance * self.direction) % vs2.display.width
        self.remaining -= distance


class _RefTravelCloser(_RefTravelBy):
    def step(self, sprite):
        distance = min(Y_SPEED, self.remaining)
        sprite.y -= distance
        self.remaining -= distance


class _RefTravelAway(_RefTravelBy):
    def step(self, sprite):
        distance = min(Y_SPEED, self.remaining)
        sprite.y += distance
        self.remaining -= distance


def _original_trajectory(x0, y0, odd):
    """Replicates update_one_baddie()'s own queue-popping loop
    (vyruss_vs2.py) against the first five phases only -- TravelTo (the
    sixth) is excluded, matching what BaddieFormation itself ports. Stops
    the tick after the fifth phase finishes, mirroring "formed"."""
    sprite = _ReferenceSprite(x0, y0)
    if odd:
        movements = [_RefTravelCloser(85), _RefTravelX(112), _RefTravelCloser(34),
                     _RefTravelX(-96), _RefTravelAway(45)]
    else:
        movements = [_RefTravelCloser(85), _RefTravelX(-112), _RefTravelCloser(34),
                     _RefTravelX(96), _RefTravelAway(45)]
    trajectory = []
    while movements:
        movement = movements[0]
        movement.step(sprite)
        if movement.finished(sprite):
            movements.pop(0)
        trajectory.append((sprite.x, sprite.y))
    return trajectory


class BaddieFormationParityTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="vyruss_baddie_formation_test_")
        reset_runtime()
        api_guard.reset()
        self.runtime = configure_runtime("headless")
        stripes.clear()
        stripes["galaga.png"] = 0
        self.runtime.platform.sprites.stripes[0] = {
            "width": 16, "height": 16, "frames": 12, "palette": 0,
        }
        api_guard.begin_app("games.test_vyruss_vs2_baddie_formation", "vs2")

        model = build_model()
        path = Path(self.tmpdir) / "baddie_formation.py"
        generator.write_behavior_file(model, path)
        module_name = "vyruss_baddie_formation_test_module"
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.BaddieFormation = module.BaddieFormation

        self.assertEqual(X_SPEED, 3, "the model's own x_speed default assumes this")
        self.assertEqual(Y_SPEED, 2, "the model's own y_speed default assumes this")

    def tearDown(self):
        reset_runtime()
        api_guard.reset()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_game(self, x0, y0, odd):
        model_cls = self.BaddieFormation

        class Game(vs2.Scene):
            idle_timeout = None
            back_button = False

            def build(self):
                self.world = self.layer("world", projection=vs2.TUNNEL)
                self.baddies = self.world.sprite_pool("galaga.png", count=1)
                self.baddies.behave(model_cls(width=vs2.display.width))
                sprite = self.baddies.spawn(x0, y0)
                sprite.x_dir = 1 if odd else -1

            def update(self):
                pass

        game = Game()
        director.push(game)
        behavior = game.baddies.behavior(model_cls)
        return game, behavior

    def _generated_trajectory(self, x0, y0, odd):
        game, behavior = self._build_game(x0, y0, odd)
        trajectory = []
        # Generous safety cap -- the real choreography finishes in ~153
        # ticks (ceil(85/2)+ceil(112/3)+ceil(34/2)+ceil(96/3)+ceil(45/2));
        # a bug that never reaches "formed" fails loudly instead of hanging.
        for _ in range(500):
            behavior.step(game.baddies)
            sprite = game.baddies._live[0]
            trajectory.append((sprite.x, sprite.y))
            if sprite.formation_done:
                break
        else:
            self.fail("BaddieFormation never reached 'formed' within 500 ticks")
        return trajectory

    def _assert_matches_original(self, x0, y0, odd):
        expected = _original_trajectory(x0, y0, odd)
        actual = self._generated_trajectory(x0, y0, odd)
        self.assertEqual(
            actual, expected,
            "BaddieFormation's trajectory diverges from the original "
            "TravelCloser/TravelX/TravelAway queue (odd=%r, start=(%r, %r))"
            % (odd, x0, y0))

    def test_matches_the_original_queue_odd_baddie(self):
        # base_x=120, odd offset +16 -- a real starting column from
        # add_baddie()'s own bases/odd table.
        self._assert_matches_original(136, 154, odd=True)

    def test_matches_the_original_queue_even_baddie(self):
        self._assert_matches_original(104, 154, odd=False)

    def test_matches_the_original_when_the_x_phase_wraps_past_the_seam(self):
        """base_x=248 (the fourth entry in add_baddie()'s own bases table)
        plus phase 2's +112 genuinely crosses the 0/256 seam -- the case
        build_baddie_formation.py's own docstring calls out by name."""
        self._assert_matches_original(248 + 16, 154, odd=True)
        self._assert_matches_original(248 - 16, 154, odd=False)

    def test_finishes_with_formation_done_true_and_no_further_movement(self):
        expected = _original_trajectory(136, 154, odd=True)
        game, behavior = self._build_game(136, 154, odd=True)
        for _ in range(len(expected)):
            behavior.step(game.baddies)
        sprite = game.baddies._live[0]
        self.assertTrue(sprite.formation_done)
        # One more step from "formed" must not move the sprite again.
        before = (sprite.x, sprite.y)
        behavior.step(game.baddies)
        self.assertEqual((sprite.x, sprite.y), before)


class AttackCycleParityTests(unittest.TestCase):
    """attack_closer/attack_away -- update_attacking()'s own runtime
    reassignment, ported alongside the entrance phases. A separate class
    from BaddieFormationParityTests: these tests force_state() straight
    into the attack cycle rather than running the entrance choreography
    first, since the two are independent once a sprite exists."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="vyruss_attack_cycle_test_")
        reset_runtime()
        api_guard.reset()
        self.runtime = configure_runtime("headless")
        stripes.clear()
        stripes["galaga.png"] = 0
        self.runtime.platform.sprites.stripes[0] = {
            "width": 16, "height": 16, "frames": 12, "palette": 0,
        }
        api_guard.begin_app("games.test_vyruss_attack_cycle", "vs2")

        model = build_model()
        path = Path(self.tmpdir) / "baddie_formation_attack.py"
        generator.write_behavior_file(model, path)
        spec = importlib.util.spec_from_file_location(
            "vyruss_attack_cycle_test_module", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.BaddieFormation = module.BaddieFormation

    def tearDown(self):
        reset_runtime()
        api_guard.reset()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_attacking_sprite(self, y0, distance):
        model_cls = self.BaddieFormation

        class Game(vs2.Scene):
            idle_timeout = None
            back_button = False

            def build(self):
                self.world = self.layer("world", projection=vs2.TUNNEL)
                self.baddies = self.world.sprite_pool("galaga.png", count=1)
                self.baddies.behave(model_cls(width=vs2.display.width))
                self.sprite = self.baddies.spawn(0, y0)

            def update(self):
                pass

        game = Game()
        director.push(game)
        behavior = game.baddies.behavior(model_cls)
        # update_attacking()'s own sequence: set attack_distance, then
        # force_state -- see vyruss_vs2.py's own update_attacking().
        game.sprite.attack_distance = distance
        behavior.force_state(game.sprite, "attack_closer")
        return game, behavior

    def test_matches_the_original_travelcloser_then_travelaway(self):
        """The original: baddie.movements = [TravelCloser(distance),
        TravelAway(distance)] -- symmetric, same distance both ways."""
        distance = 37
        y0 = 90
        game, behavior = self._build_attacking_sprite(y0, distance)

        ref_sprite = _ReferenceSprite(0, y0)
        ref_movements = [_RefTravelCloser(distance), _RefTravelAway(distance)]
        expected = []
        while ref_movements:
            movement = ref_movements[0]
            movement.step(ref_sprite)
            if movement.finished(ref_sprite):
                ref_movements.pop(0)
            expected.append(ref_sprite.y)

        actual = []
        for _ in range(len(expected)):
            behavior.step(game.baddies)
            actual.append(game.sprite.y)
        self.assertEqual(actual, expected)
        # Symmetric distance: ends exactly where it started.
        self.assertEqual(game.sprite.y, y0)

    def test_in_attack_run_true_during_the_cycle_false_after(self):
        game, behavior = self._build_attacking_sprite(90, distance=10)
        self.assertTrue(game.sprite.in_attack_run)
        # distance=10 at Y_SPEED=2: 5 ticks closer, 5 ticks away = 10 ticks.
        for _ in range(9):
            behavior.step(game.baddies)
            self.assertTrue(game.sprite.in_attack_run, "cycle ended too early")
        behavior.step(game.baddies)
        self.assertFalse(game.sprite.in_attack_run)

    def test_does_not_disturb_formation_done_or_finished_semantics(self):
        """The attack cycle's own in_attack_run signal is deliberately
        separate from formation_done -- see build_baddie_formation.py's
        own module docstring. A baddie already through formation (already
        formation_done=True) stays that way through an attack cycle."""
        game, behavior = self._build_attacking_sprite(90, distance=6)
        game.sprite.formation_done = True
        for _ in range(6):
            behavior.step(game.baddies)
        self.assertTrue(game.sprite.formation_done)
        self.assertFalse(game.sprite.in_attack_run)


if __name__ == "__main__":
    unittest.main()
