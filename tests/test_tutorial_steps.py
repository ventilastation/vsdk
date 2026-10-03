"""The complete file at the end of each tutorial chapter (docs/vs2/tutorial/steps)
must run, and do what its chapter says. The tutorial pages include these files, so
a reader can compare theirs with a known-good one at every stage."""

import importlib.util
import os
import random
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEPS = os.path.join(ROOT, "docs", "vs2", "tutorial", "steps")
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
sys.path.insert(0, ROOT)
sys.modules.setdefault("uos", os)
sys.modules.setdefault("urandom", random)
if "utime" not in sys.modules:
    class _Utime:
        ticks_ms = staticmethod(lambda: int(time.time() * 1000))
        ticks_add = staticmethod(lambda value, delta: value + delta)
        ticks_diff = staticmethod(lambda end, start: end - start)
        sleep_ms = staticmethod(lambda ms: time.sleep(ms / 1000.0))

    sys.modules["utime"] = _Utime

from ventilastation import api_guard
from ventilastation.director import configure_runtime, director, reset_runtime, stripes

# name: (frame width, height, frames, glyphs), as in the game's __images__.yaml
STRIPS = {
    "ship.png": (18, 18, 3, None),
    "enemy.png": (14, 11, 6, None),
    "trench.png": (16, 16, 8, None),
    "numerals.png": (4, 5, 12, "0123456789 *"),
}


class TutorialStepTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        runtime_director = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            for index, (name, (width, height, frames, glyphs)) in enumerate(STRIPS.items()):
                stripes[name] = index
                runtime_director.platform.sprites.stripes[index] = {
                    "width": width, "height": height, "frames": frames,
                    "palette": 0, "glyphs": glyphs,
                }

        runtime_director.load_rom = fake_load_rom
        api_guard.begin_app("docs.tutorial_step", "vs2")

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def start(self, filename):
        path = os.path.join(STEPS, filename)
        spec = importlib.util.spec_from_file_location("tutorial_" + filename[:-3], path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        scene = module.main()
        scene._vs_api_slug = "docs.tutorial_step"
        scene._vs_declared_api = "vs2"
        director.push(scene)
        return scene

    def step(self, buttons=0, times=1):
        for _ in range(times):
            director.platform.comms.push_input(bytes([buttons]))
            director.step_once()

    def test_every_step_file_is_here(self):
        self.assertEqual(sorted(name for name in os.listdir(STEPS) if name.endswith(".py")), [
            "step1_first_game.py", "step2_display.py", "step3_sprites.py",
            "step4_pools.py", "step5_tilemaps.py"])

    def test_step1_steers_the_ship(self):
        game = self.start("step1_first_game.py")
        self.assertEqual(game.ship.x, 128)
        self.step(director.JOY_LEFT, 10)
        self.assertEqual(game.ship.x, 118)
        self.step(director.JOY_RIGHT, 20)
        self.assertEqual(game.ship.x, 138)

    def test_step2_wraps_the_ship_round_the_disc(self):
        game = self.start("step2_display.py")
        game.ship.x = 0
        self.step(director.JOY_LEFT)
        self.assertEqual(game.ship.x, 255)
        self.step(director.JOY_RIGHT)
        self.assertEqual(game.ship.x, 0)

    def test_step3_leans_the_ship_into_a_turn(self):
        game = self.start("step3_sprites.py")
        self.assertEqual(game.ship.frame, 0)
        self.step(director.JOY_LEFT)
        self.assertEqual(game.ship.frame, 1)
        self.step(director.JOY_RIGHT)
        self.assertEqual(game.ship.frame, 2)
        self.step(0)
        self.assertEqual(game.ship.frame, 0)
        before = game.ship.x
        self.step(director.JOY_LEFT | director.JOY_RIGHT)       # they cancel out
        self.assertEqual((game.ship.x, game.ship.frame), (before, 0))

    def test_step4_enemies_fly_down_the_tunnel_and_are_retired(self):
        game = self.start("step4_pools.py")
        self.assertEqual(len(game.enemies), 5)
        start_y = [enemy.y for enemy in game.enemies]
        self.step(0, 10)
        self.assertTrue(all(enemy.y < y for enemy, y in zip(game.enemies, start_y)))
        self.step(0, 400)
        self.assertEqual(len(game.enemies), 0)

    def test_step5_scrolls_the_trench_and_scores_what_gets_past(self):
        game = self.start("step5_tilemaps.py")
        self.assertEqual(game.score_label.text, "00000")
        self.assertEqual(game.ground[1, 2], 3)       # WINDOWS, the pattern's lit tile
        views = set()
        for _ in range(400):
            self.step(0)
            views.add(game.ground.view_y)
            self.assertLess(game.ground.view_y, 96)
        self.assertEqual(views, set(range(96)))
        self.assertEqual(game.score, 50)
        self.assertEqual(game.score_label.text, "00050")


if __name__ == "__main__":
    unittest.main()
