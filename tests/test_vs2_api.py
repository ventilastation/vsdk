import os
import struct
import sys
import time
import tracemalloc
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
        self.runtime_director.platform.sprites.stripes[
            stripes["font.png"]
        ]["glyphs"] = ""

        class Game(vs2.Scene):
            def build(self):
                layer = self.layer("hud", projection=vs2.HUD)
                self.map = layer.tilemap("terrain.png", columns=2, rows=2,
                                         view_width=vs2.display.width, view_height=16)
                self.label = layer.label("font.png", columns=3, glyphs="0123")
                self.cp437 = layer.label("font.png", columns=3, text="A1")

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
        self.assertEqual(game.cp437.text, "A1")
        self.assertEqual(
            list(game.cp437.cells),
            [vs2.EMPTY_TILE, ord("1"), ord("A")],
        )
        with self.assertRaises(AttributeError):
            game.map.columns = 3
        with self.assertRaises(AttributeError):
            game.map.cells = bytearray(4)
        with self.assertRaises(BufferError):
            game.map.cells.append(1)

    def test_tilemap_and_label_flips_round_trip_through_payload(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                layer = self.layer("hud", projection=vs2.HUD)
                self.map = layer.tilemap(
                    "terrain.png", columns=1, rows=1, flip_x=True)
                self.label = layer.label(
                    "font.png", columns=3, text="123", flip_y=True)

        game = self.enter(Game())
        self.assertTrue(game.map.flip_x)
        self.assertFalse(game.map.flip_y)
        self.assertFalse(game.label.flip_x)
        self.assertTrue(game.label.flip_y)

        payload = vs2.export_scene_payload(game)
        tilemap_offset = 16 + 8
        self.assertEqual(payload[tilemap_offset + 2], vs2.FLAG_VISIBLE | vs2.FLAG_FLIP_X)
        self.assertEqual(
            payload[tilemap_offset + 32 + 2],
            vs2.FLAG_VISIBLE | vs2.FLAG_FLIP_Y,
        )

        game.map.flip_y = True
        game.label.flip_x = True
        self.assertIs(vs2.export_scene_payload(game), payload)
        self.assertEqual(payload[tilemap_offset + 2], 7)
        self.assertEqual(payload[tilemap_offset + 32 + 2], 7)

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

    # -- T3: the behaviors init-surface --------------------------------------

    def test_done_sentinel_and_behaviors_limit_exist(self):
        vs2 = self.vs2
        self.assertIsNot(vs2.DONE, None)
        self.assertIs(vs2.DONE, vs2.DONE)
        self.assertEqual(vs2.limits.behaviors, 32)

    def test_vs2_store_export_is_the_store_module_singleton(self):
        # `vs2.store` is deliberately rebound (by `from .store import store`
        # in vs2/__init__.py) to the singleton itself, not the submodule --
        # so reach the submodule through sys.modules to compare identity.
        store_submodule = sys.modules["vs2.store"]
        self.assertIs(self.vs2.store, store_submodule.store)

    def test_sprite_despawn_is_pool_despawn_and_rejects_standalone(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                world = self.layer("world")
                self.pool = world.sprite_pool("ship.png", count=1)
                self.lone = world.sprite("ship.png")

        game = self.enter(Game())
        shot = game.pool.spawn(1, 2)
        shot.despawn()
        self.assertEqual(len(game.pool), 0)
        with self.assertRaises(ValueError):
            game.lone.despawn()

    def test_dx_dy_accumulate_and_commit_once_per_pool_per_tick(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            idle_timeout = None

            def build(self):
                self.pool = self.layer("world").sprite_pool("ship.png", count=1)

        game = self.enter(Game())
        shot = game.pool.spawn(10, 20)
        shot.dx = 3
        shot.dy = -1
        game.scene_step()
        self.assertEqual((shot.x, shot.y), (13, 19))
        self.assertEqual((shot.dx, shot.dy), (0, 0))
        # Untouched dx/dy costs nothing and moves nothing further.
        game.scene_step()
        self.assertEqual((shot.x, shot.y), (13, 19))

    def test_pool_var_primes_every_sprite_and_resets_on_spawn(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.pool = self.layer("world").sprite_pool("ship.png", count=2)
                self.pool.var("hp", 3, min=0, max=9)

        game = self.enter(Game())
        self.assertEqual([sprite.hp for sprite in game.pool._free], [3, 3])
        shot = game.pool.spawn(0, 0)
        self.assertEqual(shot.hp, 3)
        shot.hp = 0
        game.pool.despawn(shot)
        respawned = game.pool.spawn(0, 0)
        self.assertIs(respawned, shot)
        self.assertEqual(respawned.hp, 3, "spawn() must reset declared variables")

    def test_pool_var_rejects_duplicate_and_reserved_names(self):
        vs2 = self.vs2

        class Dup(vs2.Scene):
            def build(self):
                pool = self.layer("world").sprite_pool("ship.png", count=1)
                pool.var("hp", 1)
                pool.var("hp", 2)

        with self.assertRaises(ValueError):
            self.enter(Dup())

        class Reserved(vs2.Scene):
            def build(self):
                pool = self.layer("world").sprite_pool("ship.png", count=1)
                pool.var("dx", 0)

        with self.assertRaises(ValueError):
            self.enter(Reserved())

    def test_pool_kinds_applies_named_row_and_rejects_unknown_kind(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                # A third, unspent slot so the "unknown kind" spawn below
                # exercises the kind lookup rather than pool exhaustion.
                self.pool = self.layer("world").sprite_pool("ship.png", count=3)
                self.pool.var("hp", 1)
                self.pool.var("score", 10)
                self.pool.kinds(driller=(3, 75), chiller=(1, 40))

        game = self.enter(Game())
        driller = game.pool.spawn(0, 0, kind="driller")
        self.assertEqual((driller.hp, driller.score), (3, 75))
        chiller = game.pool.spawn(0, 0, kind="chiller")
        self.assertEqual((chiller.hp, chiller.score), (1, 40))
        with self.assertRaises(ValueError):
            game.pool.spawn(0, 0, kind="boss")

    def test_pool_kinds_rejects_bad_arity_and_a_second_call(self):
        vs2 = self.vs2

        class BadArity(vs2.Scene):
            def build(self):
                pool = self.layer("world").sprite_pool("ship.png", count=1)
                pool.var("hp", 1)
                pool.kinds(driller=(1, 2))  # hp is the pool's only variable

        with self.assertRaises(ValueError):
            self.enter(BadArity())

        class CalledTwice(vs2.Scene):
            def build(self):
                pool = self.layer("world").sprite_pool("ship.png", count=1)
                pool.var("hp", 1)
                pool.kinds(driller=(1,))
                pool.kinds(chiller=(2,))

        with self.assertRaises(ValueError):
            self.enter(CalledTwice())

    def test_pool_capacity_is_the_fixed_total_budget(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.world = self.layer("world")
                self.pool = self.world.sprite_pool("ship.png", count=3)

        game = self.enter(Game())
        self.assertEqual(game.pool.capacity, 3)
        game.pool.spawn(0, 0)
        self.assertEqual(game.pool.capacity, 3)
        self.assertIs(game.pool.layer, game.world)

    def test_scene_var_declares_primes_and_resets_on_rebuild(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.var("score", 0, min=0, max=999999)
                self.layer("world")

        game = self.enter(Game())
        self.assertEqual(game.score, 0)
        game.score = 42
        director.pop()
        game2 = self.enter(Game())
        self.assertEqual(game2.score, 0, "var() must reset fresh on every build()")

    def test_scene_var_rejects_duplicate_and_reserved_names(self):
        vs2 = self.vs2

        class Dup(vs2.Scene):
            def build(self):
                self.var("score", 0)
                self.var("score", 1)

        with self.assertRaises(ValueError):
            self.enter(Dup())

        class Reserved(vs2.Scene):
            def build(self):
                self.var("enabled", True)

        with self.assertRaises(ValueError):
            self.enter(Reserved())

    def test_family_groups_same_layer_members_and_is_not_iterable(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.world = self.layer("world")
                self.enemies = self.world.sprite_pool("ship.png", count=2)
                self.boss = self.world.sprite("ship.png")
                self.hostiles = self.family(self.enemies, self.boss)

        game = self.enter(Game())
        self.assertEqual(game.hostiles.members, (game.enemies, game.boss))
        self.assertEqual(len(game.hostiles), 2)
        self.assertIs(game.hostiles.layer, game.world)
        with self.assertRaises(TypeError):
            for _ in game.hostiles:
                pass

    def test_family_rejects_cross_layer_members_and_bad_types(self):
        vs2 = self.vs2

        class CrossLayer(vs2.Scene):
            def build(self):
                a = self.layer("a").sprite_pool("ship.png", count=1)
                b = self.layer("b").sprite_pool("ship.png", count=1)
                self.family(a, b)

        with self.assertRaises(ValueError):
            self.enter(CrossLayer())

        class BadMember(vs2.Scene):
            def build(self):
                pool = self.layer("world").sprite_pool("ship.png", count=1)
                self.family(pool, "not a sprite")

        with self.assertRaises(TypeError):
            self.enter(BadMember())

    def test_layer_cannot_be_named_scene(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.layer("scene")

        with self.assertRaises(ValueError):
            self.enter(Game())

    def test_project_var_declares_once_and_wires_persist_to_store(self):
        vs2 = self.vs2
        # A module-level singleton outlives one test; scope this test's own
        # bookkeeping so it never collides with another test or run.
        vs2.project._vars = {}
        vs2.project._persisted = set()
        with mock.patch.object(vs2.store, "get", return_value=55) as get:
            value = vs2.project.var("hiscore_t3", 0, persist=True)
        get.assert_called_once_with("hiscore_t3", 0)
        self.assertEqual(value, 55)
        self.assertEqual(vs2.project.hiscore_t3, 55)
        with mock.patch.object(vs2.store, "get") as get_again:
            self.assertEqual(vs2.project.var("hiscore_t3", 999), 55,
                             "a second var() call is a no-op returning the current value")
        get_again.assert_not_called()
        vs2.project.hiscore_t3 = 77
        # Special methods are looked up on the type for `obj[k] = v`
        # syntax, so the mock has to go on the class, not the instance.
        with mock.patch.object(type(vs2.store), "__setitem__") as setitem, \
             mock.patch.object(vs2.store, "save") as save:
            vs2.project.save()
        setitem.assert_called_once_with("hiscore_t3", 77)
        save.assert_called_once()

    def test_project_var_rejects_reserved_names(self):
        vs2 = self.vs2
        vs2.project._vars = {}
        vs2.project._persisted = set()
        with self.assertRaises(ValueError):
            vs2.project.var("fsm_state", 0)

    def test_layer_camera_defaults_and_is_writable_until_closed(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.world = self.layer("world")

        game = self.enter(Game())
        self.assertEqual((game.world.camera_x, game.world.camera_y), (0, 0))
        game.world.camera_x = 12.5
        game.world.camera_y = 3
        self.assertEqual((game.world.camera_x, game.world.camera_y), (12.5, 3))
        director.pop()
        with self.assertRaises(vs2.SceneSealedError):
            game.world.camera_x = 1

    def test_layer_projection_accepts_a_curve_without_changing_the_mode(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.hud = self.layer("hud", projection=vs2.HUD)
                self.world = self.layer("world", projection=vs2.TUNNEL)

        game = self.enter(Game())
        custom = vs2.tunnel(gamma=1.0)
        game.hud.projection = custom
        # Assigning a curve never changes the wire-format mode: every
        # native call, payload byte and `== vs2.HUD`-style check must keep
        # working exactly as it did in revision 2.
        self.assertEqual(game.hud.projection, vs2.HUD)
        self.assertEqual(game.hud.to_row(128), custom[128])
        # Reverting to a classic mode resets the curve to that mode's own
        # default.
        game.hud.projection = vs2.HUD
        self.assertEqual(game.hud.to_row(128), vs2.projection.HUD[128])

        game.world.projection = custom
        self.assertEqual(game.world.projection, vs2.TUNNEL)
        self.assertEqual(game.world.to_row(200), custom[200])

        with self.assertRaises(ValueError):
            game.world.projection = bytes(255)  # not 256 bytes

    def test_layer_to_depth_to_row_agree_with_the_default_curve(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.world = self.layer("world", projection=vs2.TUNNEL)

        game = self.enter(Game())
        self.assertEqual(game.world.to_row(0), vs2.VS1_TUNNEL[0])
        self.assertEqual(game.world.to_row(255), vs2.VS1_TUNNEL[255])
        for row in (0, 10, 53, 128, 255):
            depth = game.world.to_depth(row)
            self.assertEqual(game.world.to_row(depth), game.world.to_row(depth))

    def test_layer_polar_matches_the_disc_angle_convention(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.world = self.layer("world")

        game = self.enter(Game())
        width = vs2.display.width
        for (x, y), expected_angle in (
            ((0, -1), 0), ((-1, 0), width // 4),
            ((0, 1), width // 2), ((1, 0), 3 * width // 4),
        ):
            angle, depth = game.world.polar(x, y)
            self.assertAlmostEqual(angle % width, expected_angle, places=3)
            self.assertAlmostEqual(depth, 1.0, places=6)

    def test_behave_defaults_name_to_snake_case_and_reads_back(self):
        vs2 = self.vs2

        class Patrolling:
            pass

        class Game(vs2.Scene):
            def build(self):
                self.pool = self.layer("world").sprite_pool("ship.png", count=1)
                self.attached = self.pool.behave(Patrolling())

        game = self.enter(Game())
        self.assertIs(game.pool.behavior("patrolling"), game.attached)
        self.assertIs(game.pool.behavior(Patrolling), game.attached)
        self.assertEqual(game.pool.behaviors, (game.attached,))

    def test_behave_rejects_name_collision_on_one_subject(self):
        vs2 = self.vs2

        class Thing:
            pass

        class Game(vs2.Scene):
            def build(self):
                pool = self.layer("world").sprite_pool("ship.png", count=1)
                pool.behave(Thing())
                pool.behave(Thing())  # same default name "thing" twice

        with self.assertRaises(ValueError):
            self.enter(Game())

    def test_behave_is_structural_only_legal_in_build(self):
        vs2 = self.vs2

        class Thing:
            pass

        class Game(vs2.Scene):
            def build(self):
                self.pool = self.layer("world").sprite_pool("ship.png", count=1)

        game = self.enter(Game())
        with self.assertRaises(vs2.SceneSealedError):
            game.pool.behave(Thing())

    def test_behave_on_a_stale_handle_from_a_closed_scene_raises_cleanly(self):
        # A closed scene nulls a Sprite's own _layer and a Layer's own
        # .scene; behave() must not crash with a raw AttributeError when a
        # stale handle is used after the scene has gone away.
        vs2 = self.vs2

        class Thing:
            pass

        class Game(vs2.Scene):
            def build(self):
                self.world = self.layer("world")
                self.pool = self.world.sprite_pool("ship.png", count=1)
                self.ship = self.world.sprite("ship.png")

        game = self.enter(Game())
        director.pop()
        with self.assertRaises(vs2.SceneSealedError):
            game.ship.behave(Thing())
        with self.assertRaises(vs2.SceneSealedError):
            game.pool.behave(Thing())

    def test_scene_behaviors_lists_every_attachment_scene_wide_in_order(self):
        vs2 = self.vs2

        class A:
            pass

        class B:
            pass

        class Game(vs2.Scene):
            def build(self):
                self.world = self.layer("world")
                self.pool = self.world.sprite_pool("ship.png", count=1)
                self.ship = self.world.sprite("ship.png")
                self.a = self.pool.behave(A())
                self.b = self.ship.behave(B())
                self.c = self.behave(A(), name="scene_a")

        game = self.enter(Game())
        self.assertEqual(game.behaviors, (game.a, game.b, game.c))
        # scene.behaviors is scene-wide; scene.behavior() is scene-owned only.
        self.assertIs(game.behavior("scene_a"), game.c)
        self.assertIsNone(game.behavior("a"))

    def test_behavior_pass_dispatches_by_subject_kind_in_attach_order(self):
        vs2 = self.vs2
        calls = []

        class PoolBehavior:
            def step(self, pool):
                calls.append(("pool", pool))

        class SpriteBehavior:
            def step_one(self, sprite):
                calls.append(("sprite", sprite))

        class SceneBehavior:
            def step_scene(self, scene):
                calls.append(("scene", scene))

        class FamilyBehavior:
            def step(self, pool):
                calls.append(("family-pool", pool))

            def step_one(self, sprite):
                calls.append(("family-sprite", sprite))

        class Game(vs2.Scene):
            idle_timeout = None

            def build(self):
                self.world = self.layer("world")
                self.pool = self.world.sprite_pool("ship.png", count=1)
                self.ship = self.world.sprite("ship.png")
                self.other = self.world.sprite("ship.png")
                self.pool.behave(PoolBehavior())
                self.ship.behave(SpriteBehavior())
                self.family_ = self.family(self.pool, self.other)
                self.family_.behave(FamilyBehavior())
                self.behave(SceneBehavior())

        game = self.enter(Game())
        game.scene_step()
        self.assertEqual(calls, [
            ("pool", game.pool),
            ("sprite", game.ship),
            ("family-pool", game.pool),
            ("family-sprite", game.other),
            ("scene", game),
        ])

    def test_behavior_pass_skipped_when_update_queues_a_transition(self):
        vs2 = self.vs2
        calls = []

        class Loud:
            def step_scene(self, scene):
                calls.append("ran")

        class Launcher(LegacyScene):
            pass

        class Game(vs2.Scene):
            idle_timeout = None

            def build(self):
                self.behave(Loud())

            def update(self):
                self.pop()

        director.push(Launcher())
        game = self.enter(Game())
        game.scene_step()
        self.assertEqual(calls, [], "update()'s queued pop must skip the whole pass")

    def test_behavior_pass_stops_immediately_when_a_behavior_queues_one(self):
        vs2 = self.vs2
        calls = []

        class PopsThenScene:
            def step_scene(self, scene):
                calls.append("first")
                scene.pop()

        class NeverRuns:
            def step_scene(self, scene):
                calls.append("second")

        class Launcher(LegacyScene):
            pass

        class Game(vs2.Scene):
            idle_timeout = None

            def build(self):
                self.behave(PopsThenScene())
                self.behave(NeverRuns(), name="second")

        director.push(Launcher())
        game = self.enter(Game())
        game.scene_step()
        self.assertEqual(calls, ["first"])

    def test_tilemap_cell_at_resolves_point_or_returns_none(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.map = self.layer("world").tilemap(
                    "terrain.png", columns=2, rows=2, x=0, y=0)

        game = self.enter(Game())
        tile_w, tile_h = game.map.tile_width, game.map.tile_height
        self.assertEqual(game.map.cell_at(0, 0), (0, 0))
        self.assertEqual(game.map.cell_at(tile_w, 0), (1, 0))
        self.assertEqual(game.map.cell_at(0, tile_h), (0, 1))
        self.assertIsNone(game.map.cell_at(0, -1))
        self.assertIsNone(game.map.cell_at(0, tile_h * 2))
        # X wraps circularly, like every other X coordinate in VS2.
        self.assertEqual(game.map.cell_at(-vs2.display.width, 0), (0, 0))

    def test_payload_layer_record_reserved_bytes_carry_camera_and_curve(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.world = self.layer("world", projection=vs2.TUNNEL)

        game = self.enter(Game())
        payload = vs2.export_scene_payload(game)
        layer_offset = 16
        # Untouched: byte-identical to revision 2 (index, mode, flags, then
        # five reserved zero bytes) -- no camera, default curve.
        self.assertEqual(list(payload[layer_offset:layer_offset + 8]),
                         [0, vs2.TUNNEL, vs2.FLAG_VISIBLE, 0, 0, 0, 0, 0])

        game.world.camera_x = 12
        game.world.camera_y = 200
        game.world.projection = vs2.tunnel(gamma=1.0)
        payload = vs2.export_scene_payload(game)
        record = payload[layer_offset:layer_offset + 8]
        self.assertEqual(record[3], 12)
        self.assertEqual(record[4], 200)
        self.assertEqual(record[5], 1, "the first custom curve gets index 1, not 0")
        self.assertEqual(bytes(record[6:8]), b"\x00\x00")

    def test_scene_step_allocates_nothing_new_for_a_plain_scene(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            idle_timeout = None
            back_button = False

            def build(self):
                self.world = self.layer("world")
                self.pool = self.world.sprite_pool("ship.png", count=4)
                self.ship = self.world.sprite("ship.png")
                for _ in range(3):
                    self.pool.spawn(0, 0)

            def update(self):
                self.ship.x += 0.5

        game = self.enter(Game())
        for _ in range(50):
            game.scene_step()  # warm up any one-time caches
        tracemalloc.start()
        try:
            for _ in range(200):
                game.scene_step()
            current, _peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(current, 0,
                         "a scene using none of the new API must retain no "
                         "allocation from the commit pass or the Behavior pass")


if __name__ == "__main__":
    unittest.main()
