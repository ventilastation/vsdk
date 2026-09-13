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


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("vs2 behavior gen (micropython): %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
