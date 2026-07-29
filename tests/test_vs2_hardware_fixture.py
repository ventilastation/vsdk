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
from ventilastation.director import configure_runtime, reset_runtime, stripes


class Vs2HardwareFixtureTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        runtime_director = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            metadata = {
                "tinyfont_menu.png": (4, 6, 255),
                "galaga.png": (20, 16, 12),
                "vs2_environment.png": (32, 16, 16),
            }
            for index, (name, values) in enumerate(metadata.items()):
                width, height, frames = values
                stripes[name] = index
                runtime_director.platform.sprites.stripes[index] = {
                    "width": width,
                    "height": height,
                    "frames": frames,
                    "palette": 0,
                    "glyphs": None,
                }

        runtime_director.load_rom = fake_load_rom

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def test_fixture_seals_every_renderer_budget_at_its_limit(self):
        scene = load_app("vs2_hardware")
        import vs2
        from system.vs2_hardware.code import (
            ENVIRONMENT_TILEMAP_COUNT,
            LAYER_COUNT,
            LABEL_COUNT,
            SPRITE_COUNT,
            TILEMAP_COUNT,
        )

        self.assertEqual(scene._phase, "sealed")
        self.assertEqual(len(scene.layers), LAYER_COUNT)
        self.assertEqual(len(scene.sprites), SPRITE_COUNT)
        self.assertEqual(len(scene.labels), LABEL_COUNT)
        self.assertEqual(
            ENVIRONMENT_TILEMAP_COUNT + len(scene.labels),
            TILEMAP_COUNT,
        )
        self.assertEqual(scene._sprite_count, vs2.limits.sprites)
        self.assertEqual(scene._tilemap_count, vs2.limits.tilemaps)
        self.assertEqual(len(scene.layers), vs2.limits.layers)

        payload = vs2.export_scene_payload(scene)
        self.assertEqual(payload[4], 3)
        self.assertEqual((payload[5], payload[6], payload[7]), (8, 100, 16))

    def test_fixture_uses_tunnel_depth_and_ordered_environment_maps(self):
        scene = load_app("vs2_hardware")
        import vs2
        from system.vs2_hardware.code import (
            CLOUD_FRAME_BASE,
            CLOUD_FRAMES,
            HUD_LABEL_COLUMNS,
            HUD_LABEL_X_STEP,
            HUD_LABEL_Y_STEP,
            OBJECT_FRAME_BASE,
            OBJECT_FRAMES,
            ENVIRONMENT_VIEW_HEIGHT,
            TUNNEL_LAYER_COUNT,
            TUNNEL_DEPTH_MAX,
            TUNNEL_DEPTH_MIN,
        )

        self.assertTrue(
            all(
                layer.projection == vs2.TUNNEL
                for layer in scene.layers[:TUNNEL_LAYER_COUNT]
            )
        )
        self.assertEqual(scene.label_layer.projection, vs2.HUD)
        self.assertIs(scene.layers[-1], scene.label_layer)
        self.assertEqual(
            sorted(sprite.y for sprite in scene.sprites),
            [sprite.y for sprite in scene.sprites],
        )
        self.assertGreaterEqual(scene.sprites[0].y, TUNNEL_DEPTH_MIN)
        self.assertLess(scene.sprites[-1].y, TUNNEL_DEPTH_MAX)

        flattened = [
            drawable
            for layer in scene.layers
            for drawable in layer._drawables
        ]
        first_sprite = min(flattened.index(sprite) for sprite in scene.sprites)
        last_sprite = max(flattened.index(sprite) for sprite in scene.sprites)
        self.assertLess(flattened.index(scene.ground), first_sprite)
        self.assertLess(flattened.index(scene.objects), first_sprite)
        self.assertGreater(flattened.index(scene.clouds), last_sprite)
        self.assertTrue(
            all(
                flattened.index(label) > flattened.index(scene.clouds)
                for label in scene.labels
            )
        )
        self.assertTrue(
            all(label._layer is scene.label_layer for label in scene.labels)
        )
        self.assertFalse(scene.label_layer.sprites)
        for tilemap in (scene.ground, scene.objects, scene.clouds):
            self.assertEqual(tilemap.y, 0)
            self.assertEqual(tilemap.view_height, ENVIRONMENT_VIEW_HEIGHT)

        self.assertNotIn(vs2.EMPTY_TILE, scene.ground.cells)
        object_tiles = [
            cell for cell in scene.objects.cells if cell != vs2.EMPTY_TILE
        ]
        cloud_tiles = [
            cell for cell in scene.clouds.cells if cell != vs2.EMPTY_TILE
        ]
        self.assertTrue(object_tiles)
        self.assertTrue(cloud_tiles)
        self.assertTrue(
            all(
                OBJECT_FRAME_BASE <= cell < OBJECT_FRAME_BASE + OBJECT_FRAMES
                for cell in object_tiles
            )
        )
        self.assertTrue(
            all(
                CLOUD_FRAME_BASE <= cell < CLOUD_FRAME_BASE + CLOUD_FRAMES
                for cell in cloud_tiles
            )
        )

        expected_positions = [
            (
                (index % HUD_LABEL_COLUMNS) * HUD_LABEL_X_STEP,
                (index // HUD_LABEL_COLUMNS) * HUD_LABEL_Y_STEP,
            )
            for index in range(len(scene.labels))
        ]
        self.assertEqual(
            [(label.x, label.y) for label in scene.labels],
            expected_positions,
        )
        self.assertTrue(
            all(
                label.y + label.image.height <= vs2.display.height
                for label in scene.labels
            )
        )

    def test_fixture_reserves_the_top_hud_layer_for_all_labels(self):
        scene = load_app("vs2_hardware")
        import vs2

        expected_text = [
            "L%d.%d VS2 USB %03d" % (
                layer_index,
                label_index,
                layer_index * 17 + label_index,
            )
            for layer_index in range(1, 8)
            for label_index in range(2 if layer_index < 7 else 1)
        ]
        self.assertEqual(
            [label.text for label in scene.labels],
            expected_text,
        )
        self.assertTrue(
            all(
                any(cell != vs2.EMPTY_TILE for cell in label.cells)
                for label in scene.labels
            )
        )
        self.assertEqual(scene.label_layer._drawables, scene.labels)

    def test_fixture_scrolls_layers_and_environment_at_different_speeds(self):
        scene = load_app("vs2_hardware")
        import vs2
        from system.vs2_hardware.code import _LAYER_SCROLL_EVERY

        first = scene.layer_sprites[0][0]
        second = scene.layer_sprites[1][0]
        label = scene.labels[0]
        before = {
            "first": (first.x, first.y),
            "second": (second.x, second.y),
            "label": (label.x, label.y),
            "ground": (scene.ground.x, scene.ground.view_y),
            "objects": (scene.objects.x, scene.objects.view_y),
            "clouds": (scene.clouds.x, scene.clouds.view_y),
        }
        for _ in range(_LAYER_SCROLL_EVERY * 2):
            scene.update()

        self.assertNotEqual((first.x, first.y), before["first"])
        self.assertNotEqual((second.x, second.y), before["second"])
        self.assertNotEqual(
            (first.x - before["first"][0], first.y - before["first"][1]),
            (second.x - before["second"][0], second.y - before["second"][1]),
        )
        self.assertEqual((label.x, label.y), before["label"])
        self.assertEqual((scene.ground.x, scene.ground.view_y), (4, 4))
        self.assertEqual((scene.objects.x, scene.objects.view_y), (8, 12))
        self.assertEqual(
            (scene.clouds.x, scene.clouds.view_y),
            (vs2.display.width - 12, 8),
        )

    def test_fixture_restores_and_freezes_the_native_oracle_frame(self):
        scene = load_app("vs2_hardware")

        initial_sprites = [(sprite.x, sprite.y) for sprite in scene.sprites]
        initial_labels = [(label.x, label.y) for label in scene.labels]
        for _ in range(12):
            scene.update()
        self.assertNotEqual(
            [(sprite.x, sprite.y) for sprite in scene.sprites],
            initial_sprites,
        )

        scene.prepare_capture()
        self.assertFalse(scene.animate)
        self.assertEqual(
            [(sprite.x, sprite.y) for sprite in scene.sprites],
            initial_sprites,
        )
        self.assertEqual(
            [(label.x, label.y) for label in scene.labels],
            initial_labels,
        )
        self.assertEqual((scene.ground.x, scene.ground.view_y), (0, 0))
        self.assertEqual((scene.objects.x, scene.objects.view_y), (0, 0))
        self.assertEqual((scene.clouds.x, scene.clouds.view_y), (0, 0))
        scene.update()
        self.assertEqual(
            [(sprite.x, sprite.y) for sprite in scene.sprites],
            initial_sprites,
        )


if __name__ == "__main__":
    unittest.main()
