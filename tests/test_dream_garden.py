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
    "seed.png": (9, 9, 4, None),
    "flowers.png": (17, 17, 8, None),
    "clouds.png": (16, 16, 18, None),
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
            if not director.scene_stack:
                return
            comms = director.platform.comms
            comms.next_joy2 = lambda: player2
            comms.next_extra = lambda: extra
            comms.push_input(bytes([player1]))
            try:
                director.step_once()
            except StopIteration:
                pass

    def start(self, player2=0, keep_timer=False):
        load_app("demos.dream_garden")
        self.step(A, player2)
        self.step()
        garden = director.scene_stack[-1]
        if not keep_timer:
            garden.pending_calls.clear()  # wall-clock timers are checked separately
        return garden

    def start_file(self, path):
        spec = importlib.util.spec_from_file_location("presentation_checkpoint", path)
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

    def test_empty_garden_and_three_ordered_layers(self):
        garden = self.start()
        self.assertEqual(len(garden.flowers), 0)
        self.assertEqual([layer.name for layer in garden.layers], ["world", "air", "hud"])
        self.assertIs(garden.dreamer.layer, garden.world)
        self.assertIs(garden.friend.layer, garden.world)
        self.assertTrue(all(sprite.layer is garden.world for sprite in garden.flowers._free))
        self.assertIs(garden.ground.layer, garden.air)
        self.assertTrue(all(sprite.layer is garden.air for sprite in garden.seeds._free))
        self.assertIs(garden.air._drawables[0], garden.ground)
        self.assertEqual(garden.air._drawables[1:], garden.seeds._free)
        # All reserved flowers precede both dreamers in the lower layer.
        self.assertEqual(garden.world.sprites[-2:], [garden.dreamer, garden.friend])
        self.assertEqual(garden.hud.tilemaps, [garden.mood, garden.sound_notice])
        self.assertFalse(garden.mood.visible)
        self.assertFalse(garden.sound_notice.visible)

    def test_moving_catches_follow_direction_and_stopped_catches_alternate(self):
        garden = self.start(player2=A)
        garden.dreamer.y = 12
        garden.friend.y = 20
        for first, second, sides1, sides2 in (
                (LEFT, RIGHT, (1, 1, 1), (-1, -1, -1)),
                (0, 0, (1, -1, 1), (-1, 1, -1)),
                (0, 0, (-1, 1), (1, -1)),
                (RIGHT | A, LEFT | A, (-1, -1, -1), (1, 1, 1)),
                (0, LEFT, (-1, 1), (1, 1)),
                (LEFT | RIGHT, 0, (-1, 1), (1, -1)),
                (LEFT, RIGHT, (1, 1), (-1, -1))):
            self.step(first, second)
            for player, sides in ((garden.dreamer, sides1), (garden.friend, sides2)):
                for side in sides:
                    seed = garden.seeds.spawn(x=100, y=100)
                    garden.bloom(seed, player)
                    flower = garden.flowers._newest
                    self.assertEqual(flower.y, player.y)
                    expected = (player.x + player.width // 2 + side * player.width * 0.75
                                - garden.flower_half) % vs2.display.width
                    self.assertAlmostEqual(flower.x, expected)

    def test_catch_after_stopping_uses_heading_across_the_angular_seam(self):
        garden = self.start()
        self.assertEqual(garden.last_direction1, 1)
        self.step(LEFT, count=10)
        self.assertEqual(garden.dreamer.x, 1)
        self.step()
        garden.seeds.spawn(x=254, y=10)
        self.step()
        flower = garden.flowers._newest
        expected = (garden.dreamer.x + garden.dreamer.width // 2
                    + garden.dreamer.width * 0.75 - garden.flower_half) % 256
        self.assertAlmostEqual(flower.x, expected)

        self.assertEqual(flower.y, garden.dreamer.y)
        self.step(RIGHT, count=2)
        self.assertEqual(garden.dreamer.x, 255)
        self.step()
        garden.seeds.spawn(x=254, y=10)
        self.step()
        flower = garden.flowers._newest
        expected = (garden.dreamer.x + garden.dreamer.width // 2
                    - garden.dreamer.width * 0.75 - garden.flower_half) % 256
        self.assertAlmostEqual(flower.x, expected)

    def test_stationary_catches_alternate_across_ticks_and_resume_resets_the_side(self):
        garden = self.start()
        self.step(RIGHT)
        self.step()
        for side in (-1, 1, -1):
            garden.seeds.spawn(x=garden.dreamer.x, y=10)
            self.step()
            expected = (garden.dreamer.x + garden.dreamer.width // 2
                        + side * garden.dreamer.width * 0.75 - garden.flower_half) % 256
            self.assertAlmostEqual(garden.flowers._newest.x, expected)
        # Same-direction movement restarts the first stopped planting side.
        self.step(RIGHT)
        self.step()
        garden.seeds.spawn(x=garden.dreamer.x, y=10)
        self.step()
        expected = (garden.dreamer.x + garden.dreamer.width // 2
                    - garden.dreamer.width * 0.75 - garden.flower_half) % 256
        self.assertAlmostEqual(garden.flowers._newest.x, expected)

    def test_flowers_drift_inward_much_slower_than_seeds_and_retire(self):
        from games.demos.dream_garden.code.dream_garden import FLOWER_DRIFT_RATIO, SEED_SPEED_RATIO, CLOUD_SPEED
        garden = self.start()
        flower = garden.flowers.spawn(x=100, y=20)
        seed = garden.seeds.spawn(x=150, y=100)
        for buttons in (0, A):
            before_flower, before_seed = flower.y, seed.y
            self.step(buttons)
            self.assertAlmostEqual(flower.y - before_flower,
                                   CLOUD_SPEED * SEED_SPEED_RATIO * FLOWER_DRIFT_RATIO)
            self.assertAlmostEqual(before_seed - seed.y, garden.speed * SEED_SPEED_RATIO)
        flower.y = 254.999
        self.step()
        self.assertEqual(len(garden.flowers), 0)

    def test_seed_glow_is_random_independent_and_cleared_on_retirement(self):
        from unittest.mock import patch
        garden = self.start()
        first = garden.seeds.spawn(x=100, y=100)
        second = garden.seeds.spawn(x=150, y=100)
        with patch.dict(garden.glow_seed.__globals__, {"randrange": lambda *args: 90}):
            garden.glow_seed(first)
            garden.glow_seed(second)
            self.assertEqual(first.frame, 0)
            garden.seed_glows[first][0] = 0
            frames = []
            for _ in range(36):
                garden.glow_seed(first)
                garden.glow_seed(second)
                frames.append(first.frame)
                self.assertEqual(second.frame, 0)
            self.assertEqual(frames, [frame for frame in (1, 2, 3, 2, 1, 0) for _ in range(6)])
            self.assertEqual(garden.seed_glows[first], [90, 0])
        garden.retire_seed(first)
        second.y = -10
        self.step()
        self.assertEqual(garden.seed_glows, {})

    def test_clouds_span_cells_without_gaps_at_the_scroll_repeat(self):
        from games.demos.dream_garden.code.dream_garden import CLOUD_PATCHES, PATTERN_ROWS
        garden = self.start()
        ground = garden.ground
        self.assertEqual((ground.columns, ground.rows, ground.tile_width, ground.tile_height),
                         (16, 22, 16, 16))
        self.assertEqual(ground.image.name, "clouds.png")
        for col, row, first, width, height in CLOUD_PATCHES:
            for dy in range(height):
                for dx in range(width):
                    self.assertEqual(ground[col + dx, row + dy], first + dy * width + dx)
        for row in range(ground.rows - PATTERN_ROWS):
            for col in range(ground.columns):
                self.assertEqual(ground[col, row], ground[col, row + PATTERN_ROWS])
        self.assertEqual(ground[0, 0], vs2.EMPTY_TILE)
        garden.scroll = PATTERN_ROWS * ground.tile_height - garden.speed / 2
        self.step()
        self.assertAlmostEqual(garden.scroll, garden.speed / 2)
        self.assertLess(ground.view_y + ground.view_height, ground.rows * ground.tile_height)

    def test_seeds_move_slower_than_clouds_in_normal_and_relaxed_modes(self):
        from games.demos.dream_garden.code.dream_garden import SEED_SPEED_RATIO, CLOUD_SPEED
        garden = self.start()
        seed = garden.seeds.spawn(x=100, y=100)
        for one, two in ((0, 0), (A, 0), (0, A)):
            seed_y, cloud_scroll = seed.y, garden.scroll
            self.step(one, two)
            cloud_delta = garden.scroll - cloud_scroll
            seed_delta = seed_y - seed.y
            self.assertGreater(cloud_delta, seed_delta)
            self.assertAlmostEqual(cloud_delta, CLOUD_SPEED)
            self.assertAlmostEqual(seed_delta, garden.speed * SEED_SPEED_RATIO)

    def test_relax_does_not_change_clouds_or_flower_drift_or_animation(self):
        from games.demos.dream_garden.code.dream_garden import CLOUD_SPEED, SEED_SPEED_RATIO, FLOWER_DRIFT_RATIO
        garden = self.start()
        flower = garden.flowers.spawn(x=100, y=20, frame=0)
        garden.dream_time = 5.8
        scroll, flower_y = garden.scroll, flower.y
        self.step(A)
        self.assertAlmostEqual(garden.scroll - scroll, CLOUD_SPEED)
        self.assertAlmostEqual(flower.y - flower_y, CLOUD_SPEED * SEED_SPEED_RATIO * FLOWER_DRIFT_RATIO)
        self.assertEqual(flower.frame, 1)
        self.assertEqual(garden.ground.view_y, int(garden.scroll))

    def test_multi_cell_clouds_render_as_connected_silhouettes(self):
        from pathlib import Path
        import tempfile
        from tools.generate_roms import generate_rom, load_palettegroups
        sys.path.insert(0, os.path.join(ROOT, "emulator"))
        import povrender
        images = Path(ROOT) / "games/demos/dream_garden/images"
        definitions = images / "__images__.yaml"
        old_stars = povrender.starfield_enabled
        with tempfile.TemporaryDirectory() as temporary:
            rom = Path(temporary) / "clouds.rom"
            generate_rom(images, load_palettegroups(definitions), definitions,
                         rom_filename=rom, force=True)
            director.load_rom = lambda _name: self.real_load_rom(str(rom))
            self.start()
            povrender.set_palettes(director.palette_data)
            for index, data in director._stripe_buffers.items():
                povrender.set_image_strip(index, data)
            povrender.set_starfield_enabled(False)
            try:
                for first, width, height in ((0, 1, 1), (1, 2, 1), (3, 3, 2),
                                              (9, 1, 1), (10, 2, 1), (12, 3, 2)):
                    class CloudProbe(vs2.Scene):
                        def build(probe):
                            hud = probe.layer("hud", projection=vs2.HUD)
                            tiles = hud.tilemap("clouds.png", columns=width, rows=height)
                            for row in range(height):
                                for col in range(width):
                                    tiles[col, row] = first + row * width + col
                    probe = CloudProbe()
                    director.scene_stack[-1].switch(probe)
                    self.step()
                    povrender.set_vs2_scene(vs2.export_scene_payload(probe))
                    pixels = povrender.render_frame(povrender.snapshot_vs2_scene()).reshape(256, 54)
                    opaque = {(x, y) for x in range(width * 16) for y in range(height * 16)
                              if pixels[x, 53 - y] & 0xFFFFFF}
                    total = len(opaque)
                    self.assertGreater(total, 0)
                    largest = 0
                    while opaque:
                        pending = [opaque.pop()]
                        size = 0
                        while pending:
                            x, y = pending.pop()
                            size += 1
                            for dx in (-1, 0, 1):
                                for dy in (-1, 0, 1):
                                    neighbour = (x + dx, y + dy)
                                    if neighbour in opaque:
                                        opaque.remove(neighbour)
                                        pending.append(neighbour)
                        largest = max(largest, size)
                    self.assertGreaterEqual(largest / total, 0.98, (first, width, height))
                # Exercise the real flying-layer compositor with an overlap.
                class SeedOverlay(vs2.Scene):
                    def __init__(probe, clouds, seeds):
                        vs2.Scene.__init__(probe)
                        probe.clouds, probe.seeds = clouds, seeds

                    def build(probe):
                        air = probe.layer("air", projection=vs2.TUNNEL)
                        if probe.clouds:
                            tiles = air.tilemap("clouds.png", columns=3, rows=2)
                            for row in range(2):
                                for col in range(3):
                                    tiles[col, row] = 12 + row * 3 + col
                        if probe.seeds:
                            seeds = air.sprite_pool("seed.png", count=1)
                            seeds.spawn(x=16, y=8)

                renders = []
                for clouds, seeds in ((False, True), (True, False), (True, True)):
                    probe = SeedOverlay(clouds, seeds)
                    director.scene_stack[-1].switch(probe)
                    self.step()
                    povrender.set_vs2_scene(vs2.export_scene_payload(probe))
                    renders.append(povrender.render_frame(povrender.snapshot_vs2_scene()).copy())
                seed_only, cloud_only, combined = renders
                seed_mask = (seed_only & 0xFFFFFF) != 0
                self.assertTrue(((cloud_only & 0xFFFFFF)[seed_mask] != 0).any())
                self.assertTrue((combined[seed_mask] == seed_only[seed_mask]).all())
            finally:
                povrender.set_starfield_enabled(old_stars)

    def test_sound_toggle_notice_lasts_two_seconds_and_restarts_on_retoggling(self):
        from unittest.mock import patch
        garden = self.start()
        now = [1000]
        with patch.dict(garden.update.__globals__, {"ticks_ms": lambda: now[0]}):
            self.step(X)
            self.assertTrue(garden.sound_notice.visible)
            self.assertEqual(garden.sound_notice_until, 3000)
            now[0] = 2500
            self.step()
            self.step(0, X)
            self.assertEqual(garden.sound_notice.text, "NOISY")
            self.assertEqual(garden.sound_notice_until, 4500)
            now[0] = 4499
            self.step()
            self.assertTrue(garden.sound_notice.visible)
            now[0] = 4500
            self.step()
            self.assertTrue(garden.sound_notice.visible)
            self.assertIsNone(garden.sound_notice_until)
            self.assertEqual(garden.sound_notice.y, 11)
            now[0] = 4725
            self.step()
            self.assertAlmostEqual(garden.sound_notice.y, 1.5)
            now[0] = 4800
            self.step(X)
            self.assertEqual(garden.sound_notice.text, "QUIET")
            self.assertEqual(garden.sound_notice.y, 11)
            self.assertIsNone(garden.sound_notice_exit)
            now[0] = 7025
            self.step()
            self.assertAlmostEqual(garden.sound_notice.y, 1.5)
            now[0] = 7250
            self.step()
            self.assertFalse(garden.sound_notice.visible)
            self.assertIsNone(garden.sound_notice_exit)

    def test_relax_slides_out_and_a_new_request_cancels_the_exit(self):
        from unittest.mock import patch
        garden = self.start()
        now = [1000]
        with patch.dict(garden.update.__globals__, {"ticks_ms": lambda: now[0]}):
            self.step(A)
            self.step()
            self.assertTrue(garden.mood.visible)
            now[0] = 1225
            self.step()
            self.assertAlmostEqual(garden.mood.y, -3.5)
            self.assertTrue(garden.mood.visible)
            self.step(0, A)
            self.assertEqual(garden.mood.y, 1)
            self.assertIsNone(garden.mood_exit)
            self.step()
            now[0] = 1675
            self.step()
            self.assertFalse(garden.mood.visible)
            self.assertIsNone(garden.mood_exit)

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

    def test_either_player_slows_only_seeds(self):
        from games.demos.dream_garden.code.dream_garden import SLOW_SPEED, SLOW_SPAWN_MS, SEED_SPEED_RATIO, CLOUD_SPEED
        garden = self.start()
        seed = garden.seeds.spawn(x=100, y=100)
        previous_scroll = garden.scroll
        self.step(0, A)
        self.assertAlmostEqual(seed.y, 100 - SLOW_SPEED * SEED_SPEED_RATIO, places=2)
        self.assertAlmostEqual(garden.scroll - previous_scroll, CLOUD_SPEED, places=2)
        self.assertEqual(garden.spawn_ms, SLOW_SPAWN_MS)
        self.assertEqual(garden.mood.text, "RELAX")
        self.assertTrue(garden.mood.visible)
        self.assertEqual(garden.friend.frame, 7)
        self.step()
        self.assertTrue(garden.mood.visible)
        self.assertIsNotNone(garden.mood_exit)
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
        garden.seeds.spawn(x=100, y=-9)
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
        starting = [(flower.x, flower.frame) for flower in garden.flowers]
        for index in range(80):
            garden.bloom(garden.seeds.spawn(x=130, y=10), garden.dreamer)
        self.assertTrue(all((flower.x, flower.frame) not in starting for flower in garden.flowers))
        self.assertEqual(len(list(garden.flowers)), 24)
        self.assertEqual(garden._sprite_count, 42)
        self.assertEqual(garden._tilemap_count, 3)
        vs2.export_scene_payload(garden)

    def test_rest_preserves_the_garden_and_a_begins_a_new_dream(self):
        from games.demos.dream_garden.code.dream_garden import Garden, Rest
        garden = self.start(keep_timer=True)
        self.assertEqual(len(garden.pending_calls), 1)
        garden.bloom(garden.seeds.spawn(x=130, y=10), garden.dreamer)
        self.step(LEFT, count=10)
        flowers = [(flower.x, flower.y, flower.frame) for flower in garden.flowers]
        self.step(B)
        rest = director.scene_stack[-1]
        self.assertIsInstance(rest, Rest)
        self.assertEqual(rest.saved_flowers, flowers)
        self.assertEqual([(flower.x, flower.y, flower.frame)
                          for flower in rest.layers[0].sprites if flower.visible], flowers)
        self.assertEqual(garden.pending_calls, [])
        self.step()
        self.step(0, A)
        self.assertIsInstance(director.scene_stack[-1], Garden)
        self.assertTrue(director.scene_stack[-1].joined)
        self.assertEqual(len(director.scene_stack), 1)

    def test_title_garden_and_rest_keep_the_default_idle_exit(self):
        from games.demos.dream_garden.code.dream_garden import Title, Garden, Rest
        for scene in (Title(), Garden(), Rest([])):
            with self.subTest(scene=type(scene).__name__):
                director.scene_stack.clear()
                scene._vs_api_slug = "demos.dream_garden"
                scene._vs_declared_api = "vs2"
                director.push(scene)
                self.assertEqual(scene.idle_timeout, vs2.Scene.idle_timeout)
                director.last_player_action -= 30100
                self.step()
                self.assertEqual(director.scene_stack, [])

    def test_both_players_can_exit_with_y_or_back(self):
        for player1, extra in ((0, director.EXTRA_JOY1_Y), (0, 8),
                               (0, director.EXTRA_JOY2_Y), (0, director.EXTRA_JOY2_BACK)):
            with self.subTest(player1=player1, extra=extra):
                self.start()
                self.step(player1, extra=extra)
                self.assertEqual(director.scene_stack, [])

    def test_confirmation_a_does_not_slow_a_new_garden(self):
        from games.demos.dream_garden.code.dream_garden import DRIFT_SPEED
        for player in (1, 2):
            with self.subTest(player=player):
                load_app("demos.dream_garden")
                self.step(A if player == 1 else 0, A if player == 2 else 0, count=4)
                garden = director.scene_stack[-1]
                self.assertFalse(garden.slow)
                self.assertEqual(garden.speed, DRIFT_SPEED)
                self.assertEqual(garden.dreamer.frame, 0)
                self.assertEqual(garden.friend.frame, 4)
                self.step()
                self.step(A if player == 1 else 0, A if player == 2 else 0)
                self.assertTrue(garden.slow)
                self.step(B)
                self.step()
                self.step(A if player == 1 else 0, A if player == 2 else 0, count=4)
                self.assertFalse(director.scene_stack[-1].slow)
                self.step(extra=8)
                self.step()

    def test_every_presentation_checkpoint_runs_and_has_only_its_stage_features(self):
        from pathlib import Path
        files = sorted((Path(ROOT) / "games/demos/dream_garden/code/checkpoints").glob("*.py"))
        self.assertEqual(len(files), 11)
        for stage, path in enumerate(files, 1):
            with self.subTest(checkpoint=path.name):
                self.tearDown()
                self.setUp()
                scene = self.start_file(path)
                if stage >= 9:
                    self.step(A)
                    self.step()
                    scene = director.scene_stack[-1]
                self.assertEqual(hasattr(scene, "seeds"), stage >= 3)
                self.assertEqual(hasattr(scene, "ground"), stage >= 6)
                self.assertEqual(hasattr(scene, "mood"), stage >= 8)
                self.assertEqual(hasattr(scene, "friend"), stage >= 10)
                scene.pending_calls.clear()
                before = scene.dreamer.x
                self.step(LEFT, count=5)
                self.assertEqual(scene.dreamer.x, (before + 5) % 256)
                if stage >= 5:
                    scene.seeds.despawn_all()
                    scene.seeds.spawn(x=scene.dreamer.x, y=10)
                    self.step()
                    self.assertGreater(len(scene.flowers), 0)
                    flower = scene.flowers._newest
                    expected = (scene.dreamer.x + scene.dreamer.width // 2
                                + scene.dreamer.width * 0.75
                                - scene.image("flowers.png").width // 2) % 256
                    self.assertAlmostEqual(flower.x, expected)
                vs2.export_scene_payload(scene)
                self.step(extra=8)
                self.step()

    def test_packed_art_has_binary_alpha_and_host_tools_are_not_runtime_files(self):
        from pathlib import Path
        from PIL import Image
        from tools.generate_web_runtime_bundle import is_runtime_source
        spec = importlib.util.spec_from_file_location("rotor_fs", Path(ROOT) / "hardware/rotor/build_micropython_fs.py")
        fs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fs)
        jobs = list(fs.iter_copy_jobs(Path(ROOT)))
        self.assertFalse(any("dream_garden/sources/" in str(job) for job in jobs))
        source = "games/demos/dream_garden/sources/make_audio.py"
        self.assertFalse(is_runtime_source(source))
        for name in ("dreamer.png", "seed.png", "flowers.png", "clouds.png"):
            with Image.open(Path(ROOT) / "games/demos/dream_garden/images" / name) as image:
                self.assertLessEqual(set(image.convert("RGBA").getchannel("A").tobytes()), {0, 255})

    def test_audio_starts_on_toggles_and_stops_on_rest(self):
        garden = self.start()
        self.assertTrue(garden.sound_on)
        self.assertTrue(any(b"lullaby" in line for line, _ in director.platform.comms.sent))
        garden.bloom(garden.seeds.spawn(x=130, y=10), garden.dreamer)
        self.assertTrue(any(b"bloom" in line for line, _ in director.platform.comms.sent))
        self.step(0, X)
        self.assertFalse(garden.sound_on)
        self.assertEqual(garden.sound_notice.text, "QUIET")
        self.assertEqual(director.platform.comms.sent[-1][0], b"music off")
        self.step()
        self.step(X)
        self.assertTrue(garden.sound_on)
        self.assertEqual(garden.sound_notice.text, "NOISY")
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
        self.assertEqual(garden._tilemap_count, 3)
        self.assertLessEqual(len(list(garden.seeds)), 16)
        self.assertLessEqual(len(list(garden.flowers)), 24)
        self.assertLessEqual(len(garden.seed_glows), 16)
        self.assertTrue(all(seed in list(garden.seeds) for seed in garden.seed_glows))
        self.assertLess(garden.dream_time, 96)
        self.assertLess(garden.scroll, 192)
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
