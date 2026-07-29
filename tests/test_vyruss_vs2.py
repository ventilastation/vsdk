import os
import random
import sys
import time
import unittest

from PIL import Image

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

        @staticmethod
        def sleep_ms(ms):
            time.sleep(ms / 1000.0)

    sys.modules["utime"] = _Utime

from ventilastation import api_guard
from ventilastation.app_loader import load_app
from ventilastation.director import configure_runtime, director, reset_runtime, stripes


VYRUSS_METADATA = {
    "disparo.png": (3, 8, 2),
    "explosion.png": (32, 32, 5),
    "explosion_nave.png": (32, 32, 4),
    "galaga.png": (16, 16, 12),
    "ll9.png": (16, 16, 4),
    "gameover.png": (64, 20, 1),
    "numerals.png": (4, 5, 12),
    "tierra.png": (256, 54, 1),
    "marte.png": (256, 54, 1),
    "jupiter.png": (256, 54, 1),
    "saturno.png": (256, 54, 1),
}


class VyrussVs2Tests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        runtime_director = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            for index, (name, values) in enumerate(VYRUSS_METADATA.items()):
                width, height, frames = values
                stripes[name] = index
                runtime_director.platform.sprites.stripes[index] = {
                    "width": width,
                    "height": height,
                    "frames": frames,
                    "palette": 0,
                    "glyphs": (
                        "0123456789 *"
                        if name == "numerals.png" else None
                    ),
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

    def test_angle_motion_snaps_instead_of_oscillating(self):
        from games.alecu.vyruss_vs2.code.vyruss_vs2 import (
            move_toward_angle,
        )

        self.assertEqual(move_toward_angle(1, 0, 3), 0)
        self.assertEqual(move_toward_angle(255, 0, 3), 0)
        self.assertEqual(move_toward_angle(10, 20, 3), 13)

    def test_ship_heading_targets_its_center_and_stays_on_the_rim(self):
        scene = load_app("alecu.vyruss_vs2")

        for _ in range(70):
            self.step_buttons(director.JOY_UP)
        self.assertEqual(scene.player.x, 120)

        self.step_buttons(0)
        self.assertEqual(scene.player.y, 16)
        self.step_buttons(director.BUTTON_B)
        self.assertEqual(scene.player.y, 16)
        self.step_buttons(director.JOY_DOWN)
        self.assertEqual(scene.player.y, 16)
        self.step_buttons(director.BUTTON_C)
        self.assertEqual(scene.player.y, 16)

    def test_entering_enemies_follow_their_path_instead_of_sticking_at_rim(self):
        scene = load_app("alecu.vyruss_vs2")
        for _ in range(8):
            self.step_buttons(0)
        self.assertEqual(len(scene.everyone), 1)
        baddie = scene.everyone[0]
        positions = []
        for _ in range(150):
            self.step_buttons(0)
            positions.append((baddie.x, baddie.y))

        self.assertGreater(len(set(positions)), 80)
        self.assertGreaterEqual(min(y for _x, y in positions), 48)
        self.assertNotIn(baddie.y, (30, 31))
        self.assertLess(len(baddie.movements), 6)

    def test_defeated_ship_flies_inward_toward_planet(self):
        scene = load_app("alecu.vyruss_vs2")
        scene.start_defeated()
        scene.warp_player()

        positions = []
        for _ in range(10):
            self.step_buttons(0)
            positions.append(scene.player.y)

        self.assertEqual(positions, list(range(18, 38, 2)))
        for _ in range(120):
            self.step_buttons(0)
        self.assertGreater(scene.player.y, 250)
        self.assertFalse(scene.ship_warping)

    def test_scoreboard_keeps_score_then_lives_in_screen_order(self):
        import vs2

        scene = load_app("alecu.vyruss_vs2")
        scene.score = 8100
        scene.lives = 2

        scene.update_scoreboard()

        self.assertIsInstance(scene.scoreboard, vs2.Label)
        self.assertEqual(scene.scoreboard.text, "08100 **")
        self.assertTrue(scene.scoreboard.flip_x)
        self.assertTrue(scene.scoreboard.flip_y)

    def test_scoreboard_glyphs_are_rotated_per_frame(self):
        original_path = os.path.join(
            ROOT, "games", "alecu", "vyruss", "images", "numerals.png")
        vs2_path = os.path.join(
            ROOT, "games", "alecu", "vyruss_vs2", "images", "numerals.png")

        with Image.open(original_path) as original_image:
            original = original_image.convert("RGBA")
        with Image.open(vs2_path) as vs2_image:
            rotated = vs2_image.convert("RGBA")

        self.assertEqual(original.size, (48, 5))
        self.assertEqual(rotated.size, original.size)
        for frame in range(12):
            box = (frame * 4, 0, frame * 4 + 4, 5)
            expected = original.crop(box).transpose(
                Image.Transpose.ROTATE_180)
            self.assertEqual(
                rotated.crop(box).tobytes(),
                expected.tobytes(),
                "frame %d is not an exact 180-degree rotation" % frame,
            )


if __name__ == "__main__":
    unittest.main()
