"""Headless coverage for games/vs2_examples/vyruss_vs2 -- T18's port of
games/alecu/vyruss_vs2/code/vyruss_vs2.py, following the exact T15 "scene
editor / build() generator" precedent games/vs2_examples/vixeous already
proved: the declarative object graph (layers, sprite pools, sprites,
Behaviors) that the original build() constructed by hand now lives in
games/vs2_examples/vyruss_vs2/code/vyruss_vs2_scene.vs2model.json and is
generated into vyruss_vs2_scene.py by tools/vs2_scene_gen, with the
tick-by-tick game logic (input, the baddie entrance/attack choreography,
collision, scoring, level progression, the player's explode/respawn/
game-over sequence) hand-written in the companion
games/vs2_examples/vyruss_vs2/code/vyruss_vs2.py, exactly like the
original.

This does not re-run games/alecu/vyruss_vs2's own test suite (that game
is untouched -- see tests/test_vyruss_vs2.py); it exercises the port's own
module (a different slug, "vs2_examples.vyruss_vs2") and, in particular,
the seams the generator/behavior-catalog port actually introduced:
laser/bomb Moving+DespawnBeyond, and the explosions pool's
Transient(animate=True, ticks=5) lifecycle end to end. The baddie
entrance choreography's fixed five-phase part now runs inside a real
generated Behavior (BaddieFormation, games/vs2_examples/vyruss_vs2/code/
build_baddie_formation.py) attached in vyruss_vs2.py's on_build_5 --
proven tick-by-tick against the original in its own dedicated test,
tests/test_vyruss_vs2_baddie_formation.py, not here. The final TravelTo
approach and the attack run's own runtime reassignment
(update_attacking()) stay hand-written -- see vyruss_vs2.py's own module
docstring for why -- so those two are covered here as ordinary game
logic, the same way tests/test_vyruss_vs2.py already covers the whole
thing for the original.
"""

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

VYRUSS_METADATA = {
    "disparo.png": (3, 8, 2),
    "explosion.png": (32, 32, 5),
    "explosion_nave.png": (32, 32, 4),
    "galaga.png": (16, 16, 12),
    "ll9.png": (16, 16, 4),
    "gameover.png": (64, 20, 1),
    "numerals.png": (4, 5, 12),
    "tierra.png": (256, 54, 1),
    "marte.png": (256, 54, 1),
    "jupiter.png": (256, 54, 1),
    "saturno.png": (256, 54, 1),
}


class VyrussVs2ExamplesTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        runtime_director = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            for index, (name, values) in enumerate(VYRUSS_METADATA.items()):
                width, height, frames = values
                stripes[name] = index
                runtime_director.platform.sprites.stripes[index] = {
                    "width": width,
                    "height": height,
                    "frames": frames,
                    "palette": 0,
                    "glyphs": (
                        "0123456789 *"
                        if name == "numerals.png" else None
                    ),
                }

        runtime_director.load_rom = fake_load_rom

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def step_buttons(self, buttons=0):
        director.platform.comms.push_input(bytes([buttons]))
        try:
            director.step_once()
        except StopIteration:
            pass

    # -- build() sanity -------------------------------------------------

    def test_builds_from_the_generated_scene_without_error(self):
        scene = load_app("vs2_examples.vyruss_vs2")

        self.assertEqual(scene._vs_declared_api, "vs2")
        self.assertIs(scene.world._drawables[0], scene.player)
        self.assertIs(scene.planet.layer, scene.fullscreen)
        self.assertIs(scene.scoreboard.layer, scene.hud)
        self.assertFalse(scene.planet.visible)
        self.assertFalse(scene.game_over.visible)
        self.assertEqual(scene.player.y, -1)  # RIM_Y, set by start_level()
        self.assertEqual(scene.state, 0)  # ENTERING
        self.assertEqual(scene.level, 0)
        self.assertEqual(scene.score, 0)
        self.assertEqual(scene.lives, 3)
        self.assertEqual(scene.waves, 2)  # LEVELS[0]
        self.assertEqual(scene.simultaneous_bombs, 3)

    def test_runs_many_ticks_without_crashing(self):
        scene = load_app("vs2_examples.vyruss_vs2")
        for _ in range(600):
            self.step_buttons(0)
        # The scene never raised, and baddies have been spawned along the
        # way (ENTERING keeps calling add_baddie() every 8 ticks).
        self.assertGreater(scene.num_baddies, 0)

    # -- baddie entrance / attack choreography ---------------------------
    # Entirely hand-written (vyruss_vs2.py's own module docstring explains
    # why the TravelTo/TravelX/TravelCloser/TravelAway queue does not map
    # onto PathFollowing or any other catalog Behavior); this is ordinary
    # game logic, unaffected by the port, exercised here the same way
    # tests/test_vyruss_vs2.py exercises it for the original.

    def test_baddie_entrance_follows_its_queued_movements(self):
        scene = load_app("vs2_examples.vyruss_vs2")
        for _ in range(8):
            self.step_buttons(0)
        self.assertEqual(len(scene.everyone), 1)
        baddie = scene.everyone[0]

        positions = []
        for _ in range(150):
            self.step_buttons(0)
            positions.append((baddie.x, baddie.y))

        self.assertGreater(len(set(positions)), 80)
        self.assertGreaterEqual(min(y for _x, y in positions), 35)
        # The entrance choreography now runs inside the attached
        # BaddieFormation Behavior (see vyruss_vs2.py's on_build_5, and
        # games/vs2_examples/vyruss_vs2/code/build_baddie_formation.py) --
        # 150 ticks is real progress through its states but not the full
        # ~153-tick sequence, so check it has actually advanced past the
        # first state rather than checking baddie.movements (which stays
        # None the whole time BaddieFormation is still running -- see
        # add_baddie()'s own comment).
        from games.vs2_examples.vyruss_vs2.code.baddie_formation import BaddieFormation
        behavior = scene.baddies.behavior(BaddieFormation)
        self.assertNotEqual(behavior.state_name(baddie), "closer1")

    def test_group_reaches_attacking_and_a_baddie_attacks(self):
        from games.vs2_examples.vyruss_vs2.code.vyruss_vs2 import ATTACKING

        scene = load_app("vs2_examples.vyruss_vs2")
        ticks = 0
        while scene.state != ATTACKING and ticks < 2000:
            self.step_buttons(0)
            ticks += 1
        self.assertEqual(scene.state, ATTACKING)
        self.assertGreater(len(scene.everyone), 0)

        attacked = False
        bombed = False
        for _ in range(200):
            self.step_buttons(0)
            if scene.attacking:
                attacked = True
            if len(scene.bombs):
                bombed = True
        self.assertTrue(attacked, "no baddie was ever picked to attack")
        self.assertTrue(bombed, "an attacking baddie never dropped a bomb")

    # -- laser: fire, Moving/DespawnBeyond, and the hand-written hit check

    def test_laser_moves_via_behaviors_and_despawns_past_the_far_bound(self):
        scene = load_app("vs2_examples.vyruss_vs2")
        laser = scene.laser.spawn(100, 0, frame=0)

        self.step_buttons(0)
        self.assertEqual(laser.y, 6)  # Moving(speed_y=6)
        self.step_buttons(0)
        self.assertEqual(laser.y, 12)

        ticks = 0
        while len(scene.laser) and ticks < 60:
            self.step_buttons(0)
            ticks += 1
        # DespawnBeyond(y_max=164): retired once it crosses the bound.
        self.assertEqual(len(scene.laser), 0)

    def test_fire_refuses_a_second_shot_while_one_is_live(self):
        scene = load_app("vs2_examples.vyruss_vs2")
        scene.fire()
        self.assertEqual(len(scene.laser), 1)
        scene.fire()
        self.assertEqual(len(scene.laser), 1)

    def test_laser_hits_baddie_and_spawns_an_explosion_with_score(self):
        from games.vs2_examples.vyruss_vs2.code.vyruss_vs2 import ATTACKING

        scene = load_app("vs2_examples.vyruss_vs2")
        scene.state = ATTACKING
        baddie = scene.baddies.spawn(
            scene.player.x + 6, scene.player.y + 11, frame=0)
        baddie.base_frame = 0
        baddie.frame_clock = 0
        baddie.dead = False
        baddie.finished = True
        baddie.movements = []
        scene.everyone = [baddie]

        self.assertEqual(len(scene.explosions), 0)
        scene.fire()
        self.assertEqual(len(scene.laser), 1)

        self.step_buttons(0)

        self.assertEqual(len(scene.laser), 0)
        self.assertEqual(len(scene.everyone), 0)
        self.assertEqual(len(scene.explosions), 1)
        self.assertGreaterEqual(scene.score, 10)

    def test_explosion_transient_lifecycle_end_to_end(self):
        from games.vs2_examples.vyruss_vs2.code.vyruss_vs2 import ATTACKING

        scene = load_app("vs2_examples.vyruss_vs2")
        scene.state = ATTACKING
        baddie = scene.baddies.spawn(
            scene.player.x + 6, scene.player.y + 11, frame=0)
        baddie.base_frame = 0
        baddie.frame_clock = 0
        baddie.dead = False
        baddie.finished = True
        baddie.movements = []
        scene.everyone = [baddie]

        scene.fire()
        self.step_buttons(0)  # the hit: spawns the explosion, elapsed -> 1
        self.assertEqual(len(scene.explosions), 1)

        # Transient(animate=True, ticks=5): still alive through the next
        # 3 ticks (elapsed 2..4), gone the tick elapsed reaches 5.
        for _ in range(3):
            self.step_buttons(0)
        self.assertEqual(len(scene.explosions), 1)

        self.step_buttons(0)  # elapsed reaches 5 -- expires
        self.assertEqual(len(scene.explosions), 0)

    # -- bombs: Moving/DespawnBeyond, and the player-collision hit check

    def test_bomb_moves_via_behaviors_and_despawns_past_the_rim(self):
        scene = load_app("vs2_examples.vyruss_vs2")
        # Spawn well away from the player's own angle so update_player_
        # collision() cannot hit it first -- isolating DespawnBeyond.
        bomb = scene.bombs.spawn(128, 50, frame=1)

        self.step_buttons(0)
        self.assertEqual(bomb.y, 47)  # Moving(speed_y=-3)

        ticks = 0
        while len(scene.bombs) and ticks < 60:
            self.step_buttons(0)
            ticks += 1
        self.assertEqual(len(scene.bombs), 0)
        self.assertFalse(scene.player_exploded)

    def test_bomb_hits_player_and_explodes_it(self):
        scene = load_app("vs2_examples.vyruss_vs2")
        scene.bombs.spawn(scene.player.x, scene.player.y, frame=1)
        self.assertFalse(scene.player_exploded)
        lives_before = scene.lives

        self.step_buttons(0)

        self.assertEqual(len(scene.bombs), 0)
        self.assertTrue(scene.player_exploded)
        self.assertEqual(scene.lives, lives_before - 1)
        self.assertTrue(scene.player_explosion.visible)

    # -- level progression -------------------------------------------------

    def test_finish_level_advances_to_the_next_level_and_resets_state(self):
        scene = load_app("vs2_examples.vyruss_vs2")
        self.assertEqual(scene.level, 0)
        self.assertEqual(scene.waves, 2)

        scene.finish_level()

        self.assertEqual(scene.level, 1)
        self.assertEqual(scene.waves, 3)  # LEVELS[1]
        self.assertEqual(scene.state, 0)  # ENTERING, via start_level()
        self.assertEqual(len(scene.everyone), 0)

    def test_finishing_the_last_level_pops_the_scene(self):
        from games.vs2_examples.vyruss_vs2.code.vyruss_vs2 import LEVELS

        scene = load_app("vs2_examples.vyruss_vs2")
        popped = []
        scene.pop = lambda: popped.append(True)
        scene.level = len(LEVELS) - 1

        scene.finish_level()

        self.assertEqual(popped, [True])

    def test_defeated_planet_animates_toward_the_rim(self):
        scene = load_app("vs2_examples.vyruss_vs2")
        scene.start_defeated()

        self.assertEqual(scene.planet.y, 255)
        positions = []
        for _ in range(4):
            self.step_buttons(0)
            positions.append(scene.planet.y)
        self.assertEqual(positions, [254, 253, 252, 251])

    # -- player death / respawn / game over --------------------------------

    def test_player_death_and_respawn_restores_control(self):
        scene = load_app("vs2_examples.vyruss_vs2")
        scene.lives = 3

        scene.explode_player()
        self.assertTrue(scene.player_exploded)
        self.assertEqual(scene.lives, 2)
        self.assertTrue(scene.player_explosion.visible)
        self.assertFalse(scene.player.visible)

        scene.respawn_player()
        self.assertFalse(scene.player_exploded)
        self.assertTrue(scene.player.visible)
        self.assertFalse(scene.player_explosion.visible)
        self.assertEqual(scene.player.y, -1)  # RIM_Y

    def test_last_life_lost_shows_game_over(self):
        scene = load_app("vs2_examples.vyruss_vs2")
        scene.lives = 1

        scene.explode_player()

        self.assertEqual(scene.lives, 0)
        self.assertTrue(scene.game_over.visible)

    def test_player_explosion_ages_out_via_hand_written_counter(self):
        # player_explosion stays a hand-written age counter, not a
        # Transient -- see vyruss_vs2.py's own module docstring for why a
        # Behavior on a lone, repeatedly shown/hidden sprite is the wrong
        # shape here. explosion_nave.png has 4 frames.
        scene = load_app("vs2_examples.vyruss_vs2")
        scene.explode_player()
        self.assertTrue(scene.player_explosion.visible)

        for expected_frame in (1, 2, 3):
            self.step_buttons(0)
            self.assertTrue(scene.player_explosion.visible)
            self.assertEqual(scene.player_explosion.frame, expected_frame)

        self.step_buttons(0)
        self.assertFalse(scene.player_explosion.visible)


if __name__ == "__main__":
    unittest.main()
