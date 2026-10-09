"""Trench Run, the game the VS2 tutorial builds (games/demos/tutorial_game)."""

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

        @staticmethod
        def sleep_ms(ms):
            time.sleep(ms / 1000.0)

    sys.modules["utime"] = _Utime

from ventilastation import api_guard
from ventilastation.app_loader import load_app
from ventilastation.director import configure_runtime, director, reset_runtime, stripes

# name: (frame width, height, frames, glyphs), as in the game's __images__.yaml
STRIPS = {
    "ship.png": (19, 19, 3, None),
    "enemy.png": (14, 11, 6, None),
    "trench.png": (16, 16, 8, None),
    "numerals.png": (4, 5, 12, "0123456789 *"),
    "steel8x8.png": (8, 8, 256, None),
}


class TutorialGameTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        runtime_director = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            for index, (name, (width, height, frames, glyphs)) in enumerate(STRIPS.items()):
                stripes[name] = index
                runtime_director.platform.sprites.stripes[index] = {
                    "width": width, "height": height, "frames": frames,
                    "palette": 0, "glyphs": glyphs,
                }

        runtime_director.load_rom = fake_load_rom

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def step(self, buttons=0):
        director.platform.comms.push_input(bytes([buttons]))
        try:
            director.step_once()
        except StopIteration:
            pass

    def press(self, buttons):
        self.step(buttons)
        self.step(0)

    def start_game(self, title=None, keep_timer=False):
        """Press A on the title and return the Game it switches to.

        The spawn timer is cleared: it counts real milliseconds, so on a slow
        runner it could add a random enemy in the middle of a test. Tests that
        want an enemy spawn one; the timer has its own test.
        """
        title = title or load_app("demos.tutorial_game")
        self.press(director.BUTTON_A)
        game = director.scene_stack[-1]
        self.assertIsNot(game, title)
        if not keep_timer:
            game.pending_calls.clear()
        return game

    def test_title_switches_to_a_game_that_inherits_the_app(self):
        import vs2
        from games.demos.tutorial_game.code.tutorial_game import Game, Title

        title = load_app("demos.tutorial_game")
        self.assertIsInstance(title, Title)
        game = self.start_game(title)
        self.assertIsInstance(game, Game)
        # The title was replaced, not stacked under the game.
        self.assertEqual(len(director.scene_stack), 1)
        # The scene the game built itself must still be exported as VS2.
        self.assertEqual(game._vs_declared_api, "vs2")
        self.assertEqual(game._vs_api_slug, title._vs_api_slug)
        payload = vs2.export_scene_payload(game)
        self.assertEqual(bytes(payload[:3]), b"VS2")

    def test_the_ship_starts_centred_on_the_bottom_of_the_disc(self):
        game = self.start_game()
        # x = 0 is the bottom, and a sprite's x is its edge: the ship's centre
        # column is x + 9 for a 19 pixel wide ship.
        self.assertEqual((game.ship.x + game.ship.width // 2) % 256, 0)
        self.assertEqual(game.ship.y, 0)

    def test_the_score_is_at_the_top_of_the_disc_and_flipped_to_read_upright(self):
        game = self.start_game()
        label = game.score_label
        self.assertEqual(label.x + label.columns * label.image.width // 2, 128)
        self.assertTrue(label.flip_x)
        self.assertTrue(label.flip_y)

    def test_ship_moves_around_the_disc_and_wraps(self):
        game = self.start_game()
        start = game.ship.x
        # At the bottom of the disc x counts up toward the left, so the left
        # button adds to it.
        self.step(director.JOY_LEFT)
        self.assertEqual(game.ship.x, start + 1)
        self.step(director.JOY_RIGHT)
        self.step(director.JOY_RIGHT)
        self.assertEqual(game.ship.x, start - 1)
        game.ship.x = 255
        self.step(director.JOY_LEFT)
        self.assertEqual(game.ship.x, 0)
        self.step(director.JOY_RIGHT)
        self.assertEqual(game.ship.x, 255)

    def test_the_ship_leans_into_a_turn(self):
        from games.demos.tutorial_game.code.tutorial_game import (
            LEVEL, TURN_LEFT, TURN_RIGHT)

        game = self.start_game()
        self.assertEqual(game.ship.frame, LEVEL)
        self.step(director.JOY_LEFT)
        self.assertEqual(game.ship.frame, TURN_LEFT)
        self.step(director.JOY_RIGHT)
        self.assertEqual(game.ship.frame, TURN_RIGHT)
        self.step(0)
        self.assertEqual(game.ship.frame, LEVEL)

    def test_the_turned_frames_point_their_nose_the_way_the_ship_travels(self):
        # At the bottom of the disc, where the ship flies, a sprite looks just
        # like its PNG: the left-turn frame must have its nose on the image's
        # left, and the right-turn frame on its right.
        # (See tools/vs2_doc_images/make_ship_art.py.)
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        from games.demos.tutorial_game.code.tutorial_game import (
            LEVEL, TURN_LEFT, TURN_RIGHT)

        strip = Image.open(os.path.join(
            ROOT, "games", "demos", "tutorial_game", "images", "ship.png")).convert("RGBA")
        width = strip.width // 3

        def nose_offset(frame):
            """How far right of the image's centre the topmost pixels are."""
            pixels = strip.crop((frame * width, 0, (frame + 1) * width, strip.height))
            top = next(y for y in range(pixels.height)
                       if any(pixels.getpixel((x, y))[3] for x in range(width)))
            xs = [x for x in range(width) if pixels.getpixel((x, top))[3]]
            return sum(xs) / len(xs) - (width - 1) / 2

        self.assertEqual(nose_offset(LEVEL), 0)
        self.assertLess(nose_offset(TURN_LEFT), -1)
        self.assertGreater(nose_offset(TURN_RIGHT), 1)

    def test_the_level_ship_is_symmetric_and_ends_in_a_single_pixel_point(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        from games.demos.tutorial_game.code.tutorial_game import LEVEL

        strip = Image.open(os.path.join(
            ROOT, "games", "demos", "tutorial_game", "images", "ship.png")).convert("RGBA")
        width = strip.width // 3
        self.assertEqual(width % 2, 1)          # a centre column for the point
        ship = strip.crop((LEVEL * width, 0, (LEVEL + 1) * width, strip.height))
        for y in range(ship.height):
            for x in range(width):
                self.assertEqual(ship.getpixel((x, y)), ship.getpixel((width - 1 - x, y)),
                                 "row %d is not symmetric" % y)
        top = next(y for y in range(ship.height)
                   if any(ship.getpixel((x, y))[3] for x in range(width)))
        lit = [x for x in range(width) if ship.getpixel((x, top))[3]]
        self.assertEqual(lit, [width // 2])

    def test_both_directions_held_cancel_out(self):
        from games.demos.tutorial_game.code.tutorial_game import LEVEL

        game = self.start_game()
        start = game.ship.x
        self.step(director.JOY_LEFT | director.JOY_RIGHT)
        self.assertEqual(game.ship.x, start)
        self.assertEqual(game.ship.frame, LEVEL)

    def test_the_trench_wall_scrolls_and_wraps_seamlessly(self):
        game = self.start_game()
        pattern_height = 6 * game.ground.tile_height
        seen = set()
        for _ in range(2 * pattern_height + 4):
            before = game.scroll
            self.step(0)
            # The wall moves at the speed of the trench, a bit less than a
            # depth unit per tick at the start, so no row of the view is skipped.
            self.assertAlmostEqual((game.scroll - before) % pattern_height, game.speed)
            seen.add(game.ground.view_y)
            self.assertLess(game.ground.view_y, pattern_height)
        self.assertEqual(seen, set(range(pattern_height)))
        # The wall repeats every 6 rows, so the wrap shows the same picture.
        for row in range(10):
            for col in range(16):
                self.assertEqual(game.ground[col, row], game.ground[col, row + 6])

    def test_an_enemy_that_flies_past_scores(self):
        game = self.start_game()
        game.enemies.spawn(x=(game.ship.x + 128) % 256, y=1)
        for _ in range(60):
            self.step(0)
        self.assertEqual(len(game.enemies), 0)
        self.assertEqual(game.score, 10)
        self.assertEqual(game.score_label.text, "00010")

    def test_an_enemy_reaching_the_ship_ends_the_game(self):
        from games.demos.tutorial_game.code.tutorial_game import Game, GameOver

        game = self.start_game()
        game.score = 30
        game.enemies.spawn(x=game.ship.x, y=game.ship.y + 2)
        self.step(0)
        over = director.scene_stack[-1]
        self.assertIsInstance(over, GameOver)
        self.assertEqual(over.score, 30)
        self.assertEqual(over._vs_declared_api, "vs2")

        self.press(director.BUTTON_A)
        again = director.scene_stack[-1]
        self.assertIsInstance(again, Game)
        self.assertEqual(again.score, 0)

    def test_dodging_keeps_the_game_going(self):
        game = self.start_game()
        game.enemies.spawn(x=game.ship.x, y=40)
        # Steer away from the enemy's angle while it comes down the tunnel.
        for _ in range(120):
            self.step(director.JOY_LEFT)
        self.assertIs(director.scene_stack[-1], game)
        self.assertEqual(len(game.enemies), 0)
        self.assertEqual(game.score, 10)

    def test_enemies_come_down_at_the_speed_the_wall_scrolls(self):
        game = self.start_game()
        enemy = game.enemies.spawn(x=100, y=100)
        self.step(0)
        self.assertAlmostEqual(enemy.y, 100 - game.speed)

    def pace(self, game, score):
        game.score = score
        game.get_harder()
        return game.speed, game.spawn_ms

    def test_the_game_alternates_between_getting_faster_and_getting_busier(self):
        from games.demos.tutorial_game.code.tutorial_game import (
            MAX_SPEED, MIN_SPAWN_MS, SPAWN_MS, SPAWN_STEP, SPEED_STEP, START_SPEED,
            STEP_POINTS)

        game = self.start_game()
        self.assertEqual(self.pace(game, 0), (START_SPEED, SPAWN_MS))
        # Nothing changes between steps.
        self.assertEqual(self.pace(game, STEP_POINTS - 10), (START_SPEED, SPAWN_MS))
        # Step 1: a faster trench.
        self.assertEqual(self.pace(game, STEP_POINTS),
                         (START_SPEED + SPEED_STEP, SPAWN_MS))
        # Step 2: more enemies.
        self.assertEqual(self.pace(game, 2 * STEP_POINTS),
                         (START_SPEED + SPEED_STEP, SPAWN_MS - SPAWN_STEP))
        # Step 3: faster again. Step 4: more enemies again.
        self.assertEqual(self.pace(game, 3 * STEP_POINTS),
                         (START_SPEED + 2 * SPEED_STEP, SPAWN_MS - SPAWN_STEP))
        self.assertEqual(self.pace(game, 4 * STEP_POINTS),
                         (START_SPEED + 2 * SPEED_STEP, SPAWN_MS - 2 * SPAWN_STEP))
        # Neither goes past its limit, however long you last.
        self.assertEqual(self.pace(game, 10 ** 6), (MAX_SPEED, MIN_SPAWN_MS))

    def test_each_step_changes_only_one_thing_and_never_makes_the_game_easier(self):
        from games.demos.tutorial_game.code.tutorial_game import STEP_POINTS

        game = self.start_game()
        previous = self.pace(game, 0)
        for step in range(1, 30):
            current = self.pace(game, step * STEP_POINTS)
            self.assertGreaterEqual(current[0], previous[0])
            self.assertLessEqual(current[1], previous[1])
            if previous[0] < 1.5 and previous[1] > 450:     # before either limit
                self.assertEqual((current[0] != previous[0]) + (current[1] != previous[1]), 1)
            previous = current

    def test_the_limits_are_reached_with_room_in_the_pool(self):
        from games.demos.tutorial_game.code.tutorial_game import (
            ENEMY_START, MIN_SPAWN_MS, START_SPEED)

        # The worst case for the pool is the slowest trench with the fastest
        # spawning: each enemy lives for ENEMY_START / speed ticks of 30 ms.
        game = self.start_game()
        lifetime_ms = ENEMY_START / START_SPEED * 30
        self.assertLess(lifetime_ms / MIN_SPAWN_MS, game.enemies.free + len(game.enemies))

    def crash(self, game, score):
        game.score = score
        game.enemies.spawn(x=game.ship.x, y=game.ship.y + 2)
        self.step(0)
        return director.scene_stack[-1]

    def label_texts(self, scene):
        return [drawable.text for layer in scene.layers for drawable in layer._drawables
                if getattr(drawable, "text", None)]

    def test_the_best_score_is_saved_shown_and_survives_a_restart(self):
        import vs2
        from games.demos.tutorial_game.code.tutorial_game import BEST, Title

        title = load_app("demos.tutorial_game")
        self.assertIsNone(vs2.saves.load(BEST))
        self.assertFalse(any("BEST" in text for text in self.label_texts(title)))

        over = self.crash(self.start_game(title), 30)
        self.assertTrue(over.new_best)
        self.assertEqual(vs2.saves.load(BEST), 30)
        self.assertIn("NEW BEST!", self.label_texts(over))
        self.assertIn("00030", self.label_texts(over))

        # A lower score leaves the record, and the file, alone.
        writes = []
        storage = director.platform.storage
        original = storage.write_json
        storage.write_json = lambda name, data: (writes.append(name), original(name, data))
        self.press(director.BUTTON_A)
        over = self.crash(director.scene_stack[-1], 10)
        self.assertFalse(over.new_best)
        self.assertEqual(vs2.saves.load(BEST), 30)
        self.assertEqual(writes, [])
        self.assertIn("GAME OVER", self.label_texts(over))
        self.assertIn("00010", self.label_texts(over))
        self.assertEqual(over.best, 30)

        # A fresh start of the game, as after a power cycle, shows the record.
        director.scene_stack.clear()
        title = load_app("demos.tutorial_game")
        self.assertIsInstance(title, Title)
        self.assertIn("BEST 00030", self.label_texts(title))

    def test_the_spawn_timer_rearms_itself(self):
        game = self.start_game(keep_timer=True)
        self.assertEqual(len(game.pending_calls), 1)   # build() armed it
        before = len(game.enemies)
        game.pending_calls.clear()
        game.spawn_enemy()
        self.assertEqual(len(game.enemies), before + 1)
        self.assertEqual(len(game.pending_calls), 1)


if __name__ == "__main__":
    unittest.main()
