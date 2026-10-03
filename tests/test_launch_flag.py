"""``--game=<slug>`` starts a game straight away (emulator/emu.py --game)."""

import io
import os
import random
import sys
import time
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
from ventilastation.app_loader import launch_requested_game, requested_game
from ventilastation.director import configure_runtime, director, reset_runtime, stripes


class RequestedGameTests(unittest.TestCase):
    def test_both_spellings_and_other_arguments(self):
        self.assertEqual(requested_game(["main.py", "--platform=desktop", "--game=a.b"]), "a.b")
        self.assertEqual(requested_game(["main.py", "--game", "a.b"]), "a.b")
        self.assertIsNone(requested_game(["main.py", "--platform=desktop"]))
        self.assertIsNone(requested_game(["main.py", "--game"]))
        self.assertIsNone(requested_game(["main.py", "--game="]))
        self.assertIsNone(requested_game([]))


class LaunchTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        runtime_director = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            for index, name in enumerate(("ship.png", "enemy.png", "trench.png",
                                          "numerals.png", "steel8x8.png")):
                stripes[name] = index
                runtime_director.platform.sprites.stripes[index] = {
                    "width": 16, "height": 16, "frames": 256 if name == "steel8x8.png" else 6,
                    "palette": 0, "glyphs": "0123456789 *" if name == "numerals.png" else None,
                }

        runtime_director.load_rom = fake_load_rom

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def test_the_named_game_starts_over_the_scene_below(self):
        from games.demos.tutorial_game.code.tutorial_game import Title

        scene = launch_requested_game(["main.py", "--game=demos.tutorial_game"])
        self.assertIsInstance(scene, Title)
        self.assertIs(director.scene_stack[-1], scene)

    def test_no_argument_launches_nothing(self):
        self.assertIsNone(launch_requested_game(["main.py", "--platform=desktop"]))
        self.assertEqual(len(director.scene_stack), 0)

    def test_an_unknown_game_is_reported_and_ignored(self):
        output = io.StringIO()
        with redirect_stdout(output):
            scene = launch_requested_game(["main.py", "--game=nobody.nothing"])
        self.assertIsNone(scene)
        self.assertIn("could not start 'nobody.nothing'", output.getvalue())
        self.assertEqual(len(director.scene_stack), 0)


if __name__ == "__main__":
    unittest.main()
