"""Runs games/vs2_examples/vasura_states_demo's own generated EnemyStates
for real on the MicroPython unix port -- the same real-device risk surface
tests/test_vs2_behavior_gen_micropython.py exists for (see that file's own
docstring), applied to this task's actual proving-game output rather than
a synthetic test fixture: this imports the real, checked-in
code/enemy_states.py directly, not a copy.

Run: ``micropython tests/test_vasura_states_demo_micropython.py``
"""

import sys

sys.path.insert(0, "apps/micropython")
sys.path.insert(0, ".")

from ventilastation import api_guard
from ventilastation.director import configure_runtime, director, reset_runtime, stripes
import vs2

from games.vs2_examples.vasura_states_demo.code.enemy_states import EnemyStates


def _fresh_game(behavior_kwargs):
    reset_runtime()
    api_guard.reset()
    configure_runtime("headless")
    stripes.clear()
    stripes["enemy.png"] = 0
    stripes["bullet.png"] = 1
    stripes["explosion.png"] = 2
    director.platform.sprites.stripes[0] = {
        "width": 6, "height": 6, "frames": 2, "palette": 0,
    }
    director.platform.sprites.stripes[1] = {
        "width": 3, "height": 3, "frames": 1, "palette": 0,
    }
    director.platform.sprites.stripes[2] = {
        "width": 6, "height": 6, "frames": 4, "palette": 0,
    }
    api_guard.begin_app("games.test_vasura_states_demo", "vs2")

    class Game(vs2.Scene):
        idle_timeout = None
        back_button = False

        def build(self):
            self.world = self.layer("world", projection=vs2.TUNNEL)
            self.enemies = self.world.sprite_pool("enemy.png", count=4)
            self.bullets = self.world.sprite_pool("bullet.png", count=2)
            self.explosions = self.world.sprite_pool("explosion.png", count=2)
            self.enemies.behave(EnemyStates(
                hits=self.bullets, explosion=self.explosions, **behavior_kwargs))

        def update(self):
            pass

    game = Game()
    director.push(game)
    return game


def test_a_freshly_spawned_enemy_starts_orbiting():
    game = _fresh_game(dict(orbit_ticks=5, chiller_ticks=3, ground_y=50))
    enemy = game.enemies.spawn(10, 10)
    behavior = game.enemies.behavior(EnemyStates)
    assert behavior.state_name(enemy) == "orbiting", behavior.state_name(enemy)


def test_the_full_cycle_orbiting_chiller_falling_falling_exploding():
    game = _fresh_game(dict(orbit_ticks=3, chiller_ticks=2, fall_speed=8, ground_y=30))
    enemy = game.enemies.spawn(10, 5)
    behavior = game.enemies.behavior(EnemyStates)

    for _ in range(3):
        assert behavior.state_name(enemy) == "orbiting"
        behavior.step(game.enemies)
    assert behavior.state_name(enemy) == "chiller_falling"

    for _ in range(2):
        assert behavior.state_name(enemy) == "chiller_falling"
        behavior.step(game.enemies)
    assert behavior.state_name(enemy) == "falling"

    while behavior.state_name(enemy) == "falling":
        behavior.step(game.enemies)
    assert behavior.state_name(enemy) == "exploding"
    assert len(game.enemies) == 1        # not despawned yet
    assert len(game.explosions) == 1     # already spawned

    behavior.step(game.enemies)          # exploding's own step
    assert len(game.enemies) == 0


def test_a_hit_short_circuits_orbiting_straight_to_exploding():
    game = _fresh_game(dict(orbit_ticks=100, ground_y=250))
    enemy = game.enemies.spawn(10, 10)
    game.bullets.spawn(10, 10)  # exactly overlapping
    behavior = game.enemies.behavior(EnemyStates)
    behavior.step(game.enemies)
    assert behavior.state_name(enemy) == "exploding", behavior.state_name(enemy)


def test_generated_enemy_states_over_many_sprites_allocates_nothing():
    import gc

    game = _fresh_game(dict(orbit_ticks=255, ground_y=255))
    behavior = game.enemies.behavior(EnemyStates)
    for index in range(4):
        game.enemies.spawn(index, 0)
    for _ in range(10):
        behavior.step(game.enemies)
    gc.collect()
    before = gc.mem_free()
    for _ in range(1000):
        behavior.step(game.enemies)
    gc.collect()
    after = gc.mem_free()
    assert after >= before - 64, "before=%d after=%d" % (before, after)


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("vasura states demo (micropython): %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
