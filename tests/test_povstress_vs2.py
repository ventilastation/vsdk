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

        @staticmethod
        def sleep_ms(ms):
            time.sleep(ms / 1000.0)

    sys.modules["utime"] = _Utime

from ventilastation import api_guard
from ventilastation.app_loader import load_app
from ventilastation.director import configure_runtime, director, reset_runtime, stripes

# The demo reuses these Vixeous strips (see games/demos/povstress/images).
POVSTRESS_STRIPS = ("ship.png", "shots.png", "explosion.png", "terrain.png", "digits.png")

# Renderer capacities from hardware/rotor/modules/povdisplay/gpu.h -- the demo
# is a stress test, so it must stay inside them.
VS2_MAX_LAYERS = 16
VS2_MAX_SPRITES = 100
VS2_MAX_TILEMAPS = 8


class PovStressVs2Tests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        runtime_director = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            for index, name in enumerate(POVSTRESS_STRIPS):
                stripes[name] = index
                runtime_director.platform.sprites.stripes[index] = {
                    "width": 32 if name == "terrain.png" else 20,
                    "height": 16,
                    "frames": 16,
                    "palette": 0,
                }

        runtime_director.load_rom = fake_load_rom

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def step(self, buttons=0):
        director.platform.comms.push_input(bytes([buttons]))
        try:
            director.step_once()
        except StopIteration:
            pass

    def test_scene_shape_is_6_layers_of_10_plus_terrain_and_scoreboard(self):
        scene = load_app("demos.povstress")
        from games.demos.povstress.code.povstress import (
            NUM_LAYERS, SPRITES_PER_LAYER,
        )

        self.assertEqual(scene._vs_declared_api, "vs2")

        field_layers = [l for l in scene.layers if l.name and l.name.startswith("field")]
        self.assertEqual(len(field_layers), NUM_LAYERS)
        for layer in field_layers:
            self.assertEqual(len(layer.sprites), SPRITES_PER_LAYER)
        self.assertEqual(len(scene.movers), NUM_LAYERS * SPRITES_PER_LAYER)

        # one base tilemap, scoreboard = 5 digits + 3 life icons
        self.assertEqual(len(scene.terrain_layer.tilemaps), 1)
        self.assertIs(scene.terrain.frames, scene.terrain_data)
        self.assertEqual(len(scene.hud.sprites), 8)

    def test_terrain_is_identical_to_vixeous(self):
        scene = load_app("demos.povstress")
        from games.demos.povstress.code.povstress import (
            TERRAIN_BUFFER_ROWS, TERRAIN_COLS, terrain_frame_for,
        )
        from games.alecu.vixeous.code.vixeous import (
            terrain_frame_for as vixeous_terrain_frame_for,
        )

        for row in range(TERRAIN_BUFFER_ROWS):
            for col in range(TERRAIN_COLS):
                cell = scene.terrain_data[row * TERRAIN_COLS + col]
                self.assertEqual(cell, terrain_frame_for(col, row, 0))
                # byte-for-byte identical to the real Vixeous terrain
                self.assertEqual(cell, vixeous_terrain_frame_for(col, row, 0))

    def test_payload_stays_within_renderer_limits(self):
        scene = load_app("demos.povstress")
        import vs2

        payload = vs2.export_scene_payload(scene)
        version, layers, sprites, tilemaps = payload[4], payload[5], payload[6], payload[7]
        self.assertEqual(version, 2)  # tilemap-carrying payload
        self.assertLessEqual(layers, VS2_MAX_LAYERS)
        self.assertLessEqual(sprites, VS2_MAX_SPRITES)
        self.assertLessEqual(tilemaps, VS2_MAX_TILEMAPS)
        self.assertEqual(sprites, 68)  # 60 movers + 8 scoreboard

    def test_stepping_moves_every_sprite_and_scrolls_terrain(self):
        scene = load_app("demos.povstress")

        before = [(m.sprite.x, m.sprite.y) for m in scene.movers]
        depth0 = scene.depth
        for _ in range(5):
            self.step(0)
        after = [(m.sprite.x, m.sprite.y) for m in scene.movers]

        self.assertTrue(all(b != a for b, a in zip(before, after)))
        self.assertGreater(scene.depth, depth0)

    def test_layers_move_at_different_speeds(self):
        scene = load_app("demos.povstress")

        # dy is assigned per layer index (layer_index + 1), so the vertical
        # speed of the first sprite in each field layer must be distinct.
        first_in_layer = {}
        for mover in scene.movers:
            first_in_layer.setdefault(mover.dy, mover)
        self.assertEqual(len(first_in_layer), 6)  # six distinct speeds

    def test_button_d_exits_to_the_previous_scene(self):
        load_app("demos.povstress")
        depth = len(director.scene_stack)
        self.assertGreaterEqual(depth, 1)
        self.step(director.BUTTON_D)
        self.assertEqual(len(director.scene_stack), depth - 1)


if __name__ == "__main__":
    unittest.main()
