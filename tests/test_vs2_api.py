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

    def test_base_control_uses_normalized_commands_and_deduplicates(self):
        api_guard.begin_app("games.test_vs2", "vs2")
        import vs2

        vs2.base.leds.set_all(1, 2, 3)
        vs2.base.leds.set_all(1, 2, 3)
        vs2.base.servo.set(128)
        vs2.base.buttons.set(vs2.base.BUTTON_LED_ALL, 250)
        self.assertEqual(director.platform.comms.sent, [
            (b"base leds 1 2 3", b""),
            (b"base servo 128", b""),
            (b"base buttons 3 250", b""),
        ])
        with self.assertRaises(ValueError):
            vs2.base.servo.set(256)
        with self.assertRaises(ValueError):
            vs2.base.buttons.set(4)

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

        sprite.x = -0.25
        self.assertEqual(sprite.x, -0.25)
        self.assertEqual(sprite._sprite._state["x"], 255)

        sprite.x = 256.25
        self.assertEqual(sprite.x, 256.25)
        self.assertEqual(sprite._sprite._state["x"], 0)

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

    def test_sprite_constructor_omits_replacing_when_not_replacing(self):
        api_guard.begin_app("games.test_vs2", "vs2")
        import vs2

        original_sprite_type = director.platform.sprites.Sprite
        sentinel = object()
        calls = []

        class StrictSprite(original_sprite_type):
            def __init__(self, replacing=sentinel):
                calls.append(replacing)
                if replacing is None:
                    raise AssertionError("replacing=None should be omitted")
                super().__init__(replacing=None if replacing is sentinel else replacing)

        director.platform.sprites.Sprite = StrictSprite

        sprite = vs2.Sprite()
        replacement = vs2.Sprite(replacing=sprite)

        self.assertIs(calls[0], sentinel)
        self.assertIs(calls[1], sprite._sprite)
        self.assertIs(replacement._sprite._state, sprite._sprite._state)

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

    def test_native_backend_receives_live_fixed_point_records(self):
        class NativeLayer:
            def __init__(self, mode=1, visible=True):
                self.mode = mode
                self.visible = visible

            def set_mode(self, mode):
                self.mode = mode

            def set_visible(self, visible):
                self.visible = visible

        class NativeSprite:
            def __init__(self, replacing=None):
                self.replacing = replacing
                self.x_fixed = None
                self.y_fixed = None
                self.frame = None
                self.strip = None
                self.mode = None
                self.flags = None
                self.layer = None

            def set_x_fixed(self, value):
                self.x_fixed = value

            def set_y_fixed(self, value):
                self.y_fixed = value

            def set_frame(self, value):
                self.frame = value

            def set_strip(self, value):
                self.strip = value

            def set_perspective(self, value):
                self.mode = value

            def set_flags(self, value):
                self.flags = value

            def set_layer(self, value):
                self.layer = value

            def width(self):
                return 8

            def height(self):
                return 8

        class NativeVs2:
            Layer = NativeLayer
            Sprite = NativeSprite

            def __init__(self):
                self.reset_count = 0
                self.active = []

            def reset_scene(self):
                self.reset_count += 1

            def set_active(self, active):
                self.active.append(active)

        api_guard.begin_app("games.test_vs2", "vs2")
        import vs2

        native = NativeVs2()
        director.platform.vs2 = native

        scene = vs2.Scene()
        scene.on_enter()
        layer = scene.layer("hud", mode=vs2.HUD)
        sprite = layer.add(vs2.Sprite(7, x=-0.25, y=12.5, frame=3, flip_x=True))

        self.assertEqual(native.reset_count, 1)
        self.assertEqual(native.active, [True])
        self.assertIs(sprite._sprite.layer, layer._layer)
        self.assertEqual(sprite._sprite.x_fixed, -64)
        self.assertEqual(sprite._sprite.y_fixed, 3200)
        self.assertEqual(sprite._sprite.strip, 7)
        self.assertEqual(sprite._sprite.mode, vs2.HUD)
        self.assertEqual(sprite._sprite.frame, 3)
        self.assertEqual(sprite._sprite.flags & vs2.FLAG_VISIBLE, vs2.FLAG_VISIBLE)
        self.assertEqual(sprite._sprite.flags & vs2.FLAG_FLIP_X, vs2.FLAG_FLIP_X)

        sprite.visible = False
        self.assertEqual(sprite._sprite.frame, 3)
        self.assertFalse(sprite._sprite.flags & vs2.FLAG_VISIBLE)

        sprite.frame = 4
        self.assertEqual(sprite._sprite.frame, 4)
        self.assertEqual(sprite._sprite.flags & vs2.FLAG_VISIBLE, vs2.FLAG_VISIBLE)

        scene.on_exit()
        self.assertEqual(native.active, [True, False])
        self.assertEqual(native.reset_count, 2)

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

    def test_scene_payload_reuses_buffer_when_shape_is_stable(self):
        api_guard.begin_app("games.test_vs2", "vs2")
        import vs2

        scene = vs2.Scene()
        scene._vs_api_slug = "games.test_vs2"
        scene._vs_declared_api = "vs2"
        director.push(scene)
        sprite = vs2.Sprite(7, x=1, y=2, frame=0)

        first = vs2.export_scene_payload(scene)
        sprite.x = 3
        second = vs2.export_scene_payload(scene)

        self.assertIs(first, second)
        header_size = struct.unpack_from("<H", second, 8)[0]
        x_fixed = struct.unpack_from("<i", second, header_size + 10)[0]
        self.assertEqual(x_fixed, 3 * 256)

    def test_scene_exit_releases_live_sprites_and_payload_buffer(self):
        api_guard.begin_app("games.test_vs2", "vs2")
        import vs2

        scene = vs2.Scene()
        scene._vs_api_slug = "games.test_vs2"
        scene._vs_declared_api = "vs2"
        director.push(scene)
        vs2.Sprite(7, frame=0)
        vs2.export_scene_payload(scene)

        self.assertTrue(scene._vs2_payload)
        self.assertGreaterEqual(len(vs2._live_sprites), 1)

        director.pop()

        self.assertIsNone(scene._vs2_payload)
        self.assertNotIn(scene, [getattr(sprite, "_scene", None) for sprite in vs2._live_sprites])

    def test_scene_exit_clears_layer_ownership(self):
        api_guard.begin_app("games.test_vs2", "vs2")
        import vs2

        scene = vs2.Scene()
        scene._vs_api_slug = "games.test_vs2"
        scene._vs_declared_api = "vs2"
        director.push(scene)
        layer = scene.layer("world")
        sprite = layer.add(vs2.Sprite(7, frame=0))

        director.pop()

        self.assertEqual(scene.layers, [])
        self.assertEqual(layer.sprites, [])
        self.assertIsNone(layer.scene)
        self.assertIsNone(layer._layer)
        self.assertIsNone(sprite.layer)
        self.assertIsNone(sprite._scene)

    def test_reentering_scene_recreates_layers_and_sprites(self):
        api_guard.begin_app("games.test_vs2", "vs2")
        import vs2

        class Reenterable(vs2.Scene):
            _vs_api_slug = "games.test_vs2"
            _vs_declared_api = "vs2"

            def on_enter(self):
                super().on_enter()
                layer = self.layer("world")
                self.sprite = layer.add(vs2.Sprite(7, frame=0))

        scene = Reenterable()
        director.push(scene)
        old_layer = scene.layers[0]
        old_sprite = scene.sprite
        director.pop()
        director.push(scene)

        self.assertIsNot(scene.layers[0], old_layer)
        self.assertIsNot(scene.sprite, old_sprite)
        self.assertEqual(len(scene.layers), 1)
        self.assertEqual(len(scene.layers[0].sprites), 1)
        self.assertIs(scene.layers[0].sprites[0], scene.sprite)
        self.assertNotIn(old_sprite, vs2._live_sprites)

    def test_stable_scene_payload_is_mutated_in_place(self):
        api_guard.begin_app("games.test_vs2", "vs2")
        import vs2

        scene = vs2.Scene()
        scene._vs_api_slug = "games.test_vs2"
        scene._vs_declared_api = "vs2"
        director.push(scene)
        sprite = vs2.Sprite(7, x=1, y=2, frame=0)
        payload = vs2.export_scene_payload(scene)
        payload_id = id(payload)

        sprite.x = -3.25
        updated = vs2.export_scene_payload(scene)

        self.assertEqual(id(updated), payload_id)
        header_size = struct.unpack_from("<H", updated, 8)[0]
        x_fixed = struct.unpack_from("<i", updated, header_size + 10)[0]
        self.assertEqual(x_fixed, int(-3.25 * 256))


if __name__ == "__main__":
    unittest.main()
