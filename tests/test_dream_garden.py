"""Dream Garden's shared time, bounded garden and voluntary rest flow."""
import importlib.util
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
        ticks_ms = staticmethod(lambda: int(time.time() * 1000))
        ticks_add = staticmethod(lambda value, delta: value + delta)
        ticks_diff = staticmethod(lambda end, start: end - start)
        sleep_ms = staticmethod(lambda ms: time.sleep(ms / 1000.0))
    sys.modules["utime"] = _Utime

import vs2
from vs2.controls import A, B, X, LEFT, RIGHT
from ventilastation import api_guard
from ventilastation.app_loader import load_app
from ventilastation.director import configure_runtime, director, reset_runtime, stripes

STRIPS = {
    "dreamer.png": (19, 19, 8, None),
    "seed.png": (12, 12, 4, None),
    "flowers.png": (17, 17, 8, None),
    "garden.png": (16, 16, 8, None),
    "steel8x8.png": (8, 8, 256, None),
}


class DreamGardenTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        runtime = configure_runtime("headless")
        self.real_load_rom = runtime.load_rom
        stripes.clear()

        def fake_load_rom(_filename):
            for index, (name, (width, height, frames, glyphs)) in enumerate(STRIPS.items()):
                stripes[name] = index
                runtime.platform.sprites.stripes[index] = {
                    "width": width, "height": height, "frames": frames,
                    "palette": 0, "glyphs": glyphs,
                }
        runtime.load_rom = fake_load_rom

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def step(self, player1=0, player2=0, extra=0, count=1):
        for _ in range(count):
            comms = director.platform.comms
            comms.next_joy2 = lambda: player2
            comms.next_extra = lambda: extra
            comms.push_input(bytes([player1]))
            try:
                director.step_once()
            except StopIteration:
                pass

    def start(self, player2=0):
        load_app("demos.dream_garden")
        self.step(A, player2)
        self.step()
        garden = director.scene_stack[-1]
        garden.pending_calls.clear()  # wall-clock timers are checked separately
        return garden

    def start_file(self, path):
        spec = importlib.util.spec_from_file_location("festival_starter", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        scene = module.main()
        scene._vs_api_slug = "demos.dream_garden"
        scene._vs_declared_api = "vs2"
        director.push(scene)
        return scene

    def test_steering_wraps_and_opposites_cancel(self):
        garden = self.start()
        self.assertEqual(garden.dreamer.x, 247)
        self.step(LEFT, count=10)
        self.assertEqual(garden.dreamer.x, 1)
        self.step(RIGHT, count=2)
        self.assertEqual(garden.dreamer.x, 255)
        self.step(LEFT | RIGHT)
        self.assertEqual(garden.dreamer.x, 255)

    def test_second_player_joins_and_moves_independently(self):
        garden = self.start()
        self.assertFalse(garden.friend.visible)
        self.step(LEFT, RIGHT)
        self.assertTrue(garden.joined)
        self.assertTrue(garden.friend.visible)
        self.assertEqual(garden.friend.x, 54)
        self.assertEqual(garden.dreamer.x, 248)
        self.assertEqual(garden.friend.frame, 6)

    def test_player_two_can_start_from_title(self):
        load_app("demos.dream_garden")
        self.step(0, A)
        garden = director.scene_stack[-1]
        self.assertTrue(garden.joined)

    def test_either_player_slows_every_seed_and_the_background(self):
        from games.demos.dream_garden.code.dream_garden import REST_SPEED, REST_SPAWN_MS
        garden = self.start()
        seed = garden.seeds.spawn(x=100, y=100)
        previous_scroll = garden.scroll
        self.step(0, A)
        self.assertAlmostEqual(seed.y, 100 - REST_SPEED, places=2)
        self.assertAlmostEqual(garden.scroll - previous_scroll, REST_SPEED, places=2)
        self.assertEqual(garden.spawn_ms, REST_SPAWN_MS)
        self.assertEqual(garden.mood.text, "REST")
        self.assertEqual(garden.friend.frame, 7)
        self.step()
        self.assertEqual(garden.mood.text, "DRIFT")
        self.step(A)
        self.assertTrue(garden.slow)
        self.assertEqual(garden.dreamer.frame, 3)

    def test_collision_across_the_seam_grows_a_flower(self):
        garden = self.start()
        before = len(list(garden.flowers))
        garden.seeds.spawn(x=254, y=10)
        self.step()
        self.assertEqual(len(list(garden.seeds)), 0)
        self.assertEqual(len(list(garden.flowers)), before + 1)
        self.assertIs(director.scene_stack[-1], garden)

    def test_player_two_also_grows_flowers(self):
        garden = self.start(player2=A)
        before = len(list(garden.flowers))
        garden.seeds.spawn(x=garden.friend.x, y=10)
        self.step()
        self.assertEqual(len(list(garden.flowers)), before + 1)

    def test_missing_a_seed_has_no_penalty(self):
        garden = self.start()
        before = len(list(garden.flowers))
        garden.seeds.spawn(x=100, y=-12)
        self.step()
        self.assertEqual(len(list(garden.seeds)), 0)
        self.assertEqual(len(list(garden.flowers)), before)
        self.assertIs(director.scene_stack[-1], garden)

    def test_full_pools_skip_seeds_and_recycle_flowers(self):
        garden = self.start()
        for _ in range(16):
            self.assertIsNotNone(garden.seeds.spawn(x=100, y=160))
        self.assertIsNone(garden.seeds.spawn(x=100, y=160))
        garden.spawn_seed()
        self.assertEqual(len(list(garden.seeds)), 16)
        self.assertEqual(len(garden.pending_calls), 1)
        garden.seeds.despawn_all()
        for _ in range(80):
            garden.bloom(garden.seeds.spawn(x=0, y=10))
        self.assertEqual(len(list(garden.flowers)), 24)
        self.assertEqual(garden._sprite_count, 42)
        self.assertEqual(garden._tilemap_count, 2)
        vs2.export_scene_payload(garden)

    def test_rest_preserves_the_garden_and_a_begins_a_new_dream(self):
        from games.demos.dream_garden.code.dream_garden import Garden, Rest
        garden = self.start()
        flowers = [(flower.x, flower.frame) for flower in garden.flowers]
        self.step(B)
        rest = director.scene_stack[-1]
        self.assertIsInstance(rest, Rest)
        self.assertEqual(rest.saved_flowers, flowers)
        self.assertEqual(garden.pending_calls, [])
        self.step()
        self.step(0, A)
        self.assertIsInstance(director.scene_stack[-1], Garden)
        self.assertTrue(director.scene_stack[-1].joined)
        self.assertEqual(len(director.scene_stack), 1)

    def test_watching_does_not_time_out_and_back_still_exits(self):
        garden = self.start()
        director.last_player_action -= 60000
        self.step(count=10)
        self.assertIs(director.scene_stack[-1], garden)
        self.step(extra=8)  # player one's Back button
        self.assertEqual(director.scene_stack, [])

    def test_audio_is_opt_in_and_stops_on_rest(self):
        garden = self.start()
        self.assertFalse(garden.sound_on)
        self.step(X)
        self.assertTrue(garden.sound_on)
        self.assertTrue(any(b"lullaby" in line for line, _ in director.platform.comms.sent))
        self.step()
        self.step(X)
        self.assertFalse(garden.sound_on)
        self.step()
        self.step(X)
        self.step(B)
        self.assertEqual(director.platform.comms.sent[-1][0], b"music off")

    def test_long_drift_keeps_resources_and_time_bounded(self):
        garden = self.start()
        for tick in range(1800):
            if tick % 20 == 0:
                garden.spawn_seed()
                garden.pending_calls.clear()
            self.step(A if tick % 120 < 60 else LEFT,
                      RIGHT if tick % 50 < 25 else 0)
        self.assertIs(director.scene_stack[-1], garden)
        self.assertEqual(garden._sprite_count, 42)
        self.assertEqual(garden._tilemap_count, 2)
        self.assertLessEqual(len(list(garden.seeds)), 16)
        self.assertLessEqual(len(list(garden.flowers)), 24)
        self.assertLess(garden.dream_time, 96)
        self.assertLess(garden.scroll, 96)
        vs2.export_scene_payload(garden)

    def test_real_asset_pack_builds_the_game_and_rest_scene(self):
        from pathlib import Path
        import tempfile
        from tools.generate_roms import generate_rom, load_palettegroups

        images = Path(ROOT) / "games/demos/dream_garden/images"
        definitions = images / "__images__.yaml"
        with tempfile.TemporaryDirectory() as temporary:
            rom = Path(temporary) / "dream-garden.rom"
            generate_rom(images, load_palettegroups(definitions), definitions,
                         rom_filename=rom, force=True)
            director.load_rom = lambda _name: self.real_load_rom(str(rom))
            garden = self.start()
            for name, (width, height, frames, _glyphs) in STRIPS.items():
                image = garden.image(name)
                self.assertEqual((image.width, image.height, image.frames),
                                 (width, height, frames))
            self.assertEqual(len(stripes), 5)
            vs2.export_scene_payload(garden)
            self.step(B)
            vs2.export_scene_payload(director.scene_stack[-1])


if __name__ == "__main__":
    unittest.main()
