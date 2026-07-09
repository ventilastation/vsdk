import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
sys.path.insert(0, ROOT)
sys.modules.setdefault("uos", os)
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

        @staticmethod
        def sleep_ms(ms):
            time.sleep(ms / 1000.0)

    sys.modules["utime"] = _Utime

from ventilastation import api_guard
from ventilastation.app_loader import load_app
from ventilastation.director import configure_runtime, director, reset_runtime, stripes


class TutorialVs2Tests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        runtime_director = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            for index, name in enumerate(
                ("rainbow437.png", "galaga.png", "gameover.png", "bembi.png", "doom.png")
            ):
                stripes[name] = index
                runtime_director.platform.sprites.stripes[index] = {
                    "width": 8,
                    "height": 8,
                    "frames": 256,
                    "palette": 0,
                }

        runtime_director.load_rom = fake_load_rom

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def step_buttons(self, buttons):
        director.platform.comms.push_input(bytes([buttons]))
        try:
            director.step_once()
        except StopIteration:
            pass

    def release_buttons(self):
        self.step_buttons(0)

    def text_value(self, display):
        chars = []
        for sprite in display.chars:
            frame = sprite.frame
            if frame:
                chars.append(chr(frame))
        return "".join(chars)

    def test_tutorial_vs2_uses_quarter_step_coordinates_and_flip_flags(self):
        scene = load_app("tutorial_vs2")

        self.assertEqual(scene._vs_declared_api, "vs2")
        self.assertEqual(api_guard.claimed_api("system.tutorial_vs2"), "vs2")
        self.assertEqual(self.text_value(scene.coordinates), "X=-8.00 Y=16.00")

        self.step_buttons(director.JOY_LEFT | director.JOY_UP)
        sprite = scene.active()["sprite"]

        self.assertEqual(scene.active()["xq"], -33)
        self.assertEqual(scene.active()["yq"], 63)
        self.assertEqual(sprite.x, -8.25)
        self.assertEqual(sprite.y, 15.75)
        self.assertEqual(sprite._sprite._state["x"], 247)
        self.assertEqual(sprite._sprite._state["y"], 15)
        self.assertEqual(self.text_value(scene.coordinates), "X=-8.25 Y=15.75")

        self.release_buttons()

        for _ in range(9):
            self.step_buttons(director.JOY_RIGHT)

        self.assertEqual(scene.active()["xq"], -23)
        self.assertEqual(sprite.x, -5.75)
        self.assertEqual(self.text_value(scene.coordinates), "X=-5.75 Y=15.75")

        self.release_buttons()

        states = []
        for _ in range(4):
            self.step_buttons(director.BUTTON_B)
            states.append((sprite.flip_x, sprite.flip_y))
            self.release_buttons()

        self.assertEqual(
            states,
            [
                (True, False),
                (False, True),
                (True, True),
                (False, False),
            ],
        )
        self.assertEqual(self.text_value(scene.flags), "FX=0 FY=0 FR=06")


if __name__ == "__main__":
    unittest.main()
