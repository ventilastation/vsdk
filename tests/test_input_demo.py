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
        self.assertEqual(len(scene.hud.sprites), 0)
        self.assertEqual(len(scene.hud.tilemaps), 1)
        self.assertEqual(len(scene.text_frames), 63)
        self.assertIs(scene.text.frames, scene.text_frames)
        self.assertEqual(scene.line_values[0], "     LRUD ABXY S B")
        self.assertEqual(scene.text.y, 0)
        import vs2
        payload = vs2.export_scene_payload(scene)
        self.assertEqual(payload[4], 2)  # tilemap-capable VS2 payload
        self.assertEqual(payload[7], 1)

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

        self.assertEqual(scene.line_values[1], "J1:L.U. A.XY S.")
        self.assertEqual(scene.line_values[2], "J2:.R.D .B.Y .B")
        # Tilemap columns are stored in the clockwise order used by sprites.
        row = 1 * 21
        self.assertEqual(scene.text_frames[row + 20], ord("J"))
        self.assertEqual(scene.text_frames[row + 19], ord("1"))
        # The ROM menu strip keeps white ASCII at 0..127 and red at 128..254.
        self.assertEqual(scene.text_frames[row + 17], ord("L") | 0x80)
        self.assertEqual(scene.text_frames[row + 16], ord("."))
        self.assertEqual(scene.text_frames[row + 12], ord("A") | 0x80)
        joy2_row = 2 * 21
        self.assertEqual(scene.text_frames[joy2_row + 11], ord("B") | 0x80)
        self.assertEqual(scene.text_frames[joy2_row + 9], ord("Y") | 0x80)


if __name__ == "__main__":
    unittest.main()
