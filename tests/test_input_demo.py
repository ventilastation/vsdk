import os
import random
import sys
import time
import unittest

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

from ventilastation import api_guard
from ventilastation.app_loader import load_app
from ventilastation.catalog import discover_game_entries
from ventilastation.director import configure_runtime, director, reset_runtime, stripes


class InputDemoTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        self.runtime_director = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            stripes["tinyfont_menu.png"] = 0
            self.runtime_director.platform.sprites.stripes[0] = {
                "width": 4,
                "height": 6,
                "frames": 255,
                "palette": 0,
            }

        self.runtime_director.load_rom = fake_load_rom

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def test_is_discoverable_and_reflects_both_controller_states(self):
        entries = discover_game_entries()
        self.assertTrue(any(slug == "demos.input_demo" for _order, slug, _strip, _frame in entries))

        scene = load_app("demos.input_demo")
        self.assertEqual(scene._vs_declared_api, "vs2")
        self.assertEqual(sum(len(line.sprites) for line in scene.lines), 84)
        self.assertEqual(scene.lines[0].value, "     LRUD ABXY S B")
        self.assertEqual(scene.lines[3].value, ".=UP LETTER=HELD")

        comms = director.platform.comms
        joy2 = [director.JOY2_RIGHT | director.JOY2_DOWN | director.BUTTON2_B]
        extra = [
            director.EXTRA_JOY1_Y | director.EXTRA_JOY1_START |
            director.EXTRA_JOY2_Y | director.EXTRA_JOY2_BACK
        ]
        comms.next_joy2 = lambda: joy2[0]
        comms.next_extra = lambda: extra[0]
        comms.push_input(bytes([
            director.JOY_LEFT | director.JOY_UP | director.BUTTON_A | director.BUTTON_X
        ]))
        director.step_once()

        self.assertEqual(scene.lines[1].value, "J1:L.U. A.XY S.")
        self.assertEqual(scene.lines[2].value, "J2:.R.D .B.Y .B")


if __name__ == "__main__":
    unittest.main()
