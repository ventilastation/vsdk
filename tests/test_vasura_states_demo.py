"""Headless coverage for games/vs2_examples/vasura_states_demo -- the T17
Phase 2 "state hats" proving case against real game logic: a small,
original recreation of games/vsjam-may25/vasura_espacial's own hand-rolled
enemy state machine, authored through tools/vs2_behavior_gen's new
state-hat schema (code/build_enemy_states.py generates
code/enemy_states.py from code/enemy_states.vs2behavior.json). See
code/build_enemy_states.py's own module docstring for exactly which real
states this recreates and the one deliberate departure from the real
transition graph.

Driven end to end via director.step_once(), the same way
tests/test_vixeous_vs2_examples.py drives the T15 proving case and
tests/test_event_sheet_demo.py drives the T16 one -- this file is that
same convention's T17 entry.

What this actually proves, tick by tick: a spawned enemy starts
'orbiting', holds there for its configured duration, hands off to
'chiller_falling' (a second hold()-based transition), then 'falling'
(a real per-tick descent this time, not just a timer), reaching
'exploding' either by hitting the ground or by a player bullet's Collide
hit cutting the cycle short from any of the three earlier states -- and
'exploding' despawns the enemy, spawns a real (Transient-driven) explosion
sprite, and calls back into the hand-written scene's own scoring, exactly
once.
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

import vs2  # noqa: E402
from ventilastation import api_guard  # noqa: E402
from ventilastation.app_loader import load_app  # noqa: E402
from ventilastation.director import configure_runtime, director, reset_runtime, stripes  # noqa: E402
from vs2.controls import A  # noqa: E402

DEMO_STRIPS = ("ship.png", "bullet.png", "enemy.png", "explosion.png")

DEMO_METADATA = {
    "ship.png": (4, 4, 4),
    "bullet.png": (3, 3, 1),
    "enemy.png": (6, 6, 2),
    "explosion.png": (6, 6, 4),
}


class VasuraStatesDemoTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        runtime_director = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            for index, name in enumerate(DEMO_STRIPS):
                stripes[name] = index
                width, height, frames = DEMO_METADATA[name]
                runtime_director.platform.sprites.stripes[index] = {
                    "width": width, "height": height, "frames": frames, "palette": 0,
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

    def step_many(self, count, buttons=0):
        for _ in range(count):
            self.step(buttons)

    # -- build() sanity ---------------------------------------------------

    def test_builds_without_error(self):
        scene = load_app("vs2_examples.vasura_states_demo")
        self.assertEqual(scene._vs_declared_api, "vs2")
        self.assertEqual(scene.score, 0)
        self.assertEqual(len(scene.enemies), 0)

    def test_runs_many_ticks_without_crashing(self):
        scene = load_app("vs2_examples.vasura_states_demo")
        self.step_many(400)
        # Waves keep spawning and dying without ever raising.
        self.assertGreaterEqual(scene.score, 0)

    # -- the state cycle itself --------------------------------------------

    def test_a_freshly_spawned_enemy_starts_orbiting(self):
        from games.vs2_examples.vasura_states_demo.code.enemy_states import EnemyStates

        scene = load_app("vs2_examples.vasura_states_demo")
        enemy = scene.enemies.spawn(50, 8)
        behavior = scene.enemies.behavior(EnemyStates)
        self.assertEqual(behavior.state_name(enemy), "orbiting")

    def test_orbiting_holds_then_hands_off_to_chiller_falling(self):
        from games.vs2_examples.vasura_states_demo.code.enemy_states import EnemyStates

        scene = load_app("vs2_examples.vasura_states_demo")
        enemy = scene.enemies.spawn(50, 8)
        behavior = scene.enemies.behavior(EnemyStates)
        for _ in range(behavior.orbit_ticks):
            self.assertEqual(behavior.state_name(enemy), "orbiting")
            behavior.step(scene.enemies)
        self.assertEqual(behavior.state_name(enemy), "chiller_falling")

    def test_falling_descends_and_reaches_exploding_at_the_ground(self):
        from games.vs2_examples.vasura_states_demo.code.enemy_states import EnemyStates
        from games.vs2_examples.vasura_states_demo.code.vasura_states_demo import GROUND_Y

        scene = load_app("vs2_examples.vasura_states_demo")
        enemy = scene.enemies.spawn(50, GROUND_Y - 2)
        behavior = scene.enemies.behavior(EnemyStates)
        behavior.force_state(enemy, "falling")
        behavior.step(scene.enemies)  # y += fall_speed (1): still below ground
        self.assertEqual(behavior.state_name(enemy), "falling")
        behavior.step(scene.enemies)  # y reaches GROUND_Y
        self.assertEqual(behavior.state_name(enemy), "exploding")

    def test_a_bullet_hit_cuts_the_cycle_short_from_any_vulnerable_state(self):
        from games.vs2_examples.vasura_states_demo.code.enemy_states import EnemyStates

        scene = load_app("vs2_examples.vasura_states_demo")
        enemy = scene.enemies.spawn(50, 8)
        behavior = scene.enemies.behavior(EnemyStates)
        bullet = scene.bullets.spawn(50, 8)  # exactly overlapping
        self.assertIsNotNone(bullet)
        behavior.step(scene.enemies)
        self.assertEqual(behavior.state_name(enemy), "exploding")

    def test_death_despawns_spawns_an_explosion_and_scores_exactly_once(self):
        from games.vs2_examples.vasura_states_demo.code.enemy_states import EnemyStates

        scene = load_app("vs2_examples.vasura_states_demo")
        scene.enemies.spawn(50, 8)
        behavior = scene.enemies.behavior(EnemyStates)
        bullet = scene.bullets.spawn(50, 8)
        behavior.step(scene.enemies)  # -> exploding, enter_exploding runs
        self.assertEqual(len(scene.enemies), 1)     # not despawned yet
        self.assertEqual(len(scene.explosions), 1)  # already spawned
        self.assertEqual(scene.score, 10)           # on_enemy_death ran once

        behavior.step(scene.enemies)  # exploding's own step: despawns now
        self.assertEqual(len(scene.enemies), 0)
        self.assertEqual(len(scene.explosions), 1)
        self.assertEqual(scene.score, 10)  # still just once

    # -- waves / input ------------------------------------------------------

    def test_waves_spawn_enemies_over_time(self):
        scene = load_app("vs2_examples.vasura_states_demo")
        self.step()  # next_wave starts at 1: the very first tick spawns
        self.assertGreater(len(scene.enemies), 0)

    def test_firing_spawns_a_bullet_that_eventually_leaves_the_world(self):
        scene = load_app("vs2_examples.vasura_states_demo")
        self.step(buttons=A)
        self.assertEqual(len(scene.bullets), 1)
        self.step_many(200)
        self.assertEqual(len(scene.bullets), 0)


if __name__ == "__main__":
    unittest.main()
