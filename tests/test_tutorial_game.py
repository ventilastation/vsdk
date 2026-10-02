"""The shooter the VS2 tutorial builds (games/demos/tutorial_game)."""

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
    "ship.png": (18, 13, 4, None),
    "shots.png": (6, 10, 3, None),
    "enemy.png": (14, 11, 6, None),
    "explosion.png": (20, 20, 6, None),
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

    def test_ship_moves_around_the_disc_and_wraps(self):
        game = self.start_game()
        self.assertEqual(game.ship.x, 128)
        self.step(director.JOY_LEFT)
        self.assertEqual(game.ship.x, 127)
        game.ship.x = 0
        self.step(director.JOY_LEFT)
        self.assertEqual(game.ship.x, 255)

    def test_the_trench_wall_scrolls_and_wraps_seamlessly(self):
        game = self.start_game()
        pattern_height = 6 * game.ground.tile_height
        seen = set()
        for _ in range(2 * pattern_height + 4):
            self.step(0)
            seen.add(game.ground.view_y)
            self.assertLess(game.ground.view_y, pattern_height)
        self.assertEqual(seen, set(range(pattern_height)))
        # The wall repeats every 6 rows, so the wrap shows the same picture.
        for row in range(10):
            for col in range(16):
                self.assertEqual(game.ground[col, row], game.ground[col, row + 6])

    def test_a_shot_hits_an_enemy_and_scores(self):
        game = self.start_game()
        self.press(director.BUTTON_A)
        self.assertEqual(len(game.shots), 1)
        shot = next(iter(game.shots))
        self.assertGreater(shot.y, game.ship.y)

        enemy = game.enemies.spawn(x=shot.x, y=shot.y + 6)
        self.assertEqual(len(game.enemies), 1)
        for _ in range(5):
            self.step(0)
            if game.score:
                break
        self.assertEqual(game.score, 10)
        self.assertEqual(len(game.enemies), 0)
        self.assertEqual(len(game.shots), 0)
        self.assertEqual(len(game.booms), 1)
        self.assertEqual(game.score_label.text, "00010")

    def test_a_shot_that_misses_is_retired(self):
        game = self.start_game()
        self.press(director.BUTTON_A)
        for _ in range(80):
            self.step(0)
        self.assertEqual(len(game.shots), 0)
        self.assertEqual(game.score, 0)

    def test_explosions_play_out_and_are_released(self):
        game = self.start_game()
        game.booms.spawn(x=10, y=50)
        for _ in range(60):
            self.step(0)
        self.assertEqual(len(game.booms), 0)

    def finish_game_over_delay(self, scene):
        """Run the scene's pending timers now instead of waiting for them."""
        while scene.pending_calls:
            _when, callback, args, kwargs = scene.pending_calls.pop(0)
            callback(*args, **kwargs)

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

        self.finish_game_over_delay(over)
        self.press(director.BUTTON_A)
        again = director.scene_stack[-1]
        self.assertIsInstance(again, Game)
        self.assertEqual(again.score, 0)

    def test_game_over_ignores_fire_taps_until_the_score_has_been_seen(self):
        from games.demos.tutorial_game.code.tutorial_game import GameOver

        game = self.start_game()
        game.enemies.spawn(x=game.ship.x, y=game.ship.y + 2)
        self.step(0)                           # the ship is hit
        over = director.scene_stack[-1]
        self.assertIsInstance(over, GameOver)

        self.press(director.BUTTON_A)          # a player still tapping fire
        self.press(director.BUTTON_A)
        self.assertIs(director.scene_stack[-1], over)

        self.finish_game_over_delay(over)      # the restart delay has passed
        self.press(director.BUTTON_A)
        self.assertIsNot(director.scene_stack[-1], over)

    def test_enemies_that_miss_the_ship_fly_past(self):
        game = self.start_game()
        game.enemies.spawn(x=(game.ship.x + 128) % 256, y=1)
        for _ in range(80):
            self.step(0)
        self.assertEqual(len(game.enemies), 0)

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
