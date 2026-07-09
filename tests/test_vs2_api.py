import os
import sys
import struct
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
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
from ventilastation.director import configure_runtime, director, reset_runtime
from ventilastation.scene import Scene


class Vs2ApiTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        configure_runtime("headless")

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def test_sprite_attributes_sync_to_backend(self):
        api_guard.begin_app("games.test_vs2", "vs2")
        import vs2

        sprite = vs2.Sprite(x=12.5, y=-4, frame=3, mode=vs2.HUD, visible=True)
        self.assertEqual(sprite.x, 12.5)
        self.assertEqual(sprite.y, -4)
        self.assertEqual(sprite.frame, 3)
        self.assertEqual(sprite.mode, vs2.HUD)
        self.assertEqual(sprite._sprite._state["x"], 12)
        self.assertEqual(sprite._sprite._state["y"], 0)
        self.assertEqual(sprite._sprite._state["frame"], 3)
        self.assertEqual(sprite._sprite._state["perspective"], vs2.HUD)

        sprite.hide()
        self.assertFalse(sprite.visible)
        self.assertEqual(sprite._sprite._state["frame"], 255)

    def test_sprites_start_hidden_without_an_explicit_frame(self):
        api_guard.begin_app("games.test_vs2", "vs2")
        import vs2

        sprite = vs2.Sprite()
        self.assertFalse(sprite.visible)
        self.assertEqual(sprite.frame, 0)
        self.assertEqual(sprite._sprite._state["frame"], 255)

        sprite.frame = 0
        self.assertTrue(sprite.visible)
        self.assertEqual(sprite._sprite._state["frame"], 0)

    def test_explicit_constructor_frame_shows_unless_visibility_overridden(self):
        api_guard.begin_app("games.test_vs2", "vs2")
        import vs2

        sprite = vs2.Sprite(frame=3)
        self.assertTrue(sprite.visible)
        self.assertEqual(sprite._sprite._state["frame"], 3)

        hidden = vs2.Sprite(frame=4, visible=False)
        self.assertFalse(hidden.visible)
        self.assertEqual(hidden.frame, 4)
        self.assertEqual(hidden._sprite._state["frame"], 255)

    def test_layer_adopts_sprite_mode(self):
        api_guard.begin_app("games.test_vs2", "vs2")
        import vs2

        scene = vs2.Scene()
        layer = scene.layer("hud", mode=vs2.HUD)
        sprite = vs2.Sprite()
        layer.add(sprite)

        self.assertIs(sprite.layer, layer)
        self.assertEqual(sprite.mode, vs2.HUD)
        self.assertIn(sprite, layer.sprites)
        self.assertIn(layer, scene.layers)

    def test_declared_vs2_rejects_legacy_sprites(self):
        api_guard.begin_app("games.test_vs2", "vs2")
        with self.assertRaises(ImportError):
            from ventilastation.sprites import Sprite  # noqa: F401

    def test_game_cannot_mix_vs2_after_legacy_sprites(self):
        api_guard.begin_app("games.test_legacy")
        from ventilastation.sprites import Sprite

        Sprite()
        import vs2
        with self.assertRaises(ImportError):
            vs2.Sprite()

    def test_popping_vs2_scene_reenters_neutral_legacy_scene(self):
        class Launcher(Scene):
            def __init__(self):
                super().__init__()
                self.enters = 0

            def on_enter(self):
                from ventilastation.sprites import Sprite

                self.enters += 1
                Sprite()

        class Vs2Game(Scene):
            _vs_api_slug = "games.test_vs2"
            _vs_declared_api = "vs2"

            def on_enter(self):
                import vs2

                vs2.Sprite()

        launcher = Launcher()
        director.push(launcher)
        director.push(Vs2Game())
        director.pop()

        self.assertEqual(launcher.enters, 2)
        self.assertIsNone(api_guard.current_app())

    def test_scene_payload_exports_layers_and_fixed_point_sprites(self):
        api_guard.begin_app("games.test_vs2", "vs2")
        import vs2

        scene = vs2.Scene()
        scene._vs_api_slug = "games.test_vs2"
        scene._vs_declared_api = "vs2"
        director.push(scene)
        layer = scene.layer("playfield", mode=vs2.HUD)
        sprite = layer.add(vs2.Sprite(7, x=12.5, y=-4.25, frame=3, flip_x=True))

        payload = vs2.export_scene_payload(scene)
        self.assertEqual(payload[0:4], b"VS2\0")
        self.assertEqual(payload[4], 1)
        self.assertEqual(payload[5], 1)
        self.assertEqual(payload[6], 1)

        header_size = struct.unpack_from("<H", payload, 8)[0]
        layer_size = struct.unpack_from("<H", payload, 10)[0]
        sprite_size = struct.unpack_from("<H", payload, 12)[0]
        self.assertEqual(header_size, 16)
        self.assertEqual(layer_size, 8)
        self.assertEqual(sprite_size, 24)

        layer_id, mode, flags = struct.unpack_from("<BBB", payload, header_size)
        self.assertEqual(layer_id, 0)
        self.assertEqual(mode, vs2.HUD)
        self.assertEqual(flags & vs2.FLAG_VISIBLE, vs2.FLAG_VISIBLE)

        offset = header_size + layer_size
        fields = struct.unpack_from("<BBBBBBhhii", payload, offset)
        self.assertEqual(fields[0], 0)
        self.assertEqual(fields[1], 7)
        self.assertEqual(fields[2], 3)
        self.assertEqual(fields[3], vs2.HUD)
        self.assertEqual(fields[4] & vs2.FLAG_VISIBLE, vs2.FLAG_VISIBLE)
        self.assertEqual(fields[4] & vs2.FLAG_FLIP_X, vs2.FLAG_FLIP_X)
        self.assertEqual(fields[8], int(12.5 * 256))
        self.assertEqual(fields[9], int(-4.25 * 256))
        self.assertIs(sprite.layer, layer)

    def test_unlayered_scene_payload_preserves_sprite_mode(self):
        api_guard.begin_app("games.test_vs2", "vs2")
        import vs2

        scene = vs2.Scene()
        scene._vs_api_slug = "games.test_vs2"
        scene._vs_declared_api = "vs2"
        director.push(scene)
        planet = vs2.Sprite(9, x=0, y=255, frame=0, mode=vs2.FULLSCREEN)
        sign = vs2.Sprite(10, x=224, y=0, frame=0, mode=vs2.HUD)

        payload = vs2.export_scene_payload(scene)
        self.assertEqual(payload[5], 0)
        self.assertEqual(payload[6], 2)

        header_size = struct.unpack_from("<H", payload, 8)[0]
        sprite_size = struct.unpack_from("<H", payload, 12)[0]
        first = struct.unpack_from("<BBBBBBhhii", payload, header_size)
        second = struct.unpack_from("<BBBBBBhhii", payload, header_size + sprite_size)
        self.assertEqual(first[0], vs2.NO_LAYER)
        self.assertEqual(first[1], 9)
        self.assertEqual(first[3], vs2.FULLSCREEN)
        self.assertEqual(second[0], vs2.NO_LAYER)
        self.assertEqual(second[1], 10)
        self.assertEqual(second[3], vs2.HUD)
        self.assertIs(planet.layer, None)
        self.assertIs(sign.layer, None)


if __name__ == "__main__":
    unittest.main()
