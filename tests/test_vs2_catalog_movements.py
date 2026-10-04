"""Tests for ``vs2/behaviors.py``'s catalog: T9's Movements tier (this
file's share -- T9b) plus :class:`~vs2.behaviors.ShuffleBag`.

Spec: ``docs/vs2-behaviors-proposal.md``, ``## The catalog`` -> ``###
Movements``, plus ``## Layers`` -> ``### Cameras``/``### Geometry helpers``
for :class:`~vs2.behaviors.Aiming`'s ``to_depth``/``polar`` use.
Work-breakdown card: ``docs/vs2-behaviors-implementation.md`` T9 (T9a builds
the catalog's Attributes tier in this same file, concurrently -- see the
banner below marking where that tier's own tests belong).

Deliberately **not** unittest-based, matching ``tests/test_vs2_behaviors.py``'s
precedent: this needs a real ``vs2`` scene to attach real Behaviors to, and a
plain script means the allocation benchmarks this task's acceptance list
demands can be run for real on the MicroPython unix port, not merely
simulated under CPython::

    python3 tests/test_vs2_catalog.py
    micropython tests/test_vs2_catalog.py

Only the CPython run is wired into ``tests/run_tests.py`` (``CPYTHON_TESTS``),
matching T8's own precedent for keeping that shared file's diff minimal.
"""

import os
import sys

# Relative to the repo root, matching every other test here.
sys.path.insert(0, "apps/micropython")

# uos/utime shims for CPython, needed transitively by the vs2 package's own
# imports (ventilastation.director etc.). Both modules already exist on
# MicroPython, where the imports below succeed and nothing is shimmed.
sys.modules.setdefault("uos", os)
try:
    import utime  # noqa: F401
except ImportError:
    import time as _time

    class _Utime:
        @staticmethod
        def ticks_ms():
            return int(_time.time() * 1000)

        @staticmethod
        def ticks_us():
            return int(_time.time() * 1000000)

        @staticmethod
        def ticks_add(value, delta):
            return value + delta

        @staticmethod
        def ticks_diff(end, start):
            return end - start
    sys.modules["utime"] = _Utime
    import utime  # noqa: E402

import gc  # noqa: E402
import math  # noqa: E402

from ventilastation import api_guard  # noqa: E402
from ventilastation.director import configure_runtime, director, reset_runtime, stripes  # noqa: E402

import vs2  # noqa: E402
from vs2 import actions, controls  # noqa: E402
from vs2.behaviors import (  # noqa: E402
    Aiming, Behavior, Chasing, Laned, Moving, Orbiting, Patrolling,
    PathFollowing, Pilotable, ShuffleBag,
)


def check(name, condition):
    if not condition:
        raise AssertionError("FAILED: " + name)
    print("ok:", name)


def check_raises(name, exc_type, fn):
    try:
        fn()
    except exc_type as exc:
        print("ok:", name, "->", exc_type.__name__ + ":", exc)
        return exc
    raise AssertionError("FAILED: %s did not raise %s" % (name, exc_type.__name__))


def check_close(name, actual, expected, tolerance=1e-6):
    if abs(actual - expected) > tolerance:
        raise AssertionError(
            "FAILED: %s (actual=%r, expected=%r, tolerance=%r)"
            % (name, actual, expected, tolerance))
    print("ok:", name)


def _mem_free():
    """MicroPython-only; ``None`` under CPython -- see
    ``tests/test_vs2_params.py``'s identical guard."""
    try:
        return gc.mem_free()
    except AttributeError:
        return None


def _assert_zero_alloc(name, warm_fn, run_fn, allowance=512):
    """Shared allocation-test body: warm up, then run ``run_fn`` and assert
    net heap growth stays within ``allowance`` bytes -- the pattern every
    task in this plan uses (see ``docs/vs2-behaviors-implementation.md``'s
    "Allocation tests are the real check")."""
    warm_fn()
    mem_free = _mem_free()
    if mem_free is None:
        print("SKIP allocation assertion for %r (no gc.mem_free() -- "
              "this is CPython, not MicroPython)" % (name,))
        run_fn()
        return
    gc.collect()
    before = gc.mem_free()
    run_fn()
    gc.collect()
    after = gc.mem_free()
    delta = before - after
    print("%s x many ticks: before=%d after=%d delta=%d bytes"
          % (name, before, after, delta))
    check("%s allocates ~0 bytes per tick (delta=%d, allowance=%d)"
          % (name, delta, allowance), delta <= allowance)


# ---------------------------------------------------------------------------
# Scene/pool scaffolding, mirroring tests/test_vs2_behaviors.py's setUp.
# ---------------------------------------------------------------------------

def _setup():
    reset_runtime()
    api_guard.reset()
    runtime = configure_runtime("headless")
    stripes.clear()
    stripes["ship.png"] = 0
    runtime.platform.sprites.stripes[0] = {
        "width": 4, "height": 4, "frames": 4, "palette": 0,
    }
    api_guard.begin_app("games.test_vs2_catalog", "vs2")
    return runtime


def _teardown():
    reset_runtime()
    api_guard.reset()


def _build_scene(build_fn):
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


def _press1(mask):
    """Simulate player 1's joystick/buttons reading ``mask`` this tick,
    with ``last_buttons`` left at whatever it was before this call -- so a
    test can distinguish ``held`` from ``just_pressed`` by calling this
    twice."""
    director.last_buttons = director.buttons
    director.buttons = mask


def _release_edges1():
    """Advance player 1's edge-detection state without changing which
    buttons are held -- so the *next* ``held`` read is unaffected but the
    *next* ``just_pressed`` read sees no new edge."""
    director.last_buttons = director.buttons


# =============================================================================
# Movements (T9b)
# =============================================================================

# ---------------------------------------------------------------------------
# Moving
# ---------------------------------------------------------------------------

def test_moving_accumulates_dx_dy_on_a_pool():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 0)
            scene.pool.behave(Moving(speed_x=1.5, speed_y=-2))

        game = _build_scene(build)
        game.pool.behavior(Moving).step(game.pool)
        sprite = game.pool._live[0]
        check("dx accumulated", sprite.dx == 1.5)
        check("dy accumulated", sprite.dy == -2)
    finally:
        _teardown()


def test_moving_accumulates_on_a_lone_sprite():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite("ship.png")
            scene.ship.behave(Moving(speed_x=1, speed_y=1))

        game = _build_scene(build)
        game.ship.behavior(Moving).step_one(game.ship)
        check("dx accumulated on a lone sprite", game.ship.dx == 1)
        check("dy accumulated on a lone sprite", game.ship.dy == 1)
    finally:
        _teardown()


def test_moving_composes_with_a_second_accumulating_movement():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 0)
            scene.pool.behave(Moving(speed_x=1, speed_y=0), name="a")
            scene.pool.behave(Moving(speed_x=2, speed_y=0), name="b")

        game = _build_scene(build)  # must not raise: both accumulate
        game.pool.behavior("a").step(game.pool)
        game.pool.behavior("b").step(game.pool)
        check("two accumulating movements add", game.pool._live[0].dx == 3)
    finally:
        _teardown()


def test_moving_allocates_nothing_per_tick():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=20)
            for i in range(20):
                scene.pool.spawn(i, i)
            scene.pool.behave(Moving(speed_x=0.5, speed_y=-0.25,
                                       accel_x=0.01, accel_y=0.01))

        game = _build_scene(build)
        behavior = game.pool.behavior(Moving)

        def run():
            for _ in range(1000):
                behavior.step(game.pool)

        _assert_zero_alloc("Moving.step over 20 sprites", run, run)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Patrolling
# ---------------------------------------------------------------------------

def test_patrolling_sine_stays_within_amplitude_and_applies_drift():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 100)
            scene.pool.behave(Patrolling(field="y", amplitude=10, period=20,
                                           wave="sine", drift_x=1, drift_y=0))

        game = _build_scene(build)
        behavior = game.pool.behavior(Patrolling)
        sprite = game.pool._live[0]
        min_y = 100.0
        max_y = 100.0
        for _ in range(40):  # two full periods
            behavior.step(game.pool)
            game._commit_pool_motion()
            if sprite.y < min_y:
                min_y = sprite.y
            if sprite.y > max_y:
                max_y = sprite.y
        check("sine patrol stays within amplitude of its start",
              89.9 <= min_y and max_y <= 110.1)
        check("drift_x accumulated across 40 ticks", sprite.x == 40)
    finally:
        _teardown()


def test_patrolling_square_wave_jumps_at_the_half_period():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 0)
            scene.pool.behave(Patrolling(field="y", amplitude=5, period=10,
                                           wave="square", drift_x=0, drift_y=0))

        game = _build_scene(build)
        behavior = game.pool.behavior(Patrolling)
        sprite = game.pool._live[0]
        deltas = []
        for _ in range(10):
            before = sprite.dy
            behavior.step(game.pool)
            deltas.append(sprite.dy - before)
            game._commit_pool_motion()
        # A square wave only ever jumps at tick 1 (into +amplitude) and at
        # the half-period mark (tick 6, into -amplitude); every other tick
        # contributes nothing.
        nonzero = [i for i, d in enumerate(deltas) if abs(d) > 1e-9]
        check("square wave only jumps twice in one period", len(nonzero) == 2)
    finally:
        _teardown()


def test_patrolling_two_sprites_oscillate_independently():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=2)
            scene.pool.spawn(0, 0)
            scene.pool.spawn(0, 0)
            scene.pool.behave(Patrolling(field="y", amplitude=10, period=20,
                                           wave="sine"))

        game = _build_scene(build)
        # Offset the second sprite's phase before stepping -- each sprite
        # owns its own primed patrol_phase (state), so this is legal.
        game.pool._live[1].patrol_phase = 5
        behavior = game.pool.behavior(Patrolling)
        behavior.step(game.pool)
        game._commit_pool_motion()
        check("differently-phased sprites in one pool move differently",
              game.pool._live[0].y != game.pool._live[1].y)
    finally:
        _teardown()


def test_patrolling_allocates_nothing_per_tick():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=20)
            for i in range(20):
                scene.pool.spawn(i, i)
            scene.pool.behave(Patrolling(field="y", amplitude=8, period=37,
                                           wave="triangle", drift_x=0.1))

        game = _build_scene(build)
        behavior = game.pool.behavior(Patrolling)

        def run():
            for _ in range(1000):
                behavior.step(game.pool)

        _assert_zero_alloc("Patrolling.step over 20 sprites", run, run)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# PathFollowing
# ---------------------------------------------------------------------------

def test_path_following_arrives_and_loops():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 0)
            # Each leg is a 10-unit move at speed 5 -- exactly 2 ticks per
            # leg, chosen so the test's own tick-counting cannot be
            # confused with an accidental one-tick arrival.
            scene.pool.behave(PathFollowing(
                points=((10, 0), (10, 10), (0, 10)),
                speed_x=5, speed_y=5, loop=True))

        game = _build_scene(build)
        behavior = game.pool.behavior(PathFollowing)
        sprite = game.pool._live[0]

        def run_ticks(n):
            for _ in range(n):
                behavior.step(game.pool)
                game._commit_pool_motion()

        run_ticks(2)
        check("arrived at the first waypoint", sprite.x == 10 and sprite.y == 0)
        run_ticks(2)
        check("arrived at the second waypoint", sprite.x == 10 and sprite.y == 10)
        run_ticks(2)
        check("arrived at the third waypoint", sprite.x == 0 and sprite.y == 10)
        run_ticks(2)
        check("looped back to the first waypoint", sprite.x == 10 and sprite.y == 0)
    finally:
        _teardown()


def test_path_following_then_despawn_and_on_finish_fires_once():
    _setup()
    try:
        calls = []

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 0)
            scene.pool.behave(PathFollowing(
                points=((5, 0),), speed_x=10, speed_y=10, loop=False,
                then="despawn", on_finish=lambda sprite: calls.append(1)))

        game = _build_scene(build)
        behavior = game.pool.behavior(PathFollowing)
        behavior.step(game.pool)
        game._commit_pool_motion()
        check("on_finish fired exactly once", calls == [1])
        check("then='despawn' despawned the sprite", len(game.pool) == 0)
        # A second step over the (now empty) pool must not double-fire.
        behavior.step(game.pool)
        check("on_finish did not fire again", calls == [1])
    finally:
        _teardown()


def test_path_following_relative_offsets_from_lazily_captured_origin():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(50, 50)
            scene.pool.behave(PathFollowing(
                points=((5, 5),), relative=True, speed_x=10, speed_y=10))

        game = _build_scene(build)
        behavior = game.pool.behavior(PathFollowing)
        sprite = game.pool._live[0]
        behavior.step(game.pool)
        game._commit_pool_motion()
        check("relative waypoint measured from the sprite's own spawn point",
              sprite.x == 55 and sprite.y == 55)
    finally:
        _teardown()


def test_path_following_needs_at_least_one_waypoint():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.behave(PathFollowing(points=()))

        check_raises("PathFollowing with no waypoints is a build-time error",
                     ValueError, lambda: _build_scene(build))
    finally:
        _teardown()


def test_path_following_allocates_nothing_per_tick():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=20)
            for i in range(20):
                scene.pool.spawn(i, i)
            scene.pool.behave(PathFollowing(
                points=((10, 0), (10, 40), (0, 40), (0, 0)),
                speed_x=2, speed_y=2, loop=True))

        game = _build_scene(build)
        behavior = game.pool.behavior(PathFollowing)

        def run():
            for _ in range(1000):
                behavior.step(game.pool)
                game._commit_pool_motion()

        _assert_zero_alloc("PathFollowing.step over 20 sprites", run, run)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Pilotable
# ---------------------------------------------------------------------------

def test_pilotable_direct_control_matches_held_input_exactly():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite("ship.png")
            scene.ship.behave(Pilotable(player=1, speed_x=2, speed_y=3,
                                          inertia=0))

        game = _build_scene(build)
        behavior = game.ship.behavior(Pilotable)
        director.buttons = controls.RIGHT | controls.DOWN
        director.last_buttons = 0
        behavior.step_one(game.ship)
        check("inertia=0: dx snaps straight to speed_x", game.ship.dx == 2)
        check("inertia=0: dy snaps straight to speed_y", game.ship.dy == 3)
        game.ship.dx = 0
        game.ship.dy = 0
        director.buttons = 0  # released
        behavior.step_one(game.ship)
        check("inertia=0: releasing input drops velocity to 0 immediately, "
              "no drift", game.ship.dx == 0 and game.ship.dy == 0)
    finally:
        _teardown()


def test_pilotable_rim_scheme_ignores_the_vertical_axis():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite("ship.png")
            scene.ship.behave(Pilotable(scheme="rim", speed_x=2, speed_y=3,
                                          inertia=0))

        game = _build_scene(build)
        behavior = game.ship.behavior(Pilotable)
        director.buttons = controls.RIGHT | controls.DOWN
        director.last_buttons = 0
        behavior.step_one(game.ship)
        check("rim scheme: x still responds", game.ship.dx == 2)
        check("rim scheme: y never responds to input", game.ship.dy == 0)
    finally:
        _teardown()


def test_pilotable_inertia_converges_monotonically_toward_target():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite("ship.png")
            scene.ship.behave(Pilotable(speed_x=2, speed_y=0, inertia=4,
                                          damping=0))

        game = _build_scene(build)
        behavior = game.ship.behavior(Pilotable)
        director.buttons = controls.RIGHT
        director.last_buttons = 0
        # rate = 1/(1+4) = 0.2; v1 = 0.4, v2 = 0.72, v3 = 0.976 (hand-worked
        # from the documented formula, not derived from this code).
        expected = [0.4, 0.72, 0.976]
        for target in expected:
            game.ship.dx = 0
            behavior.step_one(game.ship)
            check_close("inertia=4 velocity matches the hand-worked formula",
                        game.ship.dx, target, tolerance=1e-9)
        check("velocity stays below the target (asymptotic, never snaps)",
              game.ship.dx < 2)
    finally:
        _teardown()


def test_pilotable_damping_decays_velocity_after_release():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite("ship.png")
            scene.ship.behave(Pilotable(speed_x=2, speed_y=0, inertia=4,
                                          damping=0.5))

        game = _build_scene(build)
        behavior = game.ship.behavior(Pilotable)
        director.buttons = controls.RIGHT
        director.last_buttons = 0
        for _ in range(10):
            game.ship.dx = 0
            behavior.step_one(game.ship)
        built_up = game.ship.pilot_vx
        check("velocity built up while held", built_up > 0)
        director.buttons = 0  # release
        director.last_buttons = 0
        previous = built_up
        for _ in range(5):
            game.ship.dx = 0
            behavior.step_one(game.ship)
            current = game.ship.pilot_vx
            check("damping strictly decays velocity toward 0 each tick",
                  0 <= current < previous)
            previous = current
    finally:
        _teardown()


def test_pilotable_bounds_clamps_position_and_is_absolute():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite("ship.png")
            scene.ship.behave(Pilotable(
                speed_x=0, speed_y=20, inertia=0,
                bounds=(None, None, 0, 10)))

        game = _build_scene(build)
        behavior = game.ship.behavior(Pilotable)
        director.buttons = controls.DOWN
        director.last_buttons = 0
        for _ in range(5):
            behavior.step_one(game.ship)
            # A lone (non-pooled) sprite's dx/dy is never committed by the
            # framework's own _commit_pool_motion (it only walks
            # _payload_pools) -- commit it by hand here, the same way a
            # real game's update() loop would for a standalone sprite.
            game.ship.x = game.ship.x + game.ship.dx
            game.ship.y = game.ship.y + game.ship.dy
            game.ship.dx = 0
            game.ship.dy = 0
        check("bounds clamps y to its max", game.ship.y == 10)
    finally:
        _teardown()


def test_pilotable_follow_lag_eases_the_camera():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite("ship.png", x=40)
            scene.ship.behave(Pilotable(speed_x=0, speed_y=0, inertia=0,
                                          follow_lag=4))

        game = _build_scene(build)
        behavior = game.ship.behavior(Pilotable)
        director.buttons = 0
        director.last_buttons = 0
        check("camera starts at 0", game.world.camera_x == 0)
        behavior.step_one(game.ship)
        check_close("camera eases toward the sprite by delta/follow_lag",
                    game.world.camera_x, 10.0, tolerance=1e-9)
    finally:
        _teardown()


def test_pilotable_fire_button_spawns_once_per_press():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite("ship.png")
            scene.shots = scene.world.sprite_pool("ship.png", count=5)
            scene.ship.behave(Pilotable(speed_x=0, speed_y=0, inertia=0,
                                          fires=scene.shots,
                                          fire_button=controls.A))

        game = _build_scene(build)
        behavior = game.ship.behavior(Pilotable)
        director.buttons = controls.A
        director.last_buttons = 0  # edge: just pressed
        behavior.step_one(game.ship)
        check("one shot spawned on the press edge", len(game.shots) == 1)
        director.last_buttons = director.buttons  # still held, no new edge
        behavior.step_one(game.ship)
        check("holding the button does not spawn again", len(game.shots) == 1)
    finally:
        _teardown()


def test_pilotable_bounds_conflicts_with_path_following():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.behave(PathFollowing(points=((1, 1),)))
            scene.pool.behave(Pilotable(bounds=(None, None, 0, 10)))

        exc = check_raises(
            "bounded Pilotable after PathFollowing on one subject conflicts",
            ValueError, lambda: _build_scene(build))
        text = str(exc)
        check("names PathFollowing", "PathFollowing" in text)
        check("names Pilotable", "Pilotable" in text)
    finally:
        _teardown()


def test_pilotable_unbounded_does_not_conflict_with_path_following():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.behave(PathFollowing(points=((1, 1),)))
            scene.pool.behave(Pilotable())  # bounds=None: accumulates, fine

        _build_scene(build)  # must not raise
        print("ok: unbounded Pilotable composes with PathFollowing")
    finally:
        _teardown()


def test_pilotable_allocates_nothing_per_tick():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite("ship.png")
            scene.ship.behave(Pilotable(speed_x=1, speed_y=1, inertia=2,
                                          damping=0.1, follow_lag=10))

        game = _build_scene(build)
        behavior = game.ship.behavior(Pilotable)
        director.buttons = controls.RIGHT | controls.DOWN

        def run():
            for _ in range(1000):
                behavior.step_one(game.ship)

        _assert_zero_alloc("Pilotable.step_one", run, run)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Aiming
# ---------------------------------------------------------------------------

def test_aiming_moves_the_stick_and_clamps_to_the_unit_disc():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.cross = scene.world.sprite("ship.png")
            scene.cross.behave(Aiming(speed=0.1))

        game = _build_scene(build)
        behavior = game.cross.behavior(Aiming)
        director.buttons = controls.RIGHT
        director.last_buttons = 0
        for _ in range(50):  # far more than enough to saturate at 1.0
            behavior.step_one(game.cross)
        check("aim_x clamps to the unit disc", game.cross.aim_x == 1.0)
        check("aim_y stays at 0 (no vertical input)", game.cross.aim_y == 0.0)
    finally:
        _teardown()


def test_aiming_matches_layer_polar_and_to_depth_independently_recomputed():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.cross = scene.world.sprite("ship.png")
            scene.cross.behave(Aiming(speed=1.0))  # one tick saturates

        game = _build_scene(build)
        behavior = game.cross.behavior(Aiming)
        director.buttons = controls.RIGHT
        director.last_buttons = 0
        behavior.step_one(game.cross)
        game.cross.x = game.cross.x + game.cross.dx
        game.cross.y = game.cross.y + game.cross.dy

        # Independently recomputed from the proposal's own formulas (### Geometry
        # helpers' polar()), not by calling Aiming's code path.
        width = vs2.display.width
        angle = (0.75 * width - math.atan2(0, 1) * width / (2 * math.pi)) % width
        row = 1.0 * (vs2.display.height - 1)
        depth = game.world.to_depth(row)
        check_close("Aiming's angle matches an independently recomputed atan2",
                    game.cross.x % width, angle, tolerance=1e-6)
        check_close("Aiming's depth matches an independently recomputed "
                    "to_depth(row)", game.cross.y, depth, tolerance=1e-6)
    finally:
        _teardown()


def test_aiming_bounds_restricts_reach():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.cross = scene.world.sprite("ship.png")
            scene.cross.behave(Aiming(speed=1.0, bounds=(None, 0.5)))

        game = _build_scene(build)
        behavior = game.cross.behavior(Aiming)
        director.buttons = controls.RIGHT
        director.last_buttons = 0
        behavior.step_one(game.cross)
        check_close("bounds clamps the stick's radius to radius_max",
                    game.cross.aim_x, 0.5, tolerance=1e-9)
    finally:
        _teardown()


def test_aiming_fire_button_spawns_from_the_pool():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.cross = scene.world.sprite("ship.png")
            scene.shots = scene.world.sprite_pool("ship.png", count=3)
            scene.cross.behave(Aiming(fires=scene.shots, fire_button=controls.A))

        game = _build_scene(build)
        behavior = game.cross.behavior(Aiming)
        director.buttons = controls.A
        director.last_buttons = 0
        behavior.step_one(game.cross)
        check("Aiming's fire button spawns from the pool", len(game.shots) == 1)
    finally:
        _teardown()


def test_aiming_allocates_nothing_per_tick():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.cross = scene.world.sprite("ship.png")
            scene.cross.behave(Aiming(speed=0.05))

        game = _build_scene(build)
        behavior = game.cross.behavior(Aiming)
        director.buttons = controls.RIGHT | controls.UP

        def run():
            for _ in range(1000):
                behavior.step_one(game.cross)

        _assert_zero_alloc("Aiming.step_one", run, run)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Chasing
# ---------------------------------------------------------------------------

def test_chasing_turns_toward_a_lone_sprite_target_at_a_limited_rate():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.hunter = scene.world.sprite("ship.png")
            scene.prey = scene.world.sprite("ship.png", x=0, y=100)
            scene.hunter.behave(Chasing(target=scene.prey, speed_x=0,
                                          speed_y=1, turn_rate=0.1))

        game = _build_scene(build)
        behavior = game.hunter.behavior(Chasing)
        # prey is straight ahead (dx=0, dy=100): desired heading atan2(100,0)
        # = pi/2. Starting heading is 0 (primed): turn_rate=0.1 caps the
        # first tick's turn at 0.1 rad, far short of pi/2.
        behavior.step_one(game.hunter)
        check_close("heading turns by at most turn_rate on the first tick",
                    game.hunter.chase_heading, 0.1, tolerance=1e-9)
    finally:
        _teardown()


def test_chasing_gives_up_beyond_range():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.hunter = scene.world.sprite("ship.png")
            scene.prey = scene.world.sprite("ship.png", x=0, y=300)
            scene.hunter.behave(Chasing(target=scene.prey, speed_x=1,
                                          speed_y=1, give_up_range=50))

        game = _build_scene(build)
        behavior = game.hunter.behavior(Chasing)
        behavior.step_one(game.hunter)
        check("beyond give_up_range contributes nothing",
              game.hunter.dx == 0 and game.hunter.dy == 0)
    finally:
        _teardown()


def test_chasing_finds_the_nearest_pool_member_and_fires_on_reach_once():
    _setup()
    try:
        calls = []

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.hunter = scene.world.sprite("ship.png", x=0, y=0)
            scene.prey = scene.world.sprite_pool("ship.png", count=2)
            scene.prey.spawn(0, 200)  # far
            scene.prey.spawn(0, 0)    # exactly overlapping the hunter
            scene.hunter.behave(Chasing(
                target=scene.prey, speed_x=0, speed_y=0, turn_rate=1,
                on_reach=lambda hunter, caught: calls.append(caught)))

        game = _build_scene(build)
        behavior = game.hunter.behavior(Chasing)
        behavior.step_one(game.hunter)
        check("on_reach fired once, against the nearer (overlapping) prey",
              calls == [game.prey._live[1]])
        behavior.step_one(game.hunter)
        check("on_reach does not refire while still overlapping",
              len(calls) == 1)
    finally:
        _teardown()


def test_chasing_allocates_nothing_per_tick():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.hunter = scene.world.sprite("ship.png")
            scene.prey = scene.world.sprite_pool("ship.png", count=10)
            for i in range(10):
                scene.prey.spawn(i, i)
            scene.hunter.behave(Chasing(target=scene.prey, speed_x=1,
                                          speed_y=1, turn_rate=0.2))

        game = _build_scene(build)
        behavior = game.hunter.behavior(Chasing)

        def run():
            for _ in range(1000):
                behavior.step_one(game.hunter)

        _assert_zero_alloc("Chasing.step_one against a 10-sprite pool",
                            run, run)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Orbiting
# ---------------------------------------------------------------------------

def test_orbiting_moves_at_constant_angular_speed_and_snaps_to_radius():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.moon = scene.world.sprite("ship.png", x=0, y=30)
            scene.moon.behave(Orbiting(centre_y=50, speed=3))

        game = _build_scene(build)
        behavior = game.moon.behavior(Orbiting)
        behavior.step_one(game.moon)
        check("dx accumulates the angular speed", game.moon.dx == 3)
        check("dy snaps toward centre_y in one tick",
              game.moon.dy == 20)  # 50 - 30
    finally:
        _teardown()


def test_orbiting_composes_with_moving():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 50)
            scene.pool.behave(Orbiting(centre_y=50, speed=2))
            scene.pool.behave(Moving(speed_x=1, speed_y=0))

        _build_scene(build)  # must not raise: both accumulate
        print("ok: Orbiting composes with Moving (both accumulate)")
    finally:
        _teardown()


def test_orbiting_allocates_nothing_per_tick():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=20)
            for i in range(20):
                scene.pool.spawn(i, i)
            scene.pool.behave(Orbiting(centre_y=50, speed=1))

        game = _build_scene(build)
        behavior = game.pool.behavior(Orbiting)

        def run():
            for _ in range(1000):
                behavior.step(game.pool)

        _assert_zero_alloc("Orbiting.step over 20 sprites", run, run)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Laned
# ---------------------------------------------------------------------------

def test_laned_eases_to_the_current_lane_and_switches():
    _setup()
    try:
        calls = []

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 0)
            scene.pool.behave(Laned(centres=(0, 10, 20), speed=32,
                                      on_change=lambda sprite, index: calls.append(index)))

        game = _build_scene(build)
        behavior = game.pool.behavior(Laned)
        sprite = game.pool._live[0]
        behavior.step(game.pool)
        game._commit_pool_motion()
        check("already on lane 0: on_change fires once at attach-time lane",
              calls == [0])
        sprite.lane_index = 2
        behavior.step(game.pool)
        game._commit_pool_motion()
        check("switching lane_index eases toward the new centre",
              sprite.y == 20)
        check("on_change fired for the new lane", calls == [0, 2])
    finally:
        _teardown()


def test_laned_needs_at_least_one_lane():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.behave(Laned(centres=()))

        check_raises("Laned with no lanes is a build-time error",
                     ValueError, lambda: _build_scene(build))
    finally:
        _teardown()


def test_laned_composes_with_moving_on_x():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 0)
            scene.pool.behave(Laned(centres=(0,), speed=10))
            scene.pool.behave(Moving(speed_x=2, speed_y=0))

        _build_scene(build)  # must not raise
        print("ok: Laned (owns y) composes with Moving (drives x)")
    finally:
        _teardown()


def test_laned_conflicts_with_laned_same_class_twice():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.behave(Laned(centres=(0,)), name="first")
            scene.pool.behave(Laned(centres=(10,)), name="second")

        # Two instances of the same class declare identical `state` field
        # names, so this actually surfaces as StateConflictError -- T5/T8's
        # pre-existing per-subject state-ownership check -- fired while
        # priming the *second* Laned's state, before _guard_absolute_position
        # (called from attached(), later) ever runs. Still a build-time
        # error naming both sides, just via the mechanism that gets there
        # first for an identical-class pair specifically (see this task's
        # report).
        exc = check_raises(
            "two Laned on one subject (same class twice) conflicts",
            vs2.StateConflictError, lambda: _build_scene(build))
        check("names Laned on both sides", str(exc).count("Laned") >= 2)
    finally:
        _teardown()


def test_laned_conflicts_with_bounded_pilotable():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.behave(Laned(centres=(0,)))
            scene.pool.behave(Pilotable(bounds=(0, 100, 0, 100)))

        exc = check_raises(
            "Laned then bounded Pilotable on one subject conflicts",
            ValueError, lambda: _build_scene(build))
        text = str(exc)
        check("names Laned", "Laned" in text)
        check("names Pilotable", "Pilotable" in text)
    finally:
        _teardown()


def test_laned_allocates_nothing_per_tick():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=20)
            for i in range(20):
                scene.pool.spawn(i, i % 3 * 10)
            scene.pool.behave(Laned(centres=(0, 10, 20), speed=2))

        game = _build_scene(build)
        behavior = game.pool.behavior(Laned)

        def run():
            for _ in range(1000):
                behavior.step(game.pool)

        _assert_zero_alloc("Laned.step over 20 sprites", run, run)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# The absolute-position conflict rule: the remaining pairwise combination
# (PathFollowing vs Laned) not already covered above, plus PathFollowing
# same-class-twice.
# ---------------------------------------------------------------------------

def test_path_following_conflicts_with_laned():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.behave(PathFollowing(points=((1, 1),)))
            scene.pool.behave(Laned(centres=(0,)))

        exc = check_raises(
            "PathFollowing then Laned on one subject conflicts",
            ValueError, lambda: _build_scene(build))
        text = str(exc)
        check("names PathFollowing", "PathFollowing" in text)
        check("names Laned", "Laned" in text)
    finally:
        _teardown()


def test_path_following_conflicts_with_path_following_same_class_twice():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.behave(PathFollowing(points=((1, 1),)), name="first")
            scene.pool.behave(PathFollowing(points=((2, 2),)), name="second")

        # Same reasoning as the Laned same-class-twice test above: identical
        # `state` names on the second attach trip StateConflictError before
        # attached()/_guard_absolute_position ever runs.
        exc = check_raises(
            "two PathFollowing on one subject (same class twice) conflicts",
            vs2.StateConflictError, lambda: _build_scene(build))
        check("names PathFollowing on both sides",
              str(exc).count("PathFollowing") >= 2)
    finally:
        _teardown()


def test_bounded_pilotable_conflicts_with_bounded_pilotable_same_class_twice():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.behave(Pilotable(bounds=(0, 10, 0, 10)), name="first")
            scene.pool.behave(Pilotable(bounds=(0, 10, 0, 10)), name="second")

        # Same reasoning again: identical `state` names (pilot_vx/pilot_vy)
        # on the second attach trip StateConflictError first.
        exc = check_raises(
            "two bounded Pilotable on one subject (same class twice) "
            "conflicts", vs2.StateConflictError, lambda: _build_scene(build))
        check("names Pilotable on both sides", str(exc).count("Pilotable") >= 2)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# ShuffleBag
# ---------------------------------------------------------------------------

def test_shuffle_bag_draws_every_item_once_per_cycle():
    bag = ShuffleBag(("a", "b", "c", "d"))
    drawn = [bag.draw() for _ in range(4)]
    check("one full cycle is a permutation of every item",
          sorted(drawn) == ["a", "b", "c", "d"])
    drawn2 = [bag.draw() for _ in range(4)]
    check("the next cycle is also a full permutation",
          sorted(drawn2) == ["a", "b", "c", "d"])


def test_shuffle_bag_reshuffles_across_many_cycles():
    bag = ShuffleBag((1, 2, 3, 4, 5))
    cycles = set()
    for _ in range(50):
        cycles.add(tuple(bag.draw() for _ in range(5)))
    check("many cycles produce more than one distinct order",
          len(cycles) > 1)


def test_shuffle_bag_single_item():
    bag = ShuffleBag(("only",))
    check("a single-item bag always draws that item",
          [bag.draw() for _ in range(5)] == ["only"] * 5)


def test_shuffle_bag_rejects_empty():
    check_raises("ShuffleBag() rejects an empty sequence",
                 ValueError, lambda: ShuffleBag(()))


def test_shuffle_bag_allocates_nothing_per_draw():
    bag = ShuffleBag(tuple(range(8)))

    def run():
        for _ in range(4000):  # 500 full cycles
            bag.draw()

    _assert_zero_alloc("ShuffleBag.draw", run, run)


# =============================================================================
# T9a's Attributes-tier tests belong below this banner (kept separate so the
# two agents' independent additions to this shared file merge cleanly).
# =============================================================================


MOVEMENT_TESTS = [
    test_moving_accumulates_dx_dy_on_a_pool,
    test_moving_accumulates_on_a_lone_sprite,
    test_moving_composes_with_a_second_accumulating_movement,
    test_moving_allocates_nothing_per_tick,
    test_patrolling_sine_stays_within_amplitude_and_applies_drift,
    test_patrolling_square_wave_jumps_at_the_half_period,
    test_patrolling_two_sprites_oscillate_independently,
    test_patrolling_allocates_nothing_per_tick,
    test_path_following_arrives_and_loops,
    test_path_following_then_despawn_and_on_finish_fires_once,
    test_path_following_relative_offsets_from_lazily_captured_origin,
    test_path_following_needs_at_least_one_waypoint,
    test_path_following_allocates_nothing_per_tick,
    test_pilotable_direct_control_matches_held_input_exactly,
    test_pilotable_rim_scheme_ignores_the_vertical_axis,
    test_pilotable_inertia_converges_monotonically_toward_target,
    test_pilotable_damping_decays_velocity_after_release,
    test_pilotable_bounds_clamps_position_and_is_absolute,
    test_pilotable_follow_lag_eases_the_camera,
    test_pilotable_fire_button_spawns_once_per_press,
    test_pilotable_bounds_conflicts_with_path_following,
    test_pilotable_unbounded_does_not_conflict_with_path_following,
    test_pilotable_allocates_nothing_per_tick,
    test_aiming_moves_the_stick_and_clamps_to_the_unit_disc,
    test_aiming_matches_layer_polar_and_to_depth_independently_recomputed,
    test_aiming_bounds_restricts_reach,
    test_aiming_fire_button_spawns_from_the_pool,
    test_aiming_allocates_nothing_per_tick,
    test_chasing_turns_toward_a_lone_sprite_target_at_a_limited_rate,
    test_chasing_gives_up_beyond_range,
    test_chasing_finds_the_nearest_pool_member_and_fires_on_reach_once,
    test_chasing_allocates_nothing_per_tick,
    test_orbiting_moves_at_constant_angular_speed_and_snaps_to_radius,
    test_orbiting_composes_with_moving,
    test_orbiting_allocates_nothing_per_tick,
    test_laned_eases_to_the_current_lane_and_switches,
    test_laned_needs_at_least_one_lane,
    test_laned_composes_with_moving_on_x,
    test_laned_conflicts_with_laned_same_class_twice,
    test_laned_conflicts_with_bounded_pilotable,
    test_laned_allocates_nothing_per_tick,
    test_path_following_conflicts_with_laned,
    test_path_following_conflicts_with_path_following_same_class_twice,
    test_bounded_pilotable_conflicts_with_bounded_pilotable_same_class_twice,
    test_shuffle_bag_draws_every_item_once_per_cycle,
    test_shuffle_bag_reshuffles_across_many_cycles,
    test_shuffle_bag_single_item,
    test_shuffle_bag_rejects_empty,
    test_shuffle_bag_allocates_nothing_per_draw,
]

TESTS = MOVEMENT_TESTS


def main():
    for test in TESTS:
        print("--- %s ---" % test.__name__)
        test()
    print("ALL PASS: %d checks" % len(TESTS))


if __name__ == "__main__":
    main()
