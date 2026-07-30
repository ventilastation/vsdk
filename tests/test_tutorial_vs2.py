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
        def ticks_ms(): return int(time.time() * 1000)
        @staticmethod
        def ticks_add(value, delta): return value + delta
        @staticmethod
        def ticks_diff(end, start): return end - start
    sys.modules["utime"] = _Utime

from ventilastation import api_guard
from ventilastation.app_loader import load_app
from ventilastation.director import configure_runtime, director, reset_runtime, stripes


class TutorialVs2Tests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        self.runtime_director = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            for index, name in enumerate(("rainbow437.png", "galaga.png", "gameover.png", "bembi.png", "doom.png")):
                stripes[name] = index
                self.runtime_director.platform.sprites.stripes[index] = {
                    "width": 8, "height": 8, "frames": 256, "palette": 0,
                }
        self.runtime_director.load_rom = fake_load_rom

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def step(self, buttons):
        director.platform.comms.push_input(bytes([buttons]))
        director.step_once()

    def test_tutorial_uses_labels_and_layer_owned_projection(self):
        scene = load_app("tutorial_vs2")
        self.assertEqual(scene._vs_declared_api, "vs2")
        self.assertEqual(len(scene.hud.tilemaps), 3)
        self.assertEqual(len(scene.hud.sprites), 1)
        self.assertEqual(scene.entries[2]["sprite"].y, 0)
        self.assertEqual(scene.entries[3]["sprite"].y, 0)
        sprite = scene.active()["sprite"]
        self.assertEqual((sprite.x, sprite.y), (-8, 0))
        self.step(director.JOY_RIGHT | director.JOY_DOWN)
        self.assertEqual((sprite.x, sprite.y), (-8.25, -0.25))
        self.step(0)
        self.step(director.BUTTON_B)
        self.assertTrue(sprite.flip_x)
        self.step(0)
        self.step(director.BUTTON_C)
        self.assertEqual(sprite.frame, 7)


if __name__ == "__main__":
    unittest.main()
