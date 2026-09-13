"""Runs the generated Projectile behavior for real on the MicroPython unix
port -- the risk surface tests/test_vs2_behavior_gen_generator.py's
GeneratedProjectileBehaviorTests cannot cover, since that file imports
unittest/tempfile/importlib.util, none of which exist on MicroPython (the
CPython-shim gap this whole effort has hit before -- see
docs/vs2-behaviors-handoff.md's gotchas on why a CPython-only test suite
can look green while the generated code is actually broken on-device).

The fixture (tests/fixtures/generated_projectile_fixture.py) is not
generated at test time -- tools/vs2_behavior_gen's own generator module
uses CPython-only conveniences not guaranteed on MicroPython, so this test
deliberately doesn't depend on it importing cleanly here. Instead the
fixture is a checked-in copy of one real generator run's output;
tests/test_vs2_behavior_gen_generator.py's
test_fixture_matches_current_generator_output (CPython side) guards
against it silently drifting out of sync with the generator.

Run: ``micropython tests/test_vs2_behavior_gen_micropython.py``
"""

import sys

sys.path.insert(0, "apps/micropython")
sys.path.insert(0, "tests/fixtures")

from ventilastation import api_guard
from ventilastation.director import configure_runtime, director, reset_runtime, stripes
import vs2

from generated_projectile_fixture import GeneratedProjectile
from generated_enemy_fixture import GeneratedEnemy
from generated_damageable_fixture import GeneratedDamageable


def _fresh_game(build_fn):
    reset_runtime()
    api_guard.reset()
    configure_runtime("headless")
    stripes.clear()
    stripes["ship.png"] = 0
    director.platform.sprites.stripes[0] = {
        "width": 4, "height": 4, "frames": 4, "palette": 0,
    }
    api_guard.begin_app("games.test_vs2_behavior_gen", "vs2")

    class Game(vs2.Scene):
        idle_timeout = None
        back_button = False

        def build(self):
            build_fn(self)

        def update(self):
            pass

    game = Game()
    director.push(game)
    return game


def test_moves_via_the_hoisted_move_action():
    def build(scene):
        scene.world = scene.layer("world", projection=vs2.TUNNEL)
        scene.shots = scene.world.sprite_pool("ship.png", count=2)
        scene.targets = scene.world.sprite_pool("ship.png", count=1)
        scene.shots.behave(GeneratedProjectile(
            speed_x=1, speed_y=2, range=200, hits=scene.targets))
        scene.shots.spawn(10, 10)

    game = _fresh_game(build)
    behavior = game.shots.behavior(GeneratedProjectile)
    behavior.step(game.shots)
    sprite = game.shots._live[0]
    assert sprite.dx == 1, sprite.dx
    assert sprite.dy == 2, sprite.dy
    assert sprite.shot_flown == 2, sprite.shot_flown


def test_despawns_past_its_range():
    def build(scene):
        scene.world = scene.layer("world", projection=vs2.TUNNEL)
        scene.shots = scene.world.sprite_pool("ship.png", count=1)
        scene.targets = scene.world.sprite_pool("ship.png", count=1)
        scene.shots.behave(GeneratedProjectile(
            speed_x=0, speed_y=10, range=25, hits=scene.targets))
        scene.shots.spawn(0, 0)

    game = _fresh_game(build)
    behavior = game.shots.behavior(GeneratedProjectile)
    for _ in range(3):
        behavior.step(game.shots)
    assert len(game.shots) == 0, len(game.shots)


def test_despawns_both_sprites_on_a_hit():
    def build(scene):
        scene.world = scene.layer("world", projection=vs2.TUNNEL)
        scene.shots = scene.world.sprite_pool("ship.png", count=1)
        scene.targets = scene.world.sprite_pool("ship.png", count=1)
        scene.shots.behave(GeneratedProjectile(
            speed_x=0, speed_y=0, range=200, hits=scene.targets))
        scene.shots.spawn(10, 10)
        scene.targets.spawn(10, 10)  # exactly overlapping

    game = _fresh_game(build)
    behavior = game.shots.behavior(GeneratedProjectile)
    behavior.step(game.shots)
    assert len(game.shots) == 0, len(game.shots)
    assert len(game.targets) == 0, len(game.targets)


def test_generated_projectile_over_100_sprites_allocates_nothing():
    """The acceptance bar every hand-written catalog entry meets -- this is
    the one check that specifically needs real MicroPython (gc.mem_free()
    doesn't exist on CPython), which is the whole reason this file exists
    alongside the CPython-side behavioral tests."""
    import gc

    def build(scene):
        scene.world = scene.layer("world", projection=vs2.TUNNEL)
        scene.shots = scene.world.sprite_pool("ship.png", count=99)
        scene.targets = scene.world.sprite_pool("ship.png", count=1)
        scene.shots.behave(GeneratedProjectile(
            speed_x=0, speed_y=0, range=255, hits=scene.targets))
        for index in range(99):
            scene.shots.spawn(index, 0)

    game = _fresh_game(build)
    behavior = game.shots.behavior(GeneratedProjectile)
    for _ in range(10):
        behavior.step(game.shots)
    gc.collect()
    before = gc.mem_free()
    for _ in range(1000):
        behavior.step(game.shots)
    gc.collect()
    after = gc.mem_free()
    assert after >= before - 64, "before=%d after=%d" % (before, after)


# ---------------------------------------------------------------------------
# Phase 2: the state-hat-generated GeneratedEnemy (tests/fixtures/
# generated_enemy_fixture.py), the same real-MicroPython risk surface as
# GeneratedProjectile above -- a StateMachine subclass this time, so this
# also covers the base class's own step()/hold()/_dispatch_one() dispatch
# running for real, not just the flat two-zone skeleton.
# ---------------------------------------------------------------------------

def _build_enemy_game(on_death=None):
    def build(scene):
        scene.world = scene.layer("world", projection=vs2.TUNNEL)
        scene.enemies = scene.world.sprite_pool("ship.png", count=1)
        scene.targets = scene.world.sprite_pool("ship.png", count=1)
        scene.explosions = scene.world.sprite_pool("ship.png", count=1)
        scene.enemies.behave(GeneratedEnemy(
            ground_y=50, explosion=scene.explosions, hits=scene.targets,
            on_death=on_death))

    return _fresh_game(build)


def test_starts_in_the_declared_initial_state():
    game = _build_enemy_game()
    game.enemies.spawn(10, 10)
    behavior = game.enemies.behavior(GeneratedEnemy)
    sprite = game.enemies._live[0]
    assert behavior.state_name(sprite) == "orbiting", behavior.state_name(sprite)


def test_hold_transitions_to_falling_after_its_configured_ticks():
    game = _build_enemy_game()
    game.enemies.spawn(10, 10)
    game.targets.spawn(200, 200)  # far away: never hit
    behavior = game.enemies.behavior(GeneratedEnemy)
    sprite = game.enemies._live[0]
    for _ in range(3):
        assert behavior.state_name(sprite) == "orbiting", behavior.state_name(sprite)
        behavior.step(game.enemies)
    assert behavior.state_name(sprite) == "falling", behavior.state_name(sprite)


def test_collide_short_circuits_the_hold_into_exploding():
    game = _build_enemy_game()
    game.enemies.spawn(10, 10)
    game.targets.spawn(10, 10)  # exactly overlapping: hit on tick 1
    behavior = game.enemies.behavior(GeneratedEnemy)
    sprite = game.enemies._live[0]
    behavior.step(game.enemies)
    assert behavior.state_name(sprite) == "exploding", behavior.state_name(sprite)


def test_exploding_enter_hook_spawns_and_calls_back_once_then_despawns_next_tick():
    calls = []
    game = _build_enemy_game(on_death=lambda sprite: calls.append(sprite))
    game.enemies.spawn(10, 10)
    game.targets.spawn(200, 200)
    behavior = game.enemies.behavior(GeneratedEnemy)
    sprite = game.enemies._live[0]
    for _ in range(3):
        behavior.step(game.enemies)
    sprite.y = 60  # past ground_y=50
    behavior.step(game.enemies)  # falling -> exploding: enter_exploding runs
    assert behavior.state_name(sprite) == "exploding"
    assert len(game.enemies) == 1, len(game.enemies)      # not despawned yet
    assert len(game.explosions) == 1, len(game.explosions)  # already spawned
    assert len(calls) == 1, len(calls)                    # called back once

    behavior.step(game.enemies)                            # exploding's own step
    assert len(game.enemies) == 0, len(game.enemies)        # despawned now
    assert len(calls) == 1, len(calls)                      # still just once


def test_generated_state_machine_over_100_sprites_allocates_nothing():
    """The same acceptance bar test_generated_projectile_over_100_sprites_
    allocates_nothing sets for Projectile, applied to the StateMachine-
    shaped generated class -- proving the inherited despawn-safe step()
    loop plus this class's own per-state methods cost nothing extra per
    tick once warmed up."""
    import gc

    def build(scene):
        scene.world = scene.layer("world", projection=vs2.TUNNEL)
        # 98 + 1 + 1 = 100: the same per-layer sprite budget
        # test_generated_projectile_over_100_sprites_allocates_nothing
        # above is already right up against.
        scene.enemies = scene.world.sprite_pool("ship.png", count=98)
        scene.targets = scene.world.sprite_pool("ship.png", count=1)
        scene.explosions = scene.world.sprite_pool("ship.png", count=1)
        scene.enemies.behave(GeneratedEnemy(
            ground_y=999, explosion=scene.explosions, hits=scene.targets))
        for index in range(98):
            scene.enemies.spawn(index, 0)

    game = _fresh_game(build)
    game.targets.spawn(250, 250)  # far away: Collide never hits
    behavior = game.enemies.behavior(GeneratedEnemy)
    for _ in range(10):
        behavior.step(game.enemies)
    gc.collect()
    before = gc.mem_free()
    for _ in range(1000):
        behavior.step(game.enemies)
    gc.collect()
    after = gc.mem_free()
    assert after >= before - 64, "before=%d after=%d" % (before, after)


# ---------------------------------------------------------------------------
# Phase 2: the plain-Behavior-shaped Damageable (tests/fixtures/
# generated_damageable_fixture.py) -- the same real-MicroPython risk
# surface again, this time for the four new node kinds usable outside a
# state hat (set_state/call_callback/spawn/play_sound) plus the mutually-
# exclusive if/else invulnerability design (see this task's report for why
# two independent top-level nodes were wrong).
# ---------------------------------------------------------------------------

def _build_damageable_game(**behavior_kwargs):
    deaths = []

    def build(scene):
        scene.world = scene.layer("world", projection=vs2.TUNNEL)
        scene.enemies = scene.world.sprite_pool("ship.png", count=1)
        scene.bullets = scene.world.sprite_pool("ship.png", count=3)
        scene.explosions = scene.world.sprite_pool("ship.png", count=1)
        scene.enemies.behave(GeneratedDamageable(
            hits=scene.bullets, explosion=scene.explosions,
            on_death=lambda sprite, points: deaths.append(points),
            **behavior_kwargs))

    game = _fresh_game(build)
    game.deaths = deaths
    return game


def test_hp_decreases_on_a_hit():
    game = _build_damageable_game(hp=5, invulnerable_ticks=0)
    enemy = game.enemies.spawn(10, 10)
    game.bullets.spawn(10, 10)
    behavior = game.enemies.behavior(GeneratedDamageable)
    behavior.step(game.enemies)
    assert enemy.damage_taken == 1, enemy.damage_taken
    assert len(game.enemies) == 1, len(game.enemies)


def test_not_hit_again_during_its_invulnerability_window():
    game = _build_damageable_game(hp=99, invulnerable_ticks=3)
    enemy = game.enemies.spawn(10, 10)
    game.bullets.spawn(10, 10)  # stays overlapping the whole time
    behavior = game.enemies.behavior(GeneratedDamageable)
    behavior.step(game.enemies)
    assert enemy.damage_taken == 1, enemy.damage_taken
    for _ in range(3):
        behavior.step(game.enemies)
        assert enemy.damage_taken == 1, "hit again while invulnerable: %d" % enemy.damage_taken


def test_blink_hides_then_restores_visibility():
    game = _build_damageable_game(hp=99, invulnerable_ticks=2, blink=True)
    enemy = game.enemies.spawn(10, 10)
    game.bullets.spawn(10, 10)
    behavior = game.enemies.behavior(GeneratedDamageable)
    assert enemy.visible
    behavior.step(game.enemies)  # hit: hides
    assert not enemy.visible
    behavior.step(game.enemies)  # invuln_left 2 -> 1: still hidden
    assert not enemy.visible
    behavior.step(game.enemies)  # invuln_left 1 -> 0: restored
    assert enemy.visible


def test_dies_exactly_once_despawn_explosion_score_and_on_death():
    game = _build_damageable_game(hp=1, invulnerable_ticks=0, score=40)
    game.enemies.spawn(10, 10)
    game.bullets.spawn(10, 10)
    behavior = game.enemies.behavior(GeneratedDamageable)
    behavior.step(game.enemies)
    assert len(game.enemies) == 0, len(game.enemies)
    assert len(game.explosions) == 1, len(game.explosions)
    assert game.deaths == [40], game.deaths
    behavior.step(game.enemies)  # empty pool: must not re-trigger anything
    assert len(game.explosions) == 1, len(game.explosions)
    assert game.deaths == [40], game.deaths


def test_generated_damageable_over_100_sprites_allocates_nothing():
    import gc

    def build(scene):
        scene.world = scene.layer("world", projection=vs2.TUNNEL)
        scene.enemies = scene.world.sprite_pool("ship.png", count=98)
        scene.bullets = scene.world.sprite_pool("ship.png", count=1)
        scene.explosions = scene.world.sprite_pool("ship.png", count=1)
        scene.enemies.behave(GeneratedDamageable(
            hp=99, invulnerable_ticks=5, hits=scene.bullets, explosion=scene.explosions))
        for index in range(98):
            scene.enemies.spawn(index, 0)

    game = _fresh_game(build)
    game.bullets.spawn(250, 250)  # far away: Collide never hits
    behavior = game.enemies.behavior(GeneratedDamageable)
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
    print("vs2 behavior gen (micropython): %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
