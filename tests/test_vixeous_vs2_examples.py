"""Headless coverage for games/vs2_examples/vixeous -- the T15 "scene
editor / build() generator" proving case: a port of
games/alecu/vixeous/code/vixeous.py whose build() is generated from
games/vs2_examples/vixeous/code/vixeous_scene.vs2model.json by
tools/vs2_scene_gen, with the tick-by-tick game logic (input, collision,
scoring, terrain scroll, the boss fight) hand-written in the companion
games/vs2_examples/vixeous/code/vixeous.py, exactly like the original.

This does not re-run games/alecu/vixeous's own test suite (that game is
untouched -- see tests/test_vixeous_vs2.py); it exercises the port's own
module (a different slug, "vs2_examples.vixeous") and, in particular, the
seams the generator/behavior-catalog port actually introduced: enemy
Moving/DespawnBeyond, shot/bomb Moving, and the explosions pool's
Transient(animate=True, ticks=18) lifecycle end to end.
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


class VixeousVs2ExamplesTests(unittest.TestCase):
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

    # -- build() sanity -------------------------------------------------

    def test_builds_from_the_generated_scene_without_error(self):
        scene = load_app("vs2_examples.vixeous")

        self.assertEqual(scene._vs_declared_api, "vs2")
        self.assertEqual(scene.world.projection.__class__, scene.hud.projection.__class__)
        self.assertIs(scene.world._drawables[0], scene.terrain)
        self.assertGreater(
            scene.world._drawables.index(scene.player),
            scene.world._drawables.index(scene.terrain))
        self.assertIs(scene.message.layer, scene.hud)
        self.assertTrue(scene.message.visible)
        self.assertEqual(scene.player.y, 6)
        self.assertEqual(scene.state, 0)  # STATE_READY

    def test_runs_many_ticks_without_crashing(self):
        scene = load_app("vs2_examples.vixeous")
        from games.vs2_examples.vixeous.code.vixeous import STATE_PLAYING

        scene.state = STATE_PLAYING
        scene.message.hide()
        for _ in range(120):
            self.step_buttons(0)
        # The terrain keeps scrolling and the scene never raised.
        self.assertGreater(scene.depth, 0)

    # -- enemy spawn / movement / despawn --------------------------------

    def test_enemy_spawns_moves_and_despawns_via_behaviors(self):
        scene = load_app("vs2_examples.vixeous")
        from games.vs2_examples.vixeous.code.vixeous import (
            ENEMY_START_Y, STATE_PLAYING,
        )

        scene.state = STATE_PLAYING
        scene.message.hide()

        scene.spawn_wave()
        self.assertGreater(len(scene.enemies), 0)
        enemy = next(iter(scene.enemies))
        self.assertEqual(enemy.y, ENEMY_START_Y)

        # Isolate one enemy far from the player's angle so check_player_hits
        # cannot despawn it first, and force it close to the DespawnBeyond
        # bound (y_min=0) so it despawns from Moving+DespawnBeyond alone.
        for other in list(scene.enemies):
            scene.enemies.despawn(other)
        enemy = scene.enemies.spawn(0, 2, frame=0)
        enemy.theta = 128
        enemy.kind = 0
        enemy.hp = 1

        self.step_buttons(0)
        self.assertEqual(len(scene.enemies), 1)
        self.assertEqual(next(iter(scene.enemies)).y, 1)  # Moving(speed_y=-1)

        self.step_buttons(0)
        self.assertEqual(len(scene.enemies), 1)
        self.assertEqual(next(iter(scene.enemies)).y, 0)

        # DespawnBeyond(y_min=0) checks the position at the *start* of the
        # tick, before that same tick's Moving commit lands (dispatch runs
        # scene-wide, then the dx/dy commit runs once, after -- see
        # Scene._run_behaviors) -- so a sprite despawns one tick after it
        # actually crosses the bound, not the tick it crosses on.
        self.step_buttons(0)
        self.assertEqual(len(scene.enemies), 1)
        self.assertEqual(next(iter(scene.enemies)).y, -1)

        self.step_buttons(0)
        self.assertEqual(len(scene.enemies), 0)

    # -- shot fire + hit --------------------------------------------------

    def test_shot_hits_enemy_and_spawns_an_explosion(self):
        scene = load_app("vs2_examples.vixeous")
        from games.vs2_examples.vixeous.code.vixeous import STATE_PLAYING

        scene.state = STATE_PLAYING
        scene.message.hide()

        shot = scene.shots.spawn(0, 50, frame=0)
        shot.theta = 100
        enemy = scene.enemies.spawn(0, 50, frame=0)
        enemy.theta = 100
        enemy.kind = 0
        enemy.hp = 1

        self.assertEqual(len(scene.explosions), 0)
        self.step_buttons(0)

        self.assertEqual(len(scene.shots), 0)
        self.assertEqual(len(scene.enemies), 0)
        self.assertEqual(len(scene.explosions), 1)
        self.assertEqual(scene.score, 40)

    def test_boss_activates_and_orbits_via_the_attached_behavior(self):
        """maybe_start_boss()'s own gate (score>=120, depth>900) is
        expensive to reach through real gameplay ticks -- set it directly,
        matching this file's own established pattern of poking scene
        state rather than simulating minutes of play. Exercises the real
        live wiring (the scene model's declarative attach,
        update_entities()'s remaining hand-written x/frame
        reprojection), not just BossOrbit in
        isolation (see tests/test_vixeous_boss_orbit.py for that)."""
        scene = load_app("vs2_examples.vixeous")
        from games.vs2_examples.vixeous.code.boss_orbit import BossOrbit
        from games.vs2_examples.vixeous.code.vixeous import STATE_PLAYING, screen_x

        scene.state = STATE_PLAYING
        scene.message.hide()

        # BossOrbit ticks from build() onward, even while hidden (see
        # vixeous_scene.vs2model.json's boss.behaviors entry) -- confirm
        # that alone doesn't crash or do anything visible before
        # activation.
        for _ in range(5):
            self.step_buttons(0)
        self.assertFalse(scene.boss.visible)

        scene.score = 120
        scene.depth = 901
        scene.maybe_start_boss()
        self.assertTrue(scene.boss.visible)
        self.assertTrue(scene.boss_started)

        # BossOrbit itself, attached (not just importable).
        self.assertIsNotNone(scene.boss.behavior(BossOrbit))
        thetas = []
        xs = []
        for _ in range(10):
            self.step_buttons(0)
            thetas.append(scene.boss.theta)
            xs.append(scene.boss.x)
        # BossOrbit is really driving theta (not stuck), and
        # update_entities()'s own hand-written reprojection is really
        # reading it back out into a moving x -- one tick behind theta
        # itself (scene_step() runs update() before _run_behaviors(), the
        # same lag this game's own docstring already documents for
        # shots/bombs/enemies), so compared shifted by one, not lockstep.
        self.assertGreater(len(set(thetas)), 1)
        self.assertGreater(len(set(xs)), 1)
        self.assertEqual(
            xs[-1], screen_x(thetas[-2], scene.camera_theta, scene.boss.width))

    def test_explosion_transient_lifecycle_end_to_end(self):
        scene = load_app("vs2_examples.vixeous")
        from games.vs2_examples.vixeous.code.vixeous import STATE_PLAYING

        scene.state = STATE_PLAYING
        scene.message.hide()

        shot = scene.shots.spawn(0, 50, frame=0)
        shot.theta = 100
        enemy = scene.enemies.spawn(0, 50, frame=0)
        enemy.theta = 100
        enemy.kind = 0
        enemy.hp = 1

        self.step_buttons(0)  # tick 1: the hit -- spawns the explosion,
        self.assertEqual(len(scene.explosions), 1)  # Transient elapsed -> 1

        # Transient(animate=True, ticks=18): still alive through tick 17
        # (elapsed 2..17), gone once elapsed reaches 18.
        for _ in range(16):
            self.step_buttons(0)
        self.assertEqual(len(scene.explosions), 1)

        self.step_buttons(0)  # tick 18: elapsed reaches 18 -- expires
        self.assertEqual(len(scene.explosions), 0)

    # -- bomb + target interaction ---------------------------------------

    def test_bomb_hits_target_and_scores(self):
        scene = load_app("vs2_examples.vixeous")
        from games.vs2_examples.vixeous.code.vixeous import STATE_PLAYING

        scene.state = STATE_PLAYING
        scene.message.hide()

        aim_y = scene.aim_y()
        bomb = scene.bombs.spawn(0, aim_y, frame=1)
        bomb.theta = 100
        target = scene.targets.spawn(0, aim_y, frame=0)
        target.theta = 100
        target.kind = 0

        self.step_buttons(0)

        self.assertEqual(len(scene.bombs), 0)
        self.assertEqual(len(scene.targets), 0)
        # target_burst() spawns three explosions: the main burst plus two
        # offset satellites.
        self.assertEqual(len(scene.explosions), 3)
        self.assertEqual(scene.score, 70)

    def test_bomb_miss_still_bursts(self):
        scene = load_app("vs2_examples.vixeous")
        from games.vs2_examples.vixeous.code.vixeous import STATE_PLAYING

        scene.state = STATE_PLAYING
        scene.message.hide()

        aim_y = scene.aim_y()
        bomb = scene.bombs.spawn(0, aim_y, frame=1)
        bomb.theta = 100  # nothing at this theta

        self.step_buttons(0)

        self.assertEqual(len(scene.bombs), 0)
        self.assertEqual(scene.score, 0)
        self.assertEqual(len(scene.explosions), 1)


if __name__ == "__main__":
    unittest.main()
