import os
import random
import struct
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

        @staticmethod
        def sleep_ms(ms):
            time.sleep(ms / 1000.0)

    sys.modules["utime"] = _Utime

from ventilastation import api_guard
from ventilastation.app_loader import load_app
from ventilastation.director import configure_runtime, director, reset_runtime, stripes

VIXEOUS_STRIPS = (
    "ship.png", "enemy.png", "boss.png", "shots.png", "explosion.png",
    "targets.png", "reticle.png", "terrain.png", "digits.png", "messages.png",
)


class VixeousVs2Tests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        runtime_director = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            for index, name in enumerate(VIXEOUS_STRIPS):
                stripes[name] = index
                runtime_director.platform.sprites.stripes[index] = {
                    "width": 32 if name == "terrain.png" else 16,
                    "height": 16,
                    "frames": 16,
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

    def test_vixeous_uses_one_terrain_tilemap(self):
        scene = load_app("alecu.vixeous")
        import vs2
        from games.alecu.vixeous.code.vixeous import (
            TERRAIN_BUFFER_ROWS, TERRAIN_COLS, TERRAIN_TILE_H, TERRAIN_VIEW_H,
            terrain_frame_for,
        )

        self.assertEqual(scene._vs_declared_api, "vs2")
        self.assertIs(scene.terrain.frames, scene.terrain_data)
        self.assertEqual(len(scene.world.tilemaps), 1)

        for row in range(TERRAIN_BUFFER_ROWS):
            for col in range(TERRAIN_COLS):
                self.assertEqual(
                    scene.terrain_data[row * TERRAIN_COLS + col],
                    terrain_frame_for(col, row, 0),
                )

        payload = vs2.export_scene_payload(scene)
        self.assertEqual(payload[4], 2)
        self.assertEqual(payload[7], 1)

    def test_vixeous_terrain_scrolls_by_panning_the_viewport(self):
        scene = load_app("alecu.vixeous")
        from games.alecu.vixeous.code.vixeous import (
            STATE_PLAYING, TERRAIN_COLS, TERRAIN_SCROLL_TICKS, TERRAIN_TILE_H,
            TERRAIN_TILE_W, TERRAIN_VIEW_H, terrain_frame_for,
        )

        scene.state = STATE_PLAYING
        scene.message.hide()

        # scroll half a tile: viewport pans without touching the cell buffer
        for _ in range(TERRAIN_SCROLL_TICKS * (TERRAIN_TILE_H // 2)):
            self.step_buttons(0)
        self.assertEqual(scene.depth, TERRAIN_TILE_H // 2)
        self.assertEqual(
            scene.terrain.viewport,
            (0, TERRAIN_TILE_H // 2, 256, TERRAIN_VIEW_H),
        )
        self.assertEqual(scene.terrain_base_row, 0)

        # scroll the other half: a whole row has passed, cells regenerate
        for _ in range(TERRAIN_SCROLL_TICKS * (TERRAIN_TILE_H // 2)):
            self.step_buttons(0)
        self.assertEqual(scene.depth, TERRAIN_TILE_H)
        self.assertEqual(scene.terrain.viewport, (0, 0, 256, TERRAIN_VIEW_H))
        self.assertEqual(scene.terrain_base_row, 1)
        for col in range(TERRAIN_COLS):
            self.assertEqual(
                scene.terrain_data[col], terrain_frame_for(col, 1, 0),
            )

        # the map rotates opposite the camera
        expected_x = (-scene.camera_theta - TERRAIN_TILE_W // 2) % 256
        self.assertEqual(scene.terrain.x, expected_x)
        self.step_buttons(director.JOY_RIGHT)
        self.assertNotEqual(scene.camera_theta, 0)
        expected_x = (-scene.camera_theta - TERRAIN_TILE_W // 2) % 256
        self.assertEqual(scene.terrain.x, expected_x)


if __name__ == "__main__":
    unittest.main()
