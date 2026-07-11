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


class MapDemoTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        runtime_director = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            for index, name in enumerate(("terrain.png", "ship.png")):
                stripes[name] = index
                runtime_director.platform.sprites.stripes[index] = {
                    "width": 16,
                    "height": 16,
                    "frames": 6,
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

    def test_mapdemo_pans_viewport_and_edits_cells(self):
        scene = load_app("alecu.mapdemo")
        import vs2
        from games.alecu.mapdemo.code.mapdemo import MAP_COLUMNS, MAP_ROWS, VIEW_H, WALL

        self.assertEqual(scene._vs_declared_api, "vs2")
        self.assertEqual(len(scene.map_data), MAP_COLUMNS * MAP_ROWS)
        self.assertIs(scene.map.frames, scene.map_data)

        payload = vs2.export_scene_payload(scene)
        self.assertEqual(payload[4], 2)
        self.assertEqual(payload[7], 1)
        tilemap_size = struct.unpack_from("<H", payload, 14)[0]
        self.assertEqual(tilemap_size, 32)

        # joystick pans: right rotates the map, down pans the viewport
        self.step_buttons(director.JOY_RIGHT)
        self.assertEqual(scene.map.x, 1)
        self.step_buttons(director.JOY_DOWN)
        self.assertEqual(scene.map.viewport[1], 1)
        self.step_buttons(director.JOY_UP)
        self.step_buttons(director.JOY_UP)
        self.assertEqual(scene.map.viewport[1], 0)
        self.assertEqual(scene.map.viewport[3], VIEW_H)

        # button A writes a WALL into the live buffer, visible on re-export
        col, row = scene.cursor_cell()
        index = row * MAP_COLUMNS + col
        self.step_buttons(director.BUTTON_A)
        self.assertEqual(scene.map_data[index], WALL)
        updated = vs2.export_scene_payload(scene)
        self.assertIs(updated, payload)
        frames_offset = struct.unpack_from("<I", updated, 16 + 2 * 8 + 2 * 24 + 28)[0]
        self.assertEqual(updated[frames_offset + index], WALL)


if __name__ == "__main__":
    unittest.main()
