import os
import struct
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
    sys.modules["utime"] = _Utime

from ventilastation import api_guard
from ventilastation.director import configure_runtime, director, reset_runtime, stripes
from ventilastation.scene import Scene as LegacyScene


class Vs2ApiTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        self.runtime_director = configure_runtime("headless")
        stripes.clear()
        for index, name in enumerate(("ship.png", "terrain.png", "font.png")):
            stripes[name] = index
            self.runtime_director.platform.sprites.stripes[index] = {
                "width": 8, "height": 8, "frames": 4 if name != "font.png" else 128,
                "palette": 0,
            }
        self.runtime_director.platform.sprites.stripes[stripes["terrain.png"]]["width"] = 16
        self.runtime_director.platform.sprites.stripes[stripes["terrain.png"]]["height"] = 8
        api_guard.begin_app("games.test_vs2", "vs2")
        import vs2
        self.vs2 = vs2

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def enter(self, scene):
        director.push(scene)
        return scene

    def test_display_geometry_and_services_are_public(self):
        from vs2.controls import BACK, START, joy1, joy2

        self.assertEqual(self.vs2.display.width, 256)
        self.assertEqual(self.vs2.display.height, 54)
        director.extra_buttons = 0x20
        self.assertTrue(joy2.held(BACK))
        self.assertFalse(joy1.held(BACK))
        director.extra_buttons = 0x04
        self.assertTrue(joy1.held(START))
        self.vs2.audio.sound("shoot")
        self.vs2.audio.music("theme", loop=True)
        self.vs2.audio.stop_music()
        self.assertEqual(director.platform.comms.sent[-3:], [
            (b"sound games.test_vs2/shoot", b""),
            (b"music games.test_vs2/theme loop", b""),
            (b"music off", b""),
        ])

    def test_scene_builds_owned_drawables_then_seals(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.world = self.layer("world", projection=vs2.TUNNEL)
                self.ship = self.world.sprite("ship.png", x=12.5, y=-0.25, visible=False)

            def update(self):
                self.ship.frame = 1

        game = self.enter(Game())
        self.assertEqual(game._phase, "sealed")
        self.assertIs(game.ship.layer, game.world)
        self.assertFalse(game.ship.visible)
        game.ship.frame = 2
        self.assertFalse(game.ship.visible, "preloading a hidden frame must not show it")
        with self.assertRaises(vs2.SceneSealedError):
            game.world.sprite("ship.png")
        with self.assertRaises(TypeError):
            vs2.Sprite()
        director.step_once()
        self.assertFalse(game.ship.visible)
        self.assertEqual(game.ship.frame, 1)

    def test_pool_is_fixed_and_supports_current_despawn_iteration(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                layer = self.layer("world")
                self.pool = layer.sprite_pool("ship.png", count=2, frame=0)

        game = self.enter(Game())
        first = game.pool.spawn(1, 2)
        second = game.pool.spawn(3, 4, frame=1)
        self.assertEqual((len(game.pool), game.pool.free), (2, 0))
        self.assertIsNone(game.pool.spawn(0, 0))
        seen = []
        for sprite in game.pool:
            seen.append(sprite)
            game.pool.despawn(sprite)
        self.assertEqual(set(seen), {first, second})
        self.assertEqual((len(game.pool), game.pool.free), (0, 2))

    def test_image_metadata_validates_frames_and_tile_dimensions(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.layer_ = self.layer("world")
                self.ship = self.layer_.sprite("ship.png")
                self.map = self.layer_.tilemap("terrain.png", columns=2, rows=2)

        game = self.enter(Game())
        self.assertEqual((game.ship.width, game.ship.height, game.ship.image.frames), (8, 8, 4))
        self.assertEqual((game.map.tile_width, game.map.tile_height), (16, 8))
        with self.assertRaises(vs2.FrameError):
            game.ship.frame = 4
        with self.assertRaises(vs2.AssetNotFoundError):
            game.image("missing.png")

    def test_tilemap_cells_scalar_view_and_label_writes(self):
        vs2 = self.vs2
        self.runtime_director.platform.sprites.stripes[stripes["font.png"]]["frames"] = 128

        class Game(vs2.Scene):
            def build(self):
                layer = self.layer("hud", projection=vs2.HUD)
                self.map = layer.tilemap("terrain.png", columns=2, rows=2,
                                         view_width=vs2.display.width, view_height=16)
                self.label = layer.label("font.png", columns=3, glyphs="0123")

        game = self.enter(Game())
        game.map[1, 0] = 3
        self.assertEqual(game.map[1, 0], 3)
        game.map.view_y = 4
        self.assertEqual(game.map.view_y, 4)
        game.label.write(0, 0, "12")
        self.assertEqual(list(game.label.cells), [vs2.EMPTY_TILE, 2, 1])
        game.label.set_number(23, width=2, pad="0")
        self.assertEqual(list(game.label.cells)[1:], [3, 2])

    def test_payload_v3_preserves_sprite_tilemap_interleaving_and_reuses_buffer(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                layer = self.layer("world")
                self.ground = layer.tilemap("terrain.png", columns=1, rows=1)
                self.ship = layer.sprite("ship.png", x=1)
                self.clouds = layer.tilemap("terrain.png", columns=1, rows=1)

        game = self.enter(Game())
        first = vs2.export_scene_payload(game)
        second = vs2.export_scene_payload(game)
        self.assertIs(first, second)
        self.assertEqual(first[4], 3)
        self.assertEqual(first[-6:], bytes((1, 0, 0, 0, 1, 1)))
        game.ship.x = 3
        self.assertIs(vs2.export_scene_payload(game), first)

    def test_limits_are_build_time_diagnostics(self):
        vs2 = self.vs2

        class TooMany(vs2.Scene):
            def build(self):
                layer = self.layer("world")
                for _ in range(vs2.limits.sprites + 1):
                    layer.sprite("ship.png")

        with self.assertRaises(vs2.ResourceLimitError) as error:
            self.enter(TooMany())
        self.assertIn("sprite 101/100", str(error.exception))

    def test_queued_transition_skips_timers_and_reenters_legacy_scene(self):
        vs2 = self.vs2
        calls = []

        class Launcher(LegacyScene):
            def on_enter(self):
                calls.append("launcher")

        class Game(vs2.Scene):
            def build(self):
                self.call_later(0, lambda: calls.append("timer"))

            def update(self):
                calls.append("update")
                self.pop()

        director.push(Launcher())
        self.enter(Game())
        director.step_once()
        self.assertEqual(calls, ["launcher", "update", "launcher"])

    def test_v1_and_v2_still_cannot_mix(self):
        reset_runtime()
        api_guard.reset()
        configure_runtime("headless")
        api_guard.begin_app("games.legacy")
        from ventilastation.sprites import Sprite
        Sprite()
        with self.assertRaises(ImportError):
            self.vs2.Scene()


if __name__ == "__main__":
    unittest.main()
