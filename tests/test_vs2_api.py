import os
import sys
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


if __name__ == "__main__":
    unittest.main()
