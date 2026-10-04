"""T17 Phase 3: real-MicroPython parity between the readable and fast
backends -- the check that actually matters, per this task's own brief:
not "the transform looks right by reading the generator", but "run the
exact same behavioral test suites against both backends' output for the
same models, and confirm identical results", on real MicroPython, the
same bar every other generator claim in this effort has been held to (see
tests/test_vs2_behavior_gen_micropython.py's own docstring on why a
CPython-only suite is not enough).

The CPython-side version of this same check is
tests/test_vs2_behavior_gen_generator.py's own ``FastBackendParityTests``
-- this file exists because that one cannot see MicroPython-only failure
modes (allocation, ``super()``/attribute-lookup differences, ...) any more
than tests/test_vs2_behavior_gen_micropython.py's own existing checks
could for the readable backend alone.

Fixtures (not generated at test time -- see
tests/test_vs2_behavior_gen_micropython.py's own docstring for why):
tests/fixtures/generated_{projectile,enemy,damageable}_fixture.py
(readable, already existed) and this task's own new
tests/fixtures/generated_{projectile,enemy,damageable}_fast_fixture.py
(``backend="fast"``, drift-guarded on the CPython side by
tests/test_vs2_behavior_gen_generator.py's ``test_fast_fixture_matches_
current_generator_output`` in each of its three RoundTripTests-family
classes).

Run: ``micropython tests/test_vs2_behavior_gen_fast_backend_micropython.py``
"""

import sys

sys.path.insert(0, "apps/micropython")
sys.path.insert(0, "tests/fixtures")

from ventilastation import api_guard
from ventilastation.director import configure_runtime, director, reset_runtime, stripes
import vs2

from generated_projectile_fixture import GeneratedProjectile as ProjectileReadable
from generated_projectile_fast_fixture import GeneratedProjectile as ProjectileFast
from generated_enemy_fixture import GeneratedEnemy as EnemyReadable
from generated_enemy_fast_fixture import GeneratedEnemy as EnemyFast
from generated_damageable_fixture import GeneratedDamageable as DamageableReadable
from generated_damageable_fast_fixture import GeneratedDamageable as DamageableFast


def _fresh_runtime():
    reset_runtime()
    api_guard.reset()
    configure_runtime("headless")
    stripes.clear()
    stripes["ship.png"] = 0
    director.platform.sprites.stripes[0] = {
        "width": 4, "height": 4, "frames": 4, "palette": 0,
    }
    api_guard.begin_app("games.test_vs2_behavior_gen", "vs2")


def _snapshot(pool, fields):
    return [
        {field: getattr(sprite, field, "<missing>") for field in fields}
        for sprite in pool._live
    ]


# ---------------------------------------------------------------------------
# Projectile parity
# ---------------------------------------------------------------------------

def _run_projectile(behavior_cls):
    _fresh_runtime()

    class Game(vs2.Scene):
        idle_timeout = None
        back_button = False

        def build(self):
            self.world = self.layer("world", projection=vs2.TUNNEL)
            self.shots = self.world.sprite_pool("ship.png", count=5)
            self.targets = self.world.sprite_pool("ship.png", count=3)
            self.shots.behave(behavior_cls(
                speed_x=1, speed_y=3, range=30, hits=self.targets))

        def update(self):
            pass

    game = Game()
    director.push(game)
    for x, y in ((0, 0), (5, 5), (10, 10), (2, 2), (8, 1)):
        game.shots.spawn(x, y)
    for x, y in ((10, 10), (8, 1), (60, 60)):
        game.targets.spawn(x, y)

    behavior = game.shots.behavior(behavior_cls)
    fields = ("x", "y", "dx", "dy", "shot_flown")
    snapshots = []
    for _ in range(15):
        behavior.step(game.shots)
        snapshots.append(_snapshot(game.shots, fields))
        snapshots.append(len(game.targets))
    return snapshots


def test_projectile_readable_and_fast_produce_identical_snapshots():
    readable = _run_projectile(ProjectileReadable)
    fast = _run_projectile(ProjectileFast)
    assert readable == fast, (readable, fast)
    # Confirms this scenario actually exercised despawn (not a vacuous
    # comparison) -- same sanity bar the CPython parity test holds.
    assert len(readable[-2]) < 5, readable[-2]


def test_fast_projectile_over_100_sprites_still_allocates_nothing():
    """The same acceptance bar
    tests/test_vs2_behavior_gen_micropython.py's own
    test_generated_projectile_over_100_sprites_allocates_nothing holds the
    readable backend to -- confirms hoisting a self.<param> read to a
    local doesn't cost anything on real MicroPython (it should cost
    *less*, but zero-allocation is the acceptance bar every Behavior in
    this effort is held to, not "cheaper than before")."""
    import gc

    _fresh_runtime()

    class Game(vs2.Scene):
        idle_timeout = None
        back_button = False

        def build(self):
            self.world = self.layer("world", projection=vs2.TUNNEL)
            self.shots = self.world.sprite_pool("ship.png", count=99)
            self.targets = self.world.sprite_pool("ship.png", count=1)
            self.shots.behave(ProjectileFast(
                speed_x=0, speed_y=0, range=255, hits=self.targets))
            for index in range(99):
                self.shots.spawn(index, 0)

        def update(self):
            pass

    game = Game()
    director.push(game)
    behavior = game.shots.behavior(ProjectileFast)
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
# StateMachine (Enemy) parity
# ---------------------------------------------------------------------------

def _run_enemy(behavior_cls):
    _fresh_runtime()
    calls = []

    class Game(vs2.Scene):
        idle_timeout = None
        back_button = False

        def build(self):
            self.world = self.layer("world", projection=vs2.TUNNEL)
            self.enemies = self.world.sprite_pool("ship.png", count=1)
            self.targets = self.world.sprite_pool("ship.png", count=1)
            self.explosions = self.world.sprite_pool("ship.png", count=1)
            self.enemies.behave(behavior_cls(
                ground_y=50, explosion=self.explosions, hits=self.targets,
                on_death=lambda sprite: calls.append(True)))

        def update(self):
            pass

    game = Game()
    director.push(game)
    game.enemies.spawn(10, 10)
    game.targets.spawn(200, 200)  # far away: never hit

    behavior = game.enemies.behavior(behavior_cls)
    fields = ("x", "y", "fsm_state", "fsm_hold", "fsm_then", "frames_left")
    snapshots = []
    for tick in range(6):
        if tick == 3:
            game.enemies._live[0].y = 60  # force past ground_y -- see the
                                           # CPython parity test's own
                                           # identical comment
        behavior.step(game.enemies)
        snapshots.append(_snapshot(game.enemies, fields))
        snapshots.append(len(game.explosions))
        snapshots.append(len(calls))
    return snapshots


def test_enemy_readable_and_fast_produce_identical_snapshots():
    readable = _run_enemy(EnemyReadable)
    fast = _run_enemy(EnemyFast)
    assert readable == fast, (readable, fast)
    assert readable[-1] > 0, "on_death never called: scenario didn't reach exploding"


# ---------------------------------------------------------------------------
# Damageable parity
# ---------------------------------------------------------------------------

def _run_damageable(behavior_cls):
    _fresh_runtime()
    deaths = []

    class Game(vs2.Scene):
        idle_timeout = None
        back_button = False

        def build(self):
            self.world = self.layer("world", projection=vs2.TUNNEL)
            self.enemies = self.world.sprite_pool("ship.png", count=1)
            self.bullets = self.world.sprite_pool("ship.png", count=1)
            self.explosions = self.world.sprite_pool("ship.png", count=1)
            self.enemies.behave(behavior_cls(
                hp=2, invulnerable_ticks=2, blink=True,
                hits=self.bullets, explosion=self.explosions, score=40,
                on_death=lambda sprite, points: deaths.append(points)))

        def update(self):
            pass

    game = Game()
    director.push(game)
    game.enemies.spawn(10, 10)
    game.bullets.spawn(10, 10)

    behavior = game.enemies.behavior(behavior_cls)
    fields = ("x", "y", "damage_taken", "invuln_left", "visible")
    snapshots = []
    for _ in range(6):
        behavior.step(game.enemies)
        snapshots.append(_snapshot(game.enemies, fields))
        snapshots.append(len(game.explosions))
        snapshots.append(tuple(deaths))
    return snapshots


def test_damageable_readable_and_fast_produce_identical_snapshots():
    readable = _run_damageable(DamageableReadable)
    fast = _run_damageable(DamageableFast)
    assert readable == fast, (readable, fast)
    assert readable[-1] == (40,), readable[-1]


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("vs2 behavior gen fast backend (micropython): %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
