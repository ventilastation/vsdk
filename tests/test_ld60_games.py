"""The five LD60 "Circular Arcade" games in games/ld60.

Each one is driven through the headless director, with a virtual clock so that
the timers they use to end a game (``call_later``) run at the pace of the steps.
"""

import os
import random
import re
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

GAMES = os.path.join(ROOT, "games", "ld60")
TICK_MS = 30
# director.JOY_LEFT and JOY_RIGHT, for class attributes: the director can only
# be asked once a runtime is configured.
JOY_LEFT, JOY_RIGHT = 0x01, 0x02


def read_strips(game):
    """name: (frame width, height, frames, glyphs) from the game's yaml."""
    with open(os.path.join(GAMES, game, "images", "__images__.yaml")) as handle:
        text = handle.read()
    strips = {}
    for name, frames in re.findall(r"strip: (\S+)\s+frames: (\d+)", text):
        width = 8
        strips[name] = (width, 8, int(frames), None)
    return strips


class GameTests:
    """Tests every game must pass; mixed into one TestCase per game."""

    slug = None
    can_lose = True
    composer = "snifkey"

    def setUp(self):
        self.game_name = self.slug.split(".")[1]
        self.saved_ticks_ms = sys.modules["utime"].ticks_ms
        self.boot()

    def boot(self):
        """A fresh runtime, clock and random seed, so that booting twice in one
        test plays the same game twice."""
        reset_runtime()
        api_guard.reset()
        runtime_director = configure_runtime("headless")
        stripes.clear()
        strips = read_strips(self.game_name)

        def fake_load_rom(_filename):
            for index, (name, (width, height, frames, glyphs)) in enumerate(strips.items()):
                stripes[name] = index
                runtime_director.platform.sprites.stripes[index] = {
                    "width": width, "height": height, "frames": frames,
                    "palette": 0, "glyphs": glyphs,
                }

        runtime_director.load_rom = fake_load_rom
        # The second controller, which the headless comms otherwise lacks.
        self.joy2 = 0
        runtime_director.platform.comms.next_joy2 = lambda: self.joy2
        runtime_director.platform.comms.next_extra = lambda: 0
        self.clock = 1000
        sys.modules["utime"].ticks_ms = lambda: self.clock
        random.seed(self.id())

    def tearDown(self):
        sys.modules["utime"].ticks_ms = self.saved_ticks_ms
        reset_runtime()
        api_guard.reset()

    def step(self, buttons=0, joy2=0):
        """One tick, with ``buttons`` held on the first controller and ``joy2``
        on the second (the JOY_ and BUTTON_A bits are the same on both)."""
        self.joy2 = joy2
        director.platform.comms.push_input(bytes([buttons]))
        self.clock += TICK_MS
        try:
            director.step_once()
        except StopIteration:
            pass

    def run_ticks(self, count, buttons=0):
        for _ in range(count):
            self.step(buttons)

    def press(self, buttons):
        self.step(buttons)
        self.step(0)

    def start_game(self):
        title = load_app(self.slug)
        self.assertEqual(type(title).__name__, "Title")
        self.press(director.BUTTON_A)
        game = director.scene_stack[-1]
        self.assertEqual(type(game).__name__, "Game")
        return game

    def scene_name(self):
        return type(director.scene_stack[-1]).__name__

    def labels(self, scene):
        return [d.text for layer in scene.layers for d in layer._drawables
                if hasattr(d, "text")]

    # -- what every game does ----------------------------------------------

    def test_title_names_the_game_and_a_starts_it(self):
        title = load_app(self.slug)
        self.step(0)
        self.assertEqual(title._vs_declared_api, "vs2")
        self.assertIn("PRESS A", self.labels(title))
        self.press(director.BUTTON_A)
        self.assertEqual(self.scene_name(), "Game")

    def test_the_title_credits_the_game_and_starts_its_song_looping(self):
        title = load_app(self.slug)
        self.step(0)
        labels = self.labels(title)
        self.assertIn("designed by borisvanschooten", labels)
        self.assertIn("music by " + self.composer, labels)
        self.assertIn("vs version by alecu", labels)
        song = sys.modules[type(title).__module__].SONG
        self.assertEqual(self.music_sent(),
                         [("music %s/%s loop" % (self.slug, song)).encode()])
        # The song plays on through a game, its end and a replay.
        self.press(director.BUTTON_A)
        self.finish_with(lambda g: g.win())
        self.press(director.BUTTON_A)
        self.assertEqual(self.scene_name(), "Game")
        self.assertEqual(len(self.music_sent()), 1)

    def music_sent(self):
        return [line for line, _ in director.platform.comms.sent if line.startswith(b"music")]

    def test_game_exports_a_vs2_scene_within_the_budgets(self):
        import vs2

        game = self.start_game()
        self.run_ticks(5)
        payload = vs2.export_scene_payload(game)
        self.assertEqual(bytes(payload[:3]), b"VS2")
        census = [len(layer.sprites) for layer in game.layers]
        self.assertLessEqual(sum(census), vs2.limits.sprites)

    def test_every_game_can_be_played_for_a_long_time_without_errors(self):
        rng = random.Random(7)
        game = self.start_game()
        buttons = 0
        for tick in range(1500):
            if tick % 6 == 0:
                buttons = rng.choice((0, director.JOY_LEFT, director.JOY_RIGHT,
                                      director.JOY_UP, director.JOY_DOWN,
                                      director.JOY_LEFT | director.BUTTON_A,
                                      director.JOY_RIGHT | director.BUTTON_A,
                                      director.JOY_UP | director.BUTTON_A))
            self.step(buttons)
            if self.scene_name() == "Result":
                self.step(0)
                self.press(director.BUTTON_A)       # play again
                self.assertEqual(self.scene_name(), "Game")

    def play_on(self, controller, moves):
        """Boot, start with A and play ``moves`` (buttons, ticks) on controller 1
        or 2; returns the game and where everything in its world ended up."""
        self.boot()
        load_app(self.slug)
        press = (lambda b: self.step(b)) if controller == 1 else (lambda b: self.step(0, joy2=b))
        press(director.BUTTON_A)
        press(0)
        game = director.scene_stack[-1]
        self.assertEqual(type(game).__name__, "Game")
        for buttons, ticks in moves:
            for _ in range(ticks):
                press(buttons)
        world = ([(s.x, s.y, s.frame, s.visible) for s in game.world.sprites]
                 + [(t.x, t.view_y) for t in game.world.tilemaps])
        return game, world

    def test_either_controller_plays_and_both_play_alike(self):
        moves = ((director.JOY_RIGHT, 12), (director.JOY_DOWN, 8),
                 (director.JOY_DOWN | director.BUTTON_A, 2), (0, 3),
                 (director.JOY_LEFT, 12), (director.JOY_UP | director.BUTTON_A, 6),
                 (0, 10))
        _, idle = self.play_on(1, ())
        _, on_joy1 = self.play_on(1, moves)
        self.assertNotEqual(on_joy1, idle)          # the moves did move things
        game, on_joy2 = self.play_on(2, moves)
        self.assertEqual(on_joy2, on_joy1)
        # A on the second controller plays again, too.
        self.finish_with(lambda g: g.win())
        self.step(0, joy2=director.BUTTON_A)
        self.step(0)
        self.assertEqual(self.scene_name(), "Game")
        self.assertIsNot(director.scene_stack[-1], game)

    # How each game's tests find the player on the disc and move it round, for
    # the camera tests.
    anchor = 124            # the column the camera holds the player at
    round_button = 0        # what to hold to go round the disc, toward higher x

    def player_sprite(self, game):
        raise NotImplementedError

    def make_room(self, game):
        """Take out whatever could stop or kill the player, so that it can go
        round the disc for as long as a camera test needs."""
        raise NotImplementedError

    def ahead(self, game):
        """How many columns round the disc the player is drawn past the anchor."""
        return (self.player_sprite(game).x - self.anchor + 128) % 256 - 128

    def lead_holding(self, game, buttons):
        """Hold ``buttons`` for a while, then return how far ahead the player is
        drawn on average over ten ticks: the camera sits on whole columns, so
        any one tick is up to half a column out."""
        self.run_ticks(50, buttons)
        total = 0
        for _ in range(10):
            self.step(buttons)
            total += self.ahead(game)
        return total / 10

    def test_going_round_the_disc_the_camera_turns_a_moment_behind(self):
        game = self.start_game()
        self.make_room(game)
        self.run_ticks(60, self.round_button)
        # Drawn ahead of the anchor, but never by a twentieth of a turn (12.8
        # columns): a gap that big is jumped.
        self.assertGreater(self.ahead(game), 3)
        self.assertLess(self.ahead(game), 12.8)

    def test_when_the_player_stops_the_camera_comes_round_onto_it(self):
        if not self.round_button:
            self.skipTest("in this game you never stop going round")
        game = self.start_game()
        self.make_room(game)
        self.run_ticks(60, self.round_button)
        self.assertGreater(self.ahead(game), 3)
        self.run_ticks(150)
        self.assertAlmostEqual(self.ahead(game), 0, delta=1)

    def finish_with(self, trigger):
        """Run ``trigger`` on the game, then let its end-of-game timer run."""
        game = director.scene_stack[-1]
        trigger(game)
        self.assertFalse(game.playing)
        self.run_ticks(40)
        return director.scene_stack[-1]

    def test_losing_shows_the_result_and_a_plays_again(self):
        if not self.can_lose:
            self.skipTest("nothing in this game can kill you")
        game = self.start_game()
        result = self.finish_with(lambda g: g.lose())
        self.assertEqual(type(result).__name__, "Result")
        self.assertNotIn("NEW BEST!", self.labels(result))
        self.press(director.BUTTON_A)
        self.assertEqual(self.scene_name(), "Game")
        self.assertIsNot(director.scene_stack[-1], game)

    def test_winning_saves_the_best_time_and_only_a_faster_one_replaces_it(self):
        import vs2

        self.start_game()
        self.run_ticks(10)
        result = self.finish_with(lambda g: g.win())
        self.assertIn("NEW BEST!", self.labels(result))
        best = vs2.saves.load("best", 0)
        self.assertGreater(best, 0)
        # A slower win is not a record.
        self.press(director.BUTTON_A)
        self.run_ticks(best + 20)
        slower = self.finish_with(lambda g: g.win())
        self.assertNotIn("NEW BEST!", self.labels(slower))
        self.assertEqual(vs2.saves.load("best", 0), best)


class SpiralTunnelTests(GameTests, unittest.TestCase):
    slug = "ld60.spiral_tunnel"

    def middle(self, game, row):
        """Where a ship can fly in the open, in the middle of the tunnel."""
        return (game.left[row] * 8 + game.span[row] * 4 - 4) % 256

    def test_the_tunnel_is_wide_and_each_edge_moves_two_to_five_tiles_a_row(self):
        from games.ld60.spiral_tunnel.code.spiral_tunnel import ROWS

        for _ in range(5):
            game = self.start_game()
            for row in range(ROWS):
                self.assertTrue(13 <= game.span[row] <= 16, "row %d" % row)
                self.assertTrue(2 <= game.left_shift[row] <= 5, "row %d" % row)
                self.assertTrue(2 <= game.right_shift[row] <= 5, "row %d" % row)
                if row:
                    # Each row starts where the slant of the one above ended.
                    self.assertEqual(game.left[row],
                                     (game.left[row - 1] + game.left_shift[row - 1]) % 32)
                    self.assertEqual(game.span[row], game.span[row - 1]
                                     + game.right_shift[row - 1] - game.left_shift[row - 1])
            director.scene_stack.clear()
            self.setUp_again()

    def setUp_again(self):
        self.tearDown()
        self.setUp()

    def test_what_is_drawn_as_wall_is_wall_and_what_is_drawn_open_is_open(self):
        from games.ld60.spiral_tunnel.code.spiral_tunnel import (
            COLS, NO_TILE, ROCKS, ROCKS_AT, ROWS)

        game = self.start_game()
        for row in range(ROWS - 1):
            for col in range(COLS):
                tile = game.cells[row * COLS + col]
                centre = (col * 8 + 4, row * 8 + 4)
                if tile == NO_TILE:
                    self.assertFalse(game.wall_at(*centre), (row, col))
                elif tile == 0 or ROCKS_AT <= tile < ROCKS_AT + ROCKS:
                    self.assertTrue(game.wall_at(*centre), (row, col))

    def test_rocks_are_scattered_through_the_solid_wall(self):
        from games.ld60.spiral_tunnel.code.spiral_tunnel import ROCKS, ROCKS_AT

        game = self.start_game()
        rocks = [tile for tile in game.cells if ROCKS_AT <= tile < ROCKS_AT + ROCKS]
        solid = len(rocks) + sum(1 for tile in game.cells if tile == 0)
        # About half the solid wall, with every kind of rock in it.
        self.assertTrue(0.35 * solid < len(rocks) < 0.65 * solid, (len(rocks), solid))
        self.assertEqual(set(rocks), set(range(ROCKS_AT, ROCKS_AT + ROCKS)))

    def test_the_slanted_edge_is_a_straight_line_across_the_tiles_it_spans(self):
        game = self.start_game()
        row = 5
        left = game.left[row] * 8
        shift = game.left_shift[row]
        # A point just inside the open side of the left edge, a quarter, half and
        # three quarters of the way down the row, moves right as the edge does.
        for depth in (2, 4, 6):
            edge = left + shift * depth
            self.assertTrue(game.wall_at(edge - 1, row * 8 + depth))
            self.assertFalse(game.wall_at(edge + 1, row * 8 + depth))

    def test_the_ship_starts_in_the_open_at_the_top_of_the_disc(self):
        game = self.start_game()
        self.assertFalse(game.wall_at(game.wx + 4, game.wy + 4))
        # A tick in, it is a column ahead: the camera turns a moment behind.
        self.assertAlmostEqual(game.ship.x, 124, delta=2)

    def test_the_ship_flies_round_and_down(self):
        game = self.start_game()
        x, y = game.wx, game.wy
        self.step(director.JOY_DOWN)
        self.assertGreater(game.wy, y)
        self.assertGreater(game.wx, x)         # always flying round
        self.step(director.JOY_UP)
        self.assertAlmostEqual(game.wy, y)

    def test_right_speeds_you_round_and_left_slows_you(self):
        game = self.start_game()
        before = game.wx
        self.step(director.JOY_RIGHT)
        fast = game.wx - before
        before = game.wx
        self.step(director.JOY_LEFT)
        slow = game.wx - before
        self.assertGreater(fast, slow)

    def test_flying_into_the_wall_ends_the_game(self):
        game = self.start_game()
        game.wx = (game.left[2] * 8 - 12) % 256        # in the wall, left of the tunnel
        game.wy = 2 * 8
        self.step(0)
        self.assertFalse(game.playing)
        self.run_ticks(40)
        self.assertEqual(self.scene_name(), "Result")

    def test_reaching_the_bottom_of_the_tunnel_wins(self):
        from games.ld60.spiral_tunnel.code.spiral_tunnel import ROWS

        game = self.start_game()
        row = ROWS - 3
        game.wy = row * 8
        game.wx = float(self.middle(game, row))
        self.step(0)
        self.assertFalse(game.playing)
        self.run_ticks(40)
        result = director.scene_stack[-1]
        self.assertEqual(type(result).__name__, "Result")
        self.assertTrue(result.won)

    def test_a_bomb_destroys_a_ufo_and_a_ufo_destroys_the_ship(self):
        game = self.start_game()
        ufo = game.ufos[0]
        # Park the first UFO right in front of the ship, in the open.
        ufo.wx = game.wx + 20
        ufo.wy = game.wy
        ufo.vy = 0
        self.step(director.BUTTON_A)
        self.assertEqual(sum(1 for b in game.bombs if b.visible), 1)
        for _ in range(15):
            self.step(0)
            if not ufo.alive:
                break
        self.assertFalse(ufo.alive)
        self.assertFalse(ufo.visible)
        self.assertTrue(game.playing)
        other = game.ufos[1]
        other.wx, other.wy, other.vy = game.wx, game.wy, 0
        self.step(0)
        self.assertFalse(game.playing)

    def test_bombs_are_limited_and_have_a_cooldown(self):
        game = self.start_game()
        self.step(director.BUTTON_A)
        self.step(director.BUTTON_A)
        self.assertEqual(sum(1 for b in game.bombs if b.visible), 1)
        self.run_ticks(10, director.BUTTON_A)
        self.assertLessEqual(sum(1 for b in game.bombs if b.visible), 4)

    def player_sprite(self, game):
        return game.ship

    def make_room(self, game):
        """No walls and no UFOs, so the ship can be flown anywhere to watch the
        camera."""
        game.wall_at = lambda px, py: False
        for ufo in game.ufos:
            ufo.alive = False
            ufo.hide()

    def test_the_camera_follows_the_ship_down_the_tunnel(self):
        from games.ld60.spiral_tunnel.code.spiral_tunnel import PLAYER_DEPTH

        game = self.start_game()
        self.make_room(game)
        self.assertEqual(game.walls.view_y, 0)
        game.wy = 30 * 8
        self.step(0)
        self.assertLess(game.walls.view_y, 30 * 8 - PLAYER_DEPTH)   # on its way
        self.run_ticks(60)
        self.assertEqual(game.walls.view_y, 30 * 8 - PLAYER_DEPTH)
        self.assertEqual(game.ship.y, PLAYER_DEPTH)

    def test_steering_in_or_out_moves_the_ship_at_once_and_the_camera_after_it(self):
        from games.ld60.spiral_tunnel.code.spiral_tunnel import PLAYER_DEPTH

        game = self.start_game()
        self.make_room(game)
        game.wy = 20 * 8.0
        self.run_ticks(60)
        self.assertEqual(game.ship.y, PLAYER_DEPTH)
        view_y = game.walls.view_y
        self.step(director.JOY_DOWN)
        self.assertEqual(game.ship.y, PLAYER_DEPTH + 1)     # the ship has moved
        self.assertEqual(game.walls.view_y, view_y)         # the camera not yet
        self.run_ticks(30, director.JOY_DOWN)
        self.assertGreater(game.walls.view_y, view_y + 15)  # it follows...
        self.assertGreater(game.ship.y, PLAYER_DEPTH + 4)   # ...a little behind
        self.run_ticks(60)
        self.assertEqual(game.ship.y, PLAYER_DEPTH)         # and catches up
        self.run_ticks(30, director.JOY_UP)
        self.assertLess(game.ship.y, PLAYER_DEPTH - 4)      # the same going out

    def test_the_faster_you_fly_round_the_further_ahead_you_are_drawn(self):
        game = self.start_game()
        self.make_room(game)
        cruising = self.lead_holding(game, 0)
        self.assertGreater(self.lead_holding(game, director.JOY_RIGHT), cruising + 0.5)
        self.assertLess(self.lead_holding(game, director.JOY_LEFT), cruising - 0.5)

    def test_the_ship_stays_a_quarter_of_the_way_in_even_at_the_end_of_the_tunnel(self):
        from games.ld60.spiral_tunnel.code.spiral_tunnel import PLAYER_DEPTH, ROWS

        game = self.start_game()
        self.make_room(game)
        row = ROWS - 5
        game.wy = row * 8.0
        self.run_ticks(60)
        self.assertEqual(game.walls.view_y, row * 8 - PLAYER_DEPTH)
        self.assertEqual(game.ship.y, PLAYER_DEPTH)


class DodgeEmTests(GameTests, unittest.TestCase):
    slug = "ld60.dodge_em"

    def test_the_track_has_five_lanes_with_a_pill_on_every_free_tile(self):
        from games.ld60.dodge_em.code.dodge_em import COLS, LANES, PILL

        game = self.start_game()
        self.assertEqual(game.pills, 5 * (COLS - 4))
        for lane in LANES:
            pills = [c for c in range(COLS) if game.cells[lane * COLS + c] == PILL]
            self.assertEqual(len(pills), COLS - 4)
        # Walls between the lanes have exactly four gaps (none in the outer two).
        for row in (2, 4, 6, 8):
            gaps = [c for c in range(COLS) if not game.solid[row * COLS + c]]
            self.assertEqual(gaps, [6, 14, 22, 30])
        for row in (0, 10):
            self.assertEqual(sum(game.solid[row * COLS:(row + 1) * COLS]), COLS)

    def test_the_outer_wall_is_one_led_wide_on_the_rim(self):
        from games.ld60.dodge_em.code.dodge_em import SHIFT, TILE

        game = self.start_game()
        # Row 0 is drawn from depth SHIFT, so only its last pixel row (depth 0,
        # the outermost LED) is on the disc, and the first lane starts right after.
        self.assertEqual(game.track.y, SHIFT)
        self.assertEqual(SHIFT + TILE, 1)
        self.assertEqual(game.player.sprite.y, 1)

    def test_the_player_drives_round_eating_pills_and_the_camera_follows(self):
        game = self.start_game()
        pills = game.pills
        self.run_ticks(60)
        self.assertLess(game.pills, pills)
        self.assertTrue(3 < self.ahead(game) < 12.8)

    def player_sprite(self, game):
        return game.player.sprite

    def make_room(self, game):
        """The red cars park where they are, off your lane."""
        for car in game.enemies:
            car.go(car.col, car.row, 10 ** 6)

    def test_the_faster_you_drive_the_further_ahead_you_are_drawn(self):
        game = self.start_game()
        self.make_room(game)
        cruising = self.lead_holding(game, 0)
        self.assertGreater(self.lead_holding(game, director.JOY_RIGHT), cruising + 0.5)
        self.assertLess(self.lead_holding(game, director.JOY_LEFT), cruising - 0.5)

    def test_right_is_faster_than_left(self):
        game = self.start_game()
        self.run_ticks(30, director.JOY_RIGHT)
        fast = game.player.x
        self.step(director.BUTTON_Y)
        # A fresh game, held on slow.
        director.scene_stack.clear()
        game = self.start_game()
        self.run_ticks(30, director.JOY_LEFT)
        self.assertGreater(fast, game.player.x)

    def test_you_can_only_change_lane_at_a_gap(self):
        game = self.start_game()
        player = game.player
        self.run_ticks(3, director.JOY_DOWN)       # column 1 has a wall below
        self.assertEqual(player.row, 1)
        self.assertGreater(player.col, 1)
        # At column 6 the wall has a gap.
        while player.col != 6 or player.ticks:
            self.step(0)
        self.step(director.JOY_DOWN)
        self.assertEqual((player.col, player.row), (6, 3))

    def test_eating_the_last_pill_wins(self):
        from games.ld60.dodge_em.code.dodge_em import NO_TILE, PILL

        game = self.start_game()
        for i, cell in enumerate(game.cells):
            if cell == PILL and i != 1 * 32 + 3:
                game.cells[i] = NO_TILE
        game.pills = 1
        self.run_ticks(60)
        self.assertEqual(game.pills, 0)
        self.assertFalse(game.playing)

    def test_the_red_cars_run_the_other_way_and_a_crash_ends_the_game(self):
        game = self.start_game()
        enemy = game.enemies[0]
        before = enemy.x
        self.run_ticks(50)
        self.assertLess(enemy.x, before)
        enemy.ticks = 0
        enemy.x = game.player.x
        enemy.y = game.player.y
        self.step(0)
        self.assertFalse(game.playing)
        self.run_ticks(40)
        self.assertEqual(self.scene_name(), "Result")

    def test_red_cars_change_lane_toward_you_through_a_gap(self):
        game = self.start_game()
        enemy = game.enemies[0]
        enemy.ticks = 0
        enemy.col, enemy.x = 6, 6 * 8
        enemy.row, enemy.y = 5, 5 * 8
        game.player.row = 1                       # two lanes away
        self.step(0)
        self.assertEqual(enemy.row, 3)


class CatchTheRobotsTests(GameTests, unittest.TestCase):
    slug = "ld60.catch_the_robots"
    can_lose = False

    def reachable(self, game):
        from games.ld60.catch_the_robots.code.catch_the_robots import COLS
        seen = {(2, 2)}
        todo = [(2, 2)]
        while todo:
            col, row = todo.pop()
            for d_col, d_row in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cell = ((col + d_col) % COLS, row + d_row)
                if cell not in seen and 0 < cell[1] < 34 and not game.solid[cell[1] * COLS + cell[0]]:
                    seen.add(cell)
                    todo.append(cell)
        return seen

    def test_the_maze_is_one_connected_set_of_passages_holding_every_robot(self):
        for _ in range(3):
            game = self.start_game()
            open_cells = self.reachable(game)
            self.assertGreater(len(open_cells), 400)
            self.assertEqual(len(game.robots), 20)
            for robot in game.robots:
                self.assertIn((robot.col, robot.row), open_cells)
            director.scene_stack.clear()

    def test_the_player_cannot_walk_through_walls_but_can_round_the_disc(self):
        game = self.start_game()
        player = game.player
        self.run_ticks(10, director.JOY_UP)        # the wall above row 2
        self.assertEqual((player.col, player.row), (2, 2))
        # Wrapping: the maze is open all the way round, so keep going.
        start = player.col
        for _ in range(400):
            self.step(director.JOY_LEFT)
        self.assertLessEqual(abs(player.col - start), 32)

    def test_the_player_moves_along_a_corridor(self):
        game = self.start_game()
        player = game.player
        for direction in (director.JOY_RIGHT, director.JOY_DOWN, director.JOY_LEFT):
            before = (player.col, player.row)
            self.run_ticks(6, direction)
            if (player.col, player.row) != before:
                return
        self.fail("the start of the maze is walled in")

    def test_robots_follow_the_walls_and_stay_in_the_passages(self):
        game = self.start_game()
        robot = game.robots[0]
        start = (robot.col, robot.row)
        for _ in range(600):
            self.step(0)
            self.assertFalse(game.solid[robot.row * 32 + robot.col])
        self.assertNotEqual((robot.col, robot.row), start)

    def test_touching_a_robot_catches_it_and_the_last_one_wins(self):
        game = self.start_game()
        for robot in game.robots[1:]:
            robot.alive = False
            robot.sprite.hide()
        game.left = 1
        robot = game.robots[0]
        robot.ticks = 0
        robot.x, robot.y = game.player.x, game.player.y
        self.step(0)
        self.assertFalse(robot.alive)
        self.assertEqual(game.left, 0)
        self.assertFalse(game.playing)
        self.run_ticks(40)
        self.assertEqual(self.scene_name(), "Result")

    round_button = JOY_RIGHT

    def player_sprite(self, game):
        return game.player.sprite

    def make_room(self, game):
        """No walls and no robots."""
        game.is_wall = lambda col, row: False
        for robot in game.robots:
            robot.alive = False
            robot.sprite.hide()

    def test_the_wall_outlines_are_drawn_over_the_fill_from_the_same_cells(self):
        game = self.start_game()
        self.assertIs(game.outlines.cells, game.maze.cells)
        # Fill, then outlines, then the robots and the player over both.
        drawables = game.world._drawables
        self.assertLess(drawables.index(game.maze), drawables.index(game.outlines))
        self.assertLess(drawables.index(game.outlines), drawables.index(game.player.sprite))
        # They scroll together.
        game.player.y = 20 * 8
        game.player.row = 20
        self.run_ticks(20, director.JOY_RIGHT)
        self.assertGreater(game.maze.view_y, 0)
        self.assertEqual((game.outlines.x, game.outlines.view_y),
                         (game.maze.x, game.maze.view_y))

    def test_the_camera_scrolls_down_the_maze(self):
        game = self.start_game()
        self.assertEqual(game.maze.view_y, 0)
        game.player.y = 20 * 8
        game.player.row = 20
        self.step(0)
        self.assertLess(game.maze.view_y, 15 * 8)          # on its way
        self.run_ticks(60)
        self.assertEqual(game.maze.view_y, 15 * 8)
        # At the bottom of the maze the view goes on following the player, so the
        # player is never deeper than five rows down the view (halfway to the
        # centre), even though the map has no more rows to show there.
        game.player.y = 32 * 8
        game.player.row = 32
        self.run_ticks(60)
        self.assertEqual(game.maze.view_y, 27 * 8)
        self.assertEqual(game.player.sprite.y, 5 * 8)

    def test_running_down_the_maze_the_camera_follows_a_moment_behind(self):
        game = self.start_game()
        self.make_room(game)
        self.run_ticks(20, director.JOY_DOWN)
        self.assertGreater(game.player.sprite.y, 5 * 8 + 4)  # drawn further down
        self.run_ticks(60)
        self.assertEqual(game.player.sprite.y, 5 * 8)       # until it catches up


class RimRunnerTests(GameTests, unittest.TestCase):
    slug = "ld60.rim_runner"
    composer = "JuanJuan"

    def test_the_runner_starts_on_the_rim_at_the_bottom_of_the_disc(self):
        game = self.start_game()
        self.run_ticks(3)
        self.assertTrue(game.grounded)
        self.assertEqual(game.runner.x % 256, 252)
        # On the lowest floor, with four pixels of it below.
        self.assertEqual(game.runner.y, game.wy - (game.floor_depth - 4))

    anchor = 252            # the bottom of the disc
    round_button = JOY_LEFT     # at the bottom, left is toward higher x

    def player_sprite(self, game):
        return game.runner

    def make_room(self, game):
        """A rim with no holes, nothing on it to run into, and no birds; the
        runner stands on it."""
        game.solid_at = lambda x, y: y < game.floor_depth
        game.wy = float(game.floor_depth)
        game.vy = 0.0
        game.grounded = True
        for bird in game.birds:
            bird.alive = False
            bird.hide()

    def hold_at(self, game, wy, ticks):
        """Keep the runner hanging at depth ``wy`` while the view catches up."""
        for _ in range(ticks):
            game.wy = wy
            game.vy = 0.0
            game.grounded = False
            self.step(0)

    def test_the_view_scrolls_inward_with_the_runner_to_keep_it_near_the_rim(self):
        from games.ld60.rim_runner.code.rim_runner import PLAYER_DEPTH

        game = self.start_game()
        # Up on a platform the whole view has moved with the runner, which stays
        # PLAYER_DEPTH from the rim.
        self.hold_at(game, 13 * 8.0, 60)
        self.assertAlmostEqual(game.runner.y, PLAYER_DEPTH, delta=1)
        self.assertAlmostEqual(game.rim.view_y, game.wy - PLAYER_DEPTH, delta=1)

    def test_the_view_follows_a_jump_a_moment_behind(self):
        from games.ld60.rim_runner.code.rim_runner import PLAYER_DEPTH

        game = self.start_game()
        self.make_room(game)
        self.run_ticks(60)
        self.step(director.JOY_UP)
        highest = 0
        for _ in range(120):
            self.step(0)
            highest = max(highest, game.runner.y)
            if game.grounded:
                break
        # Rising, the runner is drawn further in than PLAYER_DEPTH: the view
        # only catches up later.
        self.assertGreater(highest, PLAYER_DEPTH + 3)

    def test_the_view_shows_only_four_pixels_of_ground_below_the_lowest_floor(self):
        from games.ld60.rim_runner.code.rim_runner import GROUND_SHOWN, PLAYER_DEPTH

        game = self.start_game()
        floor = game.floor_depth
        self.assertIn(floor, (16, 24, 32, 40))
        self.assertTrue(any(game.solid[(floor // 8 - 1) * 32 + c]
                            and not game.solid[(floor // 8) * 32 + c] for c in range(32)))
        # Standing on the lowest floor: four pixels of floor below the runner,
        # though the runner could be PLAYER_DEPTH deep.
        game.wy = float(floor)
        game.vy = 0.0
        game.grounded = False
        self.step(0)
        self.assertEqual(game.rim.view_y, floor - GROUND_SHOWN)
        self.assertAlmostEqual(game.runner.y, GROUND_SHOWN, delta=1)
        self.assertLess(GROUND_SHOWN, PLAYER_DEPTH)
        # Falling into a hole does not scroll the view outward any further.
        game.wy = 2.0
        self.step(0)
        self.assertEqual(game.rim.view_y, floor - GROUND_SHOWN)

    def test_the_view_stops_scrolling_where_the_level_ends(self):
        from games.ld60.rim_runner.code.rim_runner import ROWS, VIEW_H

        game = self.start_game()
        self.hold_at(game, (ROWS - 2) * 8.0, 60)
        self.assertEqual(game.rim.view_y, ROWS * 8 - VIEW_H)
        self.assertGreater(game.runner.y, 5)

    def test_birds_are_drawn_relative_to_the_scrolled_view(self):
        game = self.start_game()
        bird = game.birds[0]
        bird.vx = bird.vy = 0
        bird.turn = 99
        bird.wx, bird.wy = game.wx + 40, 10 * 8.0
        self.step(0)
        self.assertTrue(bird.visible)
        self.assertAlmostEqual(bird.y, 10 * 8 - game.rim.view_y, delta=1)

    def test_left_and_right_run_round_the_rim(self):
        game = self.start_game()
        self.run_ticks(2)
        x = game.wx
        self.step(director.JOY_LEFT)
        self.assertGreater(game.wx, x)         # at the bottom, left is higher x
        self.run_ticks(2, director.JOY_RIGHT)
        self.assertLess(game.wx, x + 1.2)

    def test_jumping_leaves_the_ground_and_comes_back(self):
        game = self.start_game()
        self.run_ticks(2)
        floor = game.wy
        self.step(director.JOY_UP)
        self.assertFalse(game.grounded)
        peak = floor
        for _ in range(120):
            self.step(0)
            peak = max(peak, game.wy)
            if game.grounded:
                break
        self.assertTrue(game.grounded)
        self.assertAlmostEqual(game.wy, floor)
        # About four and a half tiles, as in the original.
        self.assertGreater(peak - floor, 4 * 8)
        self.assertLess(peak - floor, 5 * 8)

    def test_falling_through_a_hole_in_the_rim_ends_the_game(self):
        game = self.start_game()
        game.wx = 3 * 8 + 1               # column 3 is always a hole
        game.wy = 2 * 8
        game.vy = 0.0
        game.grounded = False
        for _ in range(100):
            self.step(0)
            if not game.playing:
                break
        self.assertFalse(game.playing)
        self.run_ticks(40)
        self.assertEqual(self.scene_name(), "Result")

    def test_eggs_are_collected_and_the_last_one_wins(self):
        from games.ld60.rim_runner.code.rim_runner import EGG, NO_TILE

        game = self.start_game()
        eggs = [i for i, cell in enumerate(game.cells) if cell == EGG]
        self.assertEqual(len(eggs), game.eggs)
        self.assertGreater(len(eggs), 5)
        for index in eggs[1:]:
            game.cells[index] = NO_TILE
        game.eggs = 1
        row, col = divmod(eggs[0], 32)
        game.wx = col * 8
        game.wy = row * 8
        game.vy = 0.0
        self.step(0)
        self.assertEqual(game.eggs, 0)
        self.assertFalse(game.playing)

    def test_landing_on_a_bird_kills_it_and_bounces_but_touching_it_from_the_side_kills_you(self):
        game = self.start_game()
        bird = game.birds[0]
        bird.vx = bird.vy = 0
        bird.turn = 99
        game.wy = 60.0
        bird.wx, bird.wy = game.wx, 55.0
        game.vy = -1.0
        game.grounded = False
        self.step(0)
        self.assertFalse(bird.alive)
        self.assertGreater(game.vy, 1)
        self.assertTrue(game.playing)
        other = game.birds[1]
        other.vx = other.vy = 0
        other.turn = 99
        game.wy = 70.0
        game.vy = 0.0
        other.wx, other.wy = game.wx + 4, 70.0
        self.step(0)
        self.assertFalse(game.playing)

    def test_platforms_stop_you_from_jumping_through_them(self):
        game = self.start_game()
        # Find a platform floating above the rim and stand below it.
        row = next(r for r in range(8, 16) for c in range(32) if game.solid[r * 32 + c])
        col = next(c for c in range(32) if game.solid[row * 32 + c] and not game.solid[(row - 1) * 32 + c])
        game.wx = col * 8
        game.wy = (row - 2) * 8
        game.vy = 2.0
        game.grounded = False
        for _ in range(10):
            self.step(0)
        self.assertLess(game.wy, row * 8)


class DefenderTests(GameTests, unittest.TestCase):
    slug = "ld60.defender"
    round_button = JOY_RIGHT

    def player_sprite(self, game):
        return game.ship

    def make_room(self, game):
        """No aliens, so nothing shoots."""
        for alien in game.aliens:
            alien.alive = False
            alien.hide()

    def test_the_planet_has_mountains_and_an_alien_over_each_column(self):
        from games.ld60.defender.code.defender import COLS, ROWS

        game = self.start_game()
        self.assertEqual(len(game.aliens), 21)
        tops = []
        for col in range(COLS):
            column = [r for r in range(ROWS) if game.solid[r * COLS + col]]
            self.assertEqual(column, list(range(column[0], ROWS)))
            tops.append(column[0])
        self.assertGreaterEqual(min(tops), 5)
        self.assertLessEqual(max(tops), 12)
        self.assertGreater(max(tops) - min(tops), 2)

    def test_the_arrows_fly_the_ship_and_up_goes_toward_the_rim(self):
        game = self.start_game()
        game.wy = 40.0
        x, y = game.wx, game.wy
        self.step(director.JOY_RIGHT)
        self.assertGreater(game.wx, x)
        self.step(director.JOY_UP)
        self.assertLess(game.wy, y)
        self.step(director.JOY_LEFT)
        self.assertEqual(game.facing, -1)
        self.assertTrue(game.ship.flip_x)

    def test_the_ship_cannot_leave_the_sky_for_the_depths(self):
        from games.ld60.defender.code.defender import FLOOR

        game = self.start_game()
        self.run_ticks(200, director.JOY_DOWN)       # into a mountain, or the floor
        self.assertLessEqual(game.wy, FLOOR)

    def test_a_shot_kills_an_alien_and_the_last_one_wins(self):
        game = self.start_game()
        for alien in game.aliens[1:]:
            alien.alive = False
            alien.hide()
        game.left = 1
        target = game.aliens[0]
        target.vx = target.vy = 0.0
        target.turn = 999
        target.wx, target.wy = game.wx + 24, game.wy
        self.step(director.BUTTON_A)
        for _ in range(20):
            self.step(0)
            if not target.alive:
                break
        self.assertFalse(target.alive)
        self.assertEqual(game.left, 0)
        self.assertFalse(game.playing)
        self.run_ticks(40)
        self.assertTrue(director.scene_stack[-1].won)

    def test_shots_fly_the_way_you_face_and_there_are_only_four(self):
        game = self.start_game()
        self.step(director.JOY_LEFT | director.BUTTON_A)
        shot = next(s for s in game.shots if s.life)
        self.assertLess(shot.vx, 0)
        self.run_ticks(40, director.BUTTON_A)
        self.assertLessEqual(sum(1 for s in game.shots if s.life), 4)

    def still_aliens(self, game):
        for alien in game.aliens:
            alien.vx = alien.vy = 0.0
            alien.turn = 999
            alien.reload = 9999
            alien.wy = 100.0

    def test_touching_an_alien_ends_the_game(self):
        game = self.start_game()
        self.still_aliens(game)
        game.aliens[0].wx, game.aliens[0].wy = game.wx, game.wy
        self.step(0)
        self.assertFalse(game.playing)

    def test_an_alien_shot_ends_the_game(self):
        game = self.start_game()
        self.still_aliens(game)
        shot = game.alien_shots[0]
        shot.wx, shot.wy, shot.vx, shot.vy, shot.life = game.wx, game.wy, 0.0, 0.0, 10
        shot.show()
        self.step(0)
        self.assertFalse(game.playing)

    def test_flying_into_a_mountain_ends_the_game(self):
        game = self.start_game()
        self.still_aliens(game)
        col = next(c for c in range(32) if game.solid[10 * 32 + c])
        game.wx = col * 8.0
        game.wy = 80.0
        self.step(0)
        self.assertFalse(game.playing)

    def test_aliens_aim_their_shots_at_you(self):
        game = self.start_game()
        for alien in game.aliens[1:]:
            alien.alive = False
            alien.hide()
        alien = game.aliens[0]
        alien.vx = alien.vy = 0.0
        alien.turn = 999
        alien.wx, alien.wy = game.wx + 40, game.wy
        alien.reload = 1
        self.step(0)
        shot = next(s for s in game.alien_shots if s.life)
        self.assertLess(shot.vx, 0)          # toward the ship
        self.assertAlmostEqual(shot.vy, 0.0, places=3)


class LaunchTests(unittest.TestCase):
    def test_the_games_are_listed_in_their_own_menu_group(self):
        from ventilastation import catalog

        entries = catalog.discover_game_entries(os.path.join(ROOT, "games"), group="ld60")
        self.assertEqual(
            [slug for _order, slug, _strip, _frame, _title in sorted(entries)],
            ["ld60.spiral_tunnel", "ld60.catch_the_robots", "ld60.rim_runner",
             "ld60.dodge_em", "ld60.defender"])
        self.assertEqual([title for *_rest, title in sorted(entries)],
                         ["Spiral Tunnel", "Catch the Robots", "Rim Runner",
                          "Dodge 'Em", "Defender"])

    def test_every_game_has_its_own_menu_icon_and_sounds_for_what_it_plays(self):
        for name in ("spiral_tunnel", "catch_the_robots", "rim_runner", "dodge_em", "defender"):
            folder = os.path.join(GAMES, name)
            self.assertTrue(os.path.exists(os.path.join(folder, "menu.png")), name)
            with open(os.path.join(folder, "code", name + ".py")) as handle:
                source = handle.read()
            songs = re.findall(r'^SONG = "(\w+)"', source, re.M)
            self.assertEqual(len(songs), 1, name)
            for sound in set(re.findall(r'audio\.sound\("(\w+)"\)', source)) | set(songs):
                self.assertTrue(os.path.exists(os.path.join(folder, "sounds", sound + ".mp3")),
                                "%s needs sounds/%s.mp3" % (name, sound))


if __name__ == "__main__":
    unittest.main()
