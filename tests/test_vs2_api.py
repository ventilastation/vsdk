import os
import struct
import sys
import time
import unittest
from unittest import mock

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
        self.runtime_director.buttons = 0
        self.runtime_director.last_buttons = 0
        self.runtime_director.buttons2 = 0
        self.runtime_director.last_buttons2 = 0
        self.runtime_director.extra_buttons = 0
        self.runtime_director.last_extra_buttons = 0
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
        self.assertEqual(self.runtime_director.extra_buttons, 0x20)
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
        director.palette_data = bytearray(b"palette")
        self.vs2.display.apply_palettes()
        self.assertIs(director.platform.display.palette, director.palette_data)

        exported = {}
        exec("from vs2.controls import *\nexported = (LEFT, joy1, BACK)", {}, exported)
        self.assertEqual(exported["exported"][0], 1)

    def test_base_commands_validate_and_deduplicate(self):
        base = self.vs2.base
        self.vs2.reset_runtime_state()
        sent = self.runtime_director.platform.comms.sent
        base.leds.set_all(1, 2, 3)
        base.leds.set_all(1, 2, 3)
        base.leds.off()
        base.servo.set(128)
        base.servo.set(128)
        base.buttons.set(base.BUTTON_LED_ALL, blink_ms=50)
        base.buttons.set(base.BUTTON_LED_ALL, blink_ms=50)
        base.buttons.off()
        self.assertEqual(sent, [
            (b"base leds 1 2 3", b""),
            (b"base leds 0 0 0", b""),
            (b"base servo 128", b""),
            (b"base buttons 3 50", b""),
            (b"base buttons 0 0", b""),
        ])
        with self.assertRaisesRegex(ValueError, "red must be in 0..255"):
            base.leds.set_all(-1, 0, 0)
        with self.assertRaisesRegex(ValueError, "position must be in 0..255"):
            base.servo.set(256)
        with self.assertRaisesRegex(ValueError, "mask must be in 0..3"):
            base.buttons.set(4)
        with self.assertRaisesRegex(ValueError, "blink_ms must be in 0..10000"):
            base.buttons.set(0, blink_ms=10001)

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

    def test_small_game_happy_path_mutates_its_sealed_graph(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            idle_timeout = None
            back_button = False

            def build(self):
                self.world = self.layer("world")
                self.ship = self.world.sprite("ship.png")
                self.pool = self.world.sprite_pool("ship.png", count=1)
                self.map = self.world.tilemap("terrain.png", columns=2, rows=1)

        game = self.enter(Game())
        game.ship.image = "terrain.png"
        self.assertEqual(game.ship.image.name, "terrain.png")
        game.world.visible = False
        self.assertFalse(game.world.visible)
        game.world.visible = True
        game.world.projection = vs2.HUD
        self.assertEqual(game.world.projection, vs2.HUD)
        game.world.projection = vs2.TUNNEL
        game.map.fill(2)
        self.assertEqual(list(game.map.cells), [2, 2])
        game.map.y = 3
        game.map.view_x = 1
        self.assertEqual((game.map.y, game.map.view_x), (3, 1))
        game.map.visible = False
        self.assertFalse(game.map.visible)
        game.map.show()
        self.assertTrue(game.map.visible)
        game.map.hide()
        self.assertFalse(game.map.visible)
        game.map.show()
        game.ship.hide()
        self.assertFalse(game.ship.visible)
        game.ship.show()
        self.assertTrue(game.ship.visible)
        game.pool.spawn(4, 5)
        game.pool.despawn_all()
        self.assertEqual((len(game.pool), game.pool.free), (0, 1))
        director.buttons = 0
        director.last_buttons = vs2.controls.LEFT
        self.assertTrue(vs2.controls.joy1.just_released(vs2.controls.LEFT))

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

        class Recycling(vs2.Scene):
            def build(self):
                self.pool = self.layer("world").sprite_pool(
                    "ship.png", count=1, on_empty=vs2.RECYCLE)

        recycling = self.enter(Recycling())
        oldest = recycling.pool.spawn(1, 2)
        self.assertIs(recycling.pool.spawn(3, 4), oldest)
        self.assertEqual((oldest.x, oldest.y, len(recycling.pool)), (3, 4, 1))
        recycling.pool.despawn_all()
        self.assertEqual((len(recycling.pool), recycling.pool.free), (0, 1))

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
        game.label.text = "12"
        self.assertEqual(game.label.text, "12")
        game.label.text += "3"
        self.assertEqual(game.label.text, "123")
        game.label.text = " 1"
        self.assertEqual(game.label.cells[2], vs2.EMPTY_TILE)
        with self.assertRaises(AttributeError):
            game.map.columns = 3
        with self.assertRaises(AttributeError):
            game.map.cells = bytearray(4)
        with self.assertRaises(BufferError):
            game.map.cells.append(1)

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

    def test_layer_order_wins_over_allocation_order_and_layout_is_sealed(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.world = self.layer("world", projection=vs2.TUNNEL)
                self.hud = self.layer("hud", projection=vs2.HUD)
                self.badge = self.hud.sprite("ship.png")
                self.ship = self.world.sprite("ship.png")

        game = self.enter(Game())
        payload = vs2.export_scene_payload(game)
        sprite_offset = 16 + 2 * 8
        self.assertEqual(payload[sprite_offset], 0)
        self.assertEqual(payload[sprite_offset + 24], 1)
        self.assertEqual(payload[-4:], bytes((0, 0, 0, 1)))
        self.assertIs(game._payload_sprites, game._payload_sprites)
        self.assertIs(game._payload_drawables, game._payload_drawables)

    def test_native_backend_receives_layer_major_draw_order_after_seal(self):
        vs2 = self.vs2

        class Record:
            def set_x_fixed(self, _value): pass
            def set_y_fixed(self, _value): pass
            def set_strip(self, _value): pass
            def set_frame(self, _value): pass
            def set_perspective(self, _value): pass
            def set_flags(self, _value): pass
            def set_layer(self, _value): pass
            def set_viewport(self, *_values): pass

        class Native:
            def __init__(self):
                self.order = None

            class Layer:
                def __init__(self, **_kwargs): pass
                def set_mode(self, _value): pass
                def set_visible(self, _value): pass

            def Sprite(self):
                return Record()

            def Tilemap(self, **_kwargs):
                return Record()

            def reset_scene(self): pass
            def set_active(self, _active): pass
            def set_draw_order(self, drawables): self.order = drawables

        native = Native()

        class Game(vs2.Scene):
            def build(self):
                world = self.layer("world")
                hud = self.layer("hud", projection=vs2.HUD)
                self.badge = hud.sprite("ship.png")
                self.ship = world.sprite("ship.png")

        with mock.patch.object(vs2, "_vs2_backend", return_value=native):
            game = self.enter(Game())
        self.assertEqual(native.order, (game.ship._sprite, game.badge._sprite))

    def test_old_hardware_without_ordered_draw_api_fails_loudly(self):
        vs2 = self.vs2

        class OldNative:
            def reset_scene(self): pass
            def set_active(self, _active): pass

        class Game(vs2.Scene):
            def build(self):
                pass

        with mock.patch.object(vs2, "_vs2_backend", return_value=OldNative()):
            with self.assertRaisesRegex(RuntimeError,
                                        "this firmware is too old for VS2 revision 2"):
                self.enter(Game())

    def test_limits_are_build_time_diagnostics(self):
        vs2 = self.vs2

        class TooMany(vs2.Scene):
            def build(self):
                world = self.layer("world")
                hud = self.layer("hud", projection=vs2.HUD)
                for _ in range(60):
                    world.sprite("ship.png")
                for _ in range(41):
                    hud.sprite("ship.png")

        with self.assertRaises(vs2.ResourceLimitError) as error:
            self.enter(TooMany())
        self.assertIn("sprite 101/100", str(error.exception))
        self.assertIn("world: 60, hud: 41", str(error.exception))

    def test_asset_limit_is_checked_before_build(self):
        vs2 = self.vs2
        stripes.clear()
        for index in range(vs2.limits.image_strips + 1):
            stripes["image%d.png" % index] = index

        class TooManyImages(vs2.Scene):
            def build(self):
                raise AssertionError("build must not run with an oversized asset bank")

        with self.assertRaises(vs2.AssetLimitError) as error:
            self.enter(TooManyImages())
        self.assertIn("defines 101 images; this target supports 100", str(error.exception))

    def test_asset_pack_is_loaded_before_build(self):
        vs2 = self.vs2

        class Packed(vs2.Scene):
            asset_pack = "other"

            def build(self):
                self.layer("world")

        with mock.patch.object(director, "load_rom") as load_rom:
            self.enter(Packed())
        load_rom.assert_called_once_with("roms/other.rom")

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

    def test_idle_back_switch_and_timer_defaults(self):
        vs2 = self.vs2
        calls = []

        class Replacement(vs2.Scene):
            def build(self):
                calls.append("replacement")

        class Game(vs2.Scene):
            idle_timeout = 0

            def build(self):
                self.layer("world").sprite("ship.png")

            def on_idle(self):
                calls.append("idle")

        game = self.enter(Game())
        self.assertGreaterEqual(int(vs2.controls.idle_ms), 0)
        game._run_defaults()
        self.assertEqual(calls, ["idle"])
        game._pending_transition = None
        game.idle_timeout = None
        director.extra_buttons = 0x08
        director.last_extra_buttons = 0
        game._run_defaults()
        self.assertEqual(game._pending_transition[0], "pop")
        game._pending_transition = None

        vs2.audio.music("theme", loop=True)
        game.switch(Replacement())
        game._commit_transition()
        self.assertIsInstance(director.scene_stack[-1], Replacement)
        self.assertNotIn((b"music off", b""), director.platform.comms.sent[-1:])

    def test_idle_default_pops_and_back_button_can_be_claimed(self):
        vs2 = self.vs2
        idle_calls = []

        class Launcher(LegacyScene):
            pass

        class IdleGame(vs2.Scene):
            idle_timeout = 0
            back_button = False

            def build(self):
                self.layer("world")

        class ClaimsBack(vs2.Scene):
            idle_timeout = None
            back_button = False

            def build(self):
                self.layer("world")

        launcher = Launcher()
        director.push(launcher)
        idle_game = self.enter(IdleGame())
        original_on_idle = vs2.Scene.on_idle

        def trace_on_idle(scene):
            idle_calls.append(scene)
            return original_on_idle(scene)

        vs2.Scene.on_idle = trace_on_idle
        try:
            idle_game._run_defaults()
        finally:
            vs2.Scene.on_idle = original_on_idle
        self.assertEqual(idle_calls, [idle_game])
        self.assertEqual(idle_game._pending_transition, ("pop", None))
        idle_game._commit_transition()
        self.assertIs(director.scene_stack[-1], launcher)

        claims_back = self.enter(ClaimsBack())
        director.buttons = 0
        director.last_buttons = 0
        director.extra_buttons = 0x08
        director.last_extra_buttons = 0
        claims_back._run_defaults()
        self.assertIsNone(claims_back._pending_transition)

    def test_push_exits_current_scene_and_discards_its_timers(self):
        vs2 = self.vs2
        fired = []

        class Child(vs2.Scene):
            idle_timeout = None

            def build(self):
                self.layer("child")

        class Parent(vs2.Scene):
            idle_timeout = None

            def build(self):
                self.layer("parent")
                self.call_later(10000, lambda: fired.append("old timer"))

        parent = self.enter(Parent())
        queued = parent.pending_calls[0]
        child = Child()
        parent.push(child)
        parent._commit_transition()
        self.assertIs(director.scene_stack[-1], child)
        self.assertEqual(parent.pending_calls, [])
        self.assertNotIn(queued, parent.pending_calls)
        self.assertEqual(fired, [])

    def test_timers_sort_across_ticks_wraparound(self):
        vs2 = self.vs2
        calls = []

        class Game(vs2.Scene):
            def build(self):
                self.layer("world").sprite("ship.png")

        game = self.enter(Game())

        class WrappedTicks:
            now = 95

            @classmethod
            def ticks_ms(cls):
                return cls.now

            @staticmethod
            def ticks_add(value, delta):
                return (value + delta) % 100

            @staticmethod
            def ticks_diff(end, start):
                value = (end - start) % 100
                return value - 100 if value >= 50 else value

        original_utime = vs2.utime
        vs2.utime = WrappedTicks
        try:
            game.call_later(20, lambda: calls.append("later"))
            game.call_later(5, lambda: calls.append("first"))
            WrappedTicks.now = 0
            game._drain_timers()
            self.assertEqual(calls, ["first"])
            WrappedTicks.now = 15
            game._drain_timers()
            self.assertEqual(calls, ["first", "later"])
        finally:
            vs2.utime = original_utime

    def test_closed_drawables_reject_mutation_and_y_is_not_circular(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                layer = self.layer("world")
                self.one = layer.sprite("ship.png", x=0, y=8)
                self.two = layer.sprite("ship.png", x=250, y=-8)
                self.three = layer.sprite("ship.png", x=1, y=8)
                self.map = layer.tilemap("terrain.png", columns=1, rows=1)

        game = self.enter(Game())
        self.assertFalse(game.one.overlaps(game.two))
        self.assertIs(game.one.first_overlap((game.two, game.three)), game.three)
        director.pop()
        with self.assertRaises(vs2.SceneSealedError):
            game.one.x = 42
        with self.assertRaises(vs2.SceneSealedError):
            game.map.view_y = 2

    def test_api_revision_gate_rejects_unversioned_vs2_before_import(self):
        from ventilastation import app_loader

        with mock.patch.object(app_loader, "app_exists", return_value=True), \
             mock.patch.object(app_loader, "app_metadata", return_value=("test.game", "vs2", None)):
            with self.assertRaisesRegex(ImportError, "needs VS2 API revision 2"):
                app_loader.import_app_module("test.game")

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
