import os
import random
import struct
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

VIXEOUS_STRIPS = (
    "ship.png", "enemy.png", "boss.png", "shots.png", "explosion.png",
    "targets.png", "reticle.png", "terrain.png", "digits.png", "messages.png",
)

VIXEOUS_METADATA = {
    "ship.png": (18, 13, 4),
    "enemy.png": (14, 11, 6),
    "boss.png": (36, 19, 2),
    "shots.png": (6, 10, 3),
    "explosion.png": (20, 20, 6),
    "targets.png": (14, 10, 4),
    "reticle.png": (18, 6, 3),
    "terrain.png": (32, 16, 16),
    "digits.png": (4, 6, 12),
    "messages.png": (64, 12, 3),
}


class VixeousVs2Tests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        runtime_director = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            for index, name in enumerate(VIXEOUS_STRIPS):
                stripes[name] = index
                width, height, frames = VIXEOUS_METADATA[name]
                runtime_director.platform.sprites.stripes[index] = {
                    "width": width,
                    "height": height,
                    "frames": frames,
                    "palette": 0,
                    "glyphs": "0123456789 *" if name == "digits.png" else None,
                }

        runtime_director.load_rom = fake_load_rom

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def step_buttons(self, buttons):
        director.platform.comms.push_input(bytes([buttons]))
        try:
            director.step_once()
        except StopIteration:
            pass

    def test_vixeous_uses_one_terrain_tilemap(self):
        scene = load_app("alecu.vixeous")
        import vs2
        from games.alecu.vixeous.code.vixeous import (
            TERRAIN_BUFFER_ROWS, TERRAIN_COLS, TERRAIN_TILE_H, TERRAIN_VIEW_H,
            terrain_frame_for,
        )

        self.assertEqual(scene._vs_declared_api, "vs2")
        self.assertIs(scene.terrain.cells, scene.terrain_data)
        self.assertEqual(len(scene.world.tilemaps), 1)

        for row in range(TERRAIN_BUFFER_ROWS):
            for col in range(TERRAIN_COLS):
                self.assertEqual(
                    scene.terrain_data[row * TERRAIN_COLS + col],
                    terrain_frame_for(col, row, 0),
                )

        payload = vs2.export_scene_payload(scene)
        self.assertEqual(payload[4], 3)
        self.assertEqual(payload[7], 2)  # terrain + score label

    def test_ground_is_below_objects_and_startup_message_is_centered(self):
        scene = load_app("alecu.vixeous")
        import vs2
        from games.alecu.vixeous.code.vixeous import centered_x

        self.assertIs(scene.world._drawables[0], scene.terrain)
        self.assertGreater(
            scene.world._drawables.index(scene.player),
            scene.world._drawables.index(scene.terrain),
        )
        self.assertGreater(
            scene.world._drawables.index(scene.reticle),
            scene.world._drawables.index(scene.terrain),
        )
        self.assertIs(scene.message.layer, scene.hud)
        self.assertEqual(scene.hud.projection, vs2.HUD)
        self.assertEqual(
            scene.message.x, centered_x(0, scene.message.width))
        self.assertEqual(scene.message.y, 12)
        self.assertTrue(scene.message.visible)

    def test_ground_targets_and_boss_are_present_and_advance(self):
        scene = load_app("alecu.vixeous")
        from games.alecu.vixeous.code.vixeous import (
            BOSS_START_Y,
            ENEMY_START_Y,
            PLAYER_START_Y,
            TARGET_START_Y,
            TERRAIN_TILE_H,
        )

        self.assertEqual(scene.terrain.y, 0)
        self.assertEqual(scene.player.y, PLAYER_START_Y)
        self.assertEqual(scene.aim_y(), PLAYER_START_Y + 66)

        scene.spawn_wave()
        self.assertEqual(min(enemy.y for enemy in scene.enemies), ENEMY_START_Y)

        scene.depth = scene.next_target_row * TERRAIN_TILE_H
        scene.spawn_target_if_needed()
        self.assertEqual(len(scene.targets), 1)
        target = next(iter(scene.targets))
        self.assertEqual(target.y, TARGET_START_Y)
        original_y = target.y
        scene.update_targets(1)
        self.assertEqual(target.y, original_y - 1)
        self.assertTrue(target.visible)

        scene.depth = 901
        scene.score = 120
        scene.maybe_start_boss()
        self.assertTrue(scene.boss.visible)
        self.assertEqual(scene.boss.y, BOSS_START_Y)
        self.assertEqual(scene.boss.hp, 18)

    def test_scoreboard_flips_complete_label_for_top_hud(self):
        scene = load_app("alecu.vixeous")

        scene.scoreboard.set_score(120)
        scene.scoreboard.set_lives(2)

        self.assertEqual(scene.scoreboard.label.text, "00120 **")
        self.assertTrue(scene.scoreboard.label.flip_x)
        self.assertTrue(scene.scoreboard.label.flip_y)
        self.assertEqual(scene.scoreboard.label.image.width, 4)
        self.assertEqual(scene.scoreboard.label.image.height, 6)
        self.assertEqual(
            scene.scoreboard.label.x,
            (
                256
                - scene.scoreboard.label.columns
                * scene.scoreboard.label.image.width
            ) // 2,
        )

    def test_vixeous_terrain_scrolls_by_panning_the_viewport(self):
        scene = load_app("alecu.vixeous")
        from games.alecu.vixeous.code.vixeous import (
            STATE_PLAYING, TERRAIN_COLS, TERRAIN_SCROLL_TICKS, TERRAIN_TILE_H,
            TERRAIN_TILE_W, TERRAIN_VIEW_H, terrain_frame_for,
        )

        scene.state = STATE_PLAYING
        scene.message.hide()

        # scroll half a tile: viewport pans without touching the cell buffer
        for _ in range(TERRAIN_SCROLL_TICKS * (TERRAIN_TILE_H // 2)):
            self.step_buttons(0)
        self.assertEqual(scene.depth, TERRAIN_TILE_H // 2)
        self.assertEqual(
            scene.terrain.view_y,
            TERRAIN_TILE_H // 2,
        )
        self.assertEqual(scene.terrain_base_row, 0)

        # scroll the other half: a whole row has passed, cells regenerate
        for _ in range(TERRAIN_SCROLL_TICKS * (TERRAIN_TILE_H // 2)):
            self.step_buttons(0)
        self.assertEqual(scene.depth, TERRAIN_TILE_H)
        self.assertEqual(scene.terrain.view_y, 0)
        self.assertEqual(scene.terrain_base_row, 1)
        for col in range(TERRAIN_COLS):
            self.assertEqual(
                scene.terrain_data[col], terrain_frame_for(col, 1, 0),
            )

        # the map rotates opposite the camera
        expected_x = (-scene.camera_theta - TERRAIN_TILE_W // 2) % 256
        self.assertEqual(scene.terrain.x, expected_x)
        self.step_buttons(director.JOY_RIGHT)
        self.assertNotEqual(scene.camera_theta, 0)
        expected_x = (-scene.camera_theta - TERRAIN_TILE_W // 2) % 256
        self.assertEqual(scene.terrain.x, expected_x)


class VixeousAssetTests(unittest.TestCase):
    def test_text_strips_use_only_hard_edged_pixels_and_black_digits(self):
        from PIL import Image

        images = os.path.join(ROOT, "games", "alecu", "vixeous", "images")
        digits = Image.open(os.path.join(images, "digits.png")).convert("RGBA")
        messages = Image.open(os.path.join(images, "messages.png")).convert("RGBA")

        self.assertEqual(digits.size, (48, 6))
        self.assertEqual(messages.size, (192, 12))

        tinyfont = Image.open(
            os.path.join(
                ROOT, "system", "shared", "other", "images",
                "tinyfont_white.png",
            )
        ).convert("RGBA")
        for frame in range(10):
            tile = digits.crop((frame * 4, 0, frame * 4 + 4, 6))
            opaque = {
                pixel for pixel in tile.get_flattened_data() if pixel[3]
            }
            self.assertEqual(opaque, {(0, 0, 0, 255)})
            expected = tinyfont.crop(
                ((ord("0") + frame) * 4, 0, (ord("0") + frame + 1) * 4, 6)
            )
            self.assertEqual(
                tuple(pixel[3] for pixel in tile.get_flattened_data()),
                tuple(pixel[3] for pixel in expected.get_flattened_data()),
            )
            self.assertTrue(all(tile.getpixel((3, y))[3] == 0 for y in range(6)))

        life = digits.crop((11 * 4, 0, 12 * 4, 6))
        self.assertEqual(
            {pixel for pixel in life.get_flattened_data() if pixel[3]},
            {(232, 32, 42, 255)},
        )
        self.assertEqual(
            sum(pixel[3] != 0 for pixel in life.get_flattened_data()),
            6,
        )
        self.assertEqual(
            tuple(
                "".join(
                    "#" if life.getpixel((x, y))[3] else "."
                    for x in range(4)
                )
                for y in range(6)
            ),
            ("#.#.", "###.", ".#..", "....", "....", "...."),
        )
        self.assertTrue(all(life.getpixel((3, y))[3] == 0 for y in range(6)))

        allowed_message_colors = {
            (20, 24, 26, 255),
            (180, 188, 184, 255),
            (255, 238, 158, 255),
            (232, 32, 42, 255),
        }
        message_colors = set(messages.get_flattened_data())
        self.assertEqual(message_colors, allowed_message_colors)
        self.assertEqual(
            {pixel[3] for pixel in digits.get_flattened_data()} | {
                pixel[3] for pixel in messages.get_flattened_data()
            },
            {0, 255},
        )


if __name__ == "__main__":
    unittest.main()
