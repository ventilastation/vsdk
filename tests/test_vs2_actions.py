"""Tests for ``vs2/actions.py``: ``Action``, ``Move``, ``MoveTo``, ``Animate``
and ``Collide``.

Deliberately **not** unittest-based, matching ``tests/test_vs2_params.py``'s
precedent rather than ``tests/test_vs2_api.py``'s: this file needs the full
``vs2`` package (Scene, Layer, SpritePool, Family) to build real sprites to
move and collide, which ``tests/test_vs2_api_micropython.py`` already proves
works fine as a plain script on the MicroPython unix port (no ``unittest``
there). Writing it the same way means the allocation and dispatch-cost
benchmarks the T4 acceptance list demands can be run for real on MicroPython,
not merely simulated under CPython, by invoking this file directly:

    python3 tests/test_vs2_actions.py
    micropython tests/test_vs2_actions.py

Only the CPython run is wired into ``tests/run_tests.py`` (``CPYTHON_TESTS``),
per this task's own instructions to keep that shared file's diff minimal --
the MicroPython run above was used by hand while building this file to get
the real numbers reported alongside the implementation.
"""

import os
import sys

# Relative to the repo root, matching every other test here (both the
# CPython and MicroPython runners in tests/run_tests.py invoke test scripts
# with the repo root as cwd) -- MicroPython's `os` module has no `os.path`,
# so this deliberately avoids it, the same way tests/test_vs2_params.py and
# tests/test_vs2_api_micropython.py do.
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

from ventilastation import api_guard  # noqa: E402
from ventilastation.director import configure_runtime, director, reset_runtime, stripes  # noqa: E402

import vs2  # noqa: E402
from vs2 import actions  # noqa: E402
from vs2.params import Var  # noqa: E402


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


def _mem_free():
    """MicroPython-only; ``None`` under CPython -- see
    ``tests/test_vs2_params.py``'s identical guard."""
    try:
        return gc.mem_free()
    except AttributeError:
        return None


def _is_micropython():
    return (hasattr(sys, "implementation")
            and getattr(sys.implementation, "name", "") == "micropython")


# ---------------------------------------------------------------------------
# Scene/pool scaffolding, mirroring tests/test_vs2_api.py's setUp/tearDown as
# plain functions instead of unittest fixtures.
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
    api_guard.begin_app("games.test_vs2_actions", "vs2")
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


# ---------------------------------------------------------------------------
# Move: accumulates into dx/dy, never touches x/y directly.
# ---------------------------------------------------------------------------

def test_move_accumulates_into_dx_dy_and_the_scene_commit_applies_it():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=4)
            for _ in range(3):
                scene.pool.spawn(10, 20)

        game = _build_scene(build)
        move = actions.Move(speed_x=1.5, speed_y=-2)
        move.run(game.pool)
        for sprite in game.pool._live:
            check("dx accumulated, not committed", sprite.dx == 1.5)
            check("dy accumulated, not committed", sprite.dy == -2)
            check("x untouched before commit", sprite.x == 10)
            check("y untouched before commit", sprite.y == 20)
        game._commit_pool_motion()
        for sprite in game.pool._live:
            check("x moved after commit", abs(sprite.x - 11.5) < 1e-9)
            check("y moved after commit", abs(sprite.y - 18) < 1e-9)
            check("dx zeroed after commit", sprite.dx == 0)
            check("dy zeroed after commit", sprite.dy == 0)
    finally:
        _teardown()


def test_move_composes_with_a_second_movement_action_on_one_pool():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=2)
            scene.pool.spawn(0, 0)

        game = _build_scene(build)
        drift = actions.Move(speed_x=1, speed_y=0)
        fall = actions.Move(speed_x=0, speed_y=2)
        drift.run(game.pool)
        fall.run(game.pool)
        sprite = game.pool._live[0]
        check("both Moves added into the same accumulator",
              sprite.dx == 1 and sprite.dy == 2)
        game._commit_pool_motion()
        check("commit applies the combined accumulator",
              sprite.x == 1 and sprite.y == 2)
    finally:
        _teardown()


def test_move_accel_updates_speed_once_per_run_call_not_per_sprite():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=3)
            for _ in range(3):
                scene.pool.spawn(0, 0)

        game = _build_scene(build)
        move = actions.Move(speed_x=1, speed_y=0, accel_x=0.5, accel_y=0)
        move.run(game.pool)  # 3 live sprites, one run() call
        check("accel advanced speed_x exactly once regardless of pool size",
              move.speed_x == 1.5)
        move.run(game.pool)
        check("accel keeps advancing once per run() call",
              move.speed_x == 2.0)
        for sprite in game.pool._live:
            check("every sprite in the pool got the same dx",
                  sprite.dx == 1 + 1.5)
    finally:
        _teardown()


def test_move_rejects_var_bound_speed_combined_with_literal_accel():
    check_raises(
        "Move: Var speed_x with nonzero accel_x",
        ValueError,
        lambda: actions.Move(speed_x=Var("speed"), accel_x=1),
    )
    check_raises(
        "Move: Var-bound accel is never allowed",
        ValueError,
        lambda: actions.Move(accel_x=Var("accel")),
    )
    # Var-bound speed with *zero* accel is fine -- nothing to advance.
    actions.Move(speed_x=Var("speed"), accel_x=0)


def test_move_var_bound_speed_forces_the_per_sprite_path_and_reads_per_sprite():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=2)
            scene.pool.var("speed_y", 0, min=-32, max=32)
            fast = scene.pool.spawn(0, 0)
            fast.speed_y = 5
            slow = scene.pool.spawn(0, 0)
            slow.speed_y = 1

        game = _build_scene(build)
        move = actions.Move(speed_x=0, speed_y=Var("speed_y"))
        check("Var-bound parameter is detected at construction", move._uses_var)
        move.run(game.pool)
        fast, slow = game.pool._live
        check("fast sprite reads its own speed_y", fast.dy == 5)
        check("slow sprite reads its own speed_y", slow.dy == 1)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# MoveTo: clamped step toward a target, wraps X the short way, DONE on
# arrival.
# ---------------------------------------------------------------------------

def test_moveto_clamps_its_step_and_returns_done_on_arrival():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)

        game = _build_scene(build)
        sprite = game.pool.spawn(0, 0)
        move_to = actions.MoveTo(x=10, y=0, speed_x=3, speed_y=1)

        result = move_to.run_one(sprite)
        check("first tick clamps the step to speed", sprite.dx == 3)
        check("not yet arrived", result is None)
        game._commit_pool_motion()
        check("x advanced by the clamped step", sprite.x == 3)

        arrived_tick = None
        for tick in range(1, 10):
            result = move_to.run_one(sprite)
            game._commit_pool_motion()
            if result is vs2.DONE:
                arrived_tick = tick
                break
        check("MoveTo eventually reports DONE", arrived_tick is not None)
        check("sprite lands exactly on the target, no overshoot", sprite.x == 10)

        # Idempotent once arrived: MoveTo is a stateless per-call distance
        # check (it holds no per-sprite "already told you" latch -- a
        # shared latch on the Action itself would be wrong here, since one
        # MoveTo instance is routinely applied to many different sprites
        # converging on the same target). So it keeps reporting DONE, and
        # keeps contributing zero movement, for as long as the sprite sits
        # exactly on the target.
        result = move_to.run_one(sprite)
        check("no further movement once arrived", sprite.dx == 0)
        check("DONE keeps reporting true while parked on the target",
              result is vs2.DONE)
    finally:
        _teardown()


def test_moveto_wraps_the_shorter_way_around_the_circular_x_axis():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)

        game = _build_scene(build)
        sprite = game.pool.spawn(2, 0)
        move_to = actions.MoveTo(x=254, y=0, speed_x=10, speed_y=0)
        result = move_to.run_one(sprite)
        check("shortest path from 2 to 254 goes backward through 0",
              sprite.dx == -4)
        check("arrives in a single tick since 4 <= speed 10",
              result is vs2.DONE)
    finally:
        _teardown()


def test_moveto_bulk_run_hoists_and_matches_run_one():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=2)
            scene.pool.spawn(0, 0)
            scene.pool.spawn(5, 5)

        game = _build_scene(build)
        move_to = actions.MoveTo(x=20, y=20, speed_x=2, speed_y=2)
        move_to.run(game.pool)
        for sprite in game.pool._live:
            check("bulk run() clamps each sprite's own step",
                  sprite.dx == 2 and sprite.dy == 2)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Animate: field=, loop/once/pingpong modes, DONE at cycle end.
# ---------------------------------------------------------------------------

def test_animate_loop_mode_cycles_and_wraps_forever():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)

        game = _build_scene(build)
        sprite = game.pool.spawn(0, 0)
        anim = actions.Animate(first=0, last=2, ticks=1, mode="loop")
        frames = []
        for _ in range(6):
            anim.run(game.pool)
            frames.append(sprite.frame)
        check("loop mode cycles 0,1,2,0,1,2 with ticks=1",
              frames == [0, 1, 2, 0, 1, 2])
    finally:
        _teardown()


def test_animate_ticks_holds_each_frame():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)

        game = _build_scene(build)
        sprite = game.pool.spawn(0, 0)
        anim = actions.Animate(first=0, last=1, ticks=2, mode="loop")
        frames = []
        for _ in range(8):
            anim.run(game.pool)
            frames.append(sprite.frame)
        check("each frame held for 2 ticks: 0,0,1,1,0,0,1,1",
              frames == [0, 0, 1, 1, 0, 0, 1, 1])
    finally:
        _teardown()


def test_animate_once_mode_holds_on_last_and_run_one_reports_done():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)

        game = _build_scene(build)
        sprite = game.pool.spawn(0, 0)
        anim = actions.Animate(first=0, last=2, ticks=1, mode="once")

        results = []
        frames = []
        for _ in range(5):
            frames.append(sprite.frame)
            anim.run(game.pool)
            results.append(anim.run_one(sprite))
        check("once mode plays 0,1,2 then holds on 2",
              frames == [0, 1, 2, 2, 2])
        done_count = sum(1 for r in results if r is vs2.DONE)
        check("run_one() reports DONE exactly once for a 'once' cycle",
              done_count == 1)
    finally:
        _teardown()


def test_animate_pingpong_mode_bounces_between_first_and_last():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)

        game = _build_scene(build)
        sprite = game.pool.spawn(0, 0)
        anim = actions.Animate(first=0, last=2, ticks=1, mode="pingpong")
        frames = []
        for _ in range(8):
            anim.run(game.pool)
            frames.append(sprite.frame)
        check("pingpong bounces 0,1,2,1,0,1,2,1",
              frames == [0, 1, 2, 1, 0, 1, 2, 1])
    finally:
        _teardown()


def test_animate_field_writes_a_declared_instance_variable_not_frame():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.var("boom_radius", 0, min=0, max=255)

        game = _build_scene(build)
        sprite = game.pool.spawn(0, 0)
        anim = actions.Animate(field="boom_radius", first=0, last=3, ticks=1, mode="loop")
        anim.run(game.pool)
        check("Animate writes the custom field, not sprite.frame",
              sprite.boom_radius == 0 and sprite.frame == 0)
        anim.run(game.pool)
        check("custom field advances", sprite.boom_radius == 1)
    finally:
        _teardown()


def test_animate_rejects_var_bound_clock_parameters():
    check_raises(
        "Animate: Var-bound first/last/ticks/mode is rejected",
        ValueError,
        lambda: actions.Animate(first=Var("first"), last=3, ticks=1),
    )


def test_animate_rejects_non_string_field():
    check_raises(
        "Animate: field must be a string",
        TypeError,
        lambda: actions.Animate(field=123),
    )


# ---------------------------------------------------------------------------
# Collide: same-layer only, world space by default, radius, family targets.
# ---------------------------------------------------------------------------

def test_collide_box_on_hud_matches_sprite_overlaps_exactly():
    _setup()
    try:
        def build(scene):
            scene.hud = scene.layer("hud", projection=vs2.HUD)
            scene.shots = scene.hud.sprite_pool("ship.png", count=2)
            scene.baddies = scene.hud.sprite_pool("ship.png", count=2)

        game = _build_scene(build)
        shot = game.shots.spawn(10, 5)
        hit_baddie = game.baddies.spawn(11, 5)     # 4x4 sprites: overlaps
        miss_baddie = game.baddies.spawn(100, 5)   # far away: does not

        # Ground truth via the framework's own existing box test.
        check("sanity: shot overlaps the near baddie via Sprite.overlaps()",
              shot.overlaps(hit_baddie))
        check("sanity: shot does not overlap the far baddie",
              not shot.overlaps(miss_baddie))

        collide = actions.Collide(targets=game.baddies)
        result = collide.run_one(shot)
        check("Collide.run_one() finds exactly the sprite Sprite.overlaps() would",
              result is hit_baddie)

        game.baddies.despawn(hit_baddie)
        result2 = collide.run_one(shot)
        check("Collide returns None once nothing overlaps", result2 is None)
    finally:
        _teardown()


def test_collide_against_a_single_sprite_target():
    _setup()
    try:
        def build(scene):
            scene.hud = scene.layer("hud", projection=vs2.HUD)
            scene.shots = scene.hud.sprite_pool("ship.png", count=1)
            scene.wall = scene.hud.sprite("ship.png", x=10, y=5)

        game = _build_scene(build)
        shot = game.shots.spawn(11, 5)
        collide = actions.Collide(targets=game.wall)
        check("Collide against a lone Sprite target works",
              collide.run_one(shot) is game.wall)
    finally:
        _teardown()


def test_collide_radius_does_a_circular_test_not_a_box_test():
    _setup()
    try:
        def build(scene):
            scene.hud = scene.layer("hud", projection=vs2.HUD)
            scene.shots = scene.hud.sprite_pool("ship.png", count=1)
            scene.baddies = scene.hud.sprite_pool("ship.png", count=2)

        game = _build_scene(build)
        shot = game.shots.spawn(10, 10)
        near = game.baddies.spawn(13, 10)   # distance 3
        far = game.baddies.spawn(20, 10)    # distance 10

        collide = actions.Collide(targets=game.baddies, radius=5)
        check("radius test finds the near target", collide.run_one(shot) is near)

        game.baddies.despawn(near)
        check("radius test excludes the far target", collide.run_one(shot) is None)
    finally:
        _teardown()


def test_collide_cross_layer_target_is_an_error_naming_both_layers():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.hud = scene.layer("hud", projection=vs2.HUD)
            scene.shots = scene.world.sprite_pool("ship.png", count=1)
            scene.baddies = scene.hud.sprite_pool("ship.png", count=1)

        game = _build_scene(build)
        game.shots.spawn(0, 0)
        game.baddies.spawn(0, 0)

        # Eager form: subject known at construction (a future Behavior's
        # attach-time wiring), so this raises immediately, before any tick.
        exc = check_raises(
            "Collide(subject=...) validates cross-layer eagerly",
            ValueError,
            lambda: actions.Collide(targets=game.baddies, subject=game.shots),
        )
        message = str(exc)
        check("message names the target's layer", "hud" in message)
        check("message names the subject's layer", "world" in message)

        # Lazy form: matches the proposal's own worked construction
        # (`Collide(self.hits)`, no subject given up front) -- caught the
        # first time it is actually run, before any collision is tested.
        lazy = actions.Collide(targets=game.baddies)
        check_raises(
            "Collide without subject= is still caught on its first run_one()",
            ValueError,
            lambda: lazy.run_one(game.shots._live[0]),
        )
    finally:
        _teardown()


def test_collide_rejects_an_unsupported_target_type():
    check_raises(
        "Collide: targets must be Sprite/SpritePool/Family",
        TypeError,
        lambda: actions.Collide(targets=object()),
    )


def test_collide_against_a_family_spanning_two_pools_and_a_sprite():
    _setup()
    try:
        def build(scene):
            scene.hud = scene.layer("hud", projection=vs2.HUD)
            scene.shots = scene.hud.sprite_pool("ship.png", count=1)
            scene.pool_a = scene.hud.sprite_pool("ship.png", count=2)
            scene.pool_b = scene.hud.sprite_pool("ship.png", count=2)
            scene.lone = scene.hud.sprite("ship.png", x=200, y=0)
            scene.pack = scene.family(scene.pool_a, scene.pool_b, scene.lone)

        game = _build_scene(build)
        shot = game.shots.spawn(10, 10)
        game.pool_a.spawn(50, 10)   # far
        near = game.pool_b.spawn(11, 10)  # overlaps

        collide = actions.Collide(targets=game.pack)
        check("Collide finds a hit inside a Family spanning two pools",
              collide.run_one(shot) is near)

        game.pool_b.despawn(near)
        # Now only the lone sprite in the family is near; move the shot to it.
        shot.x = 200
        shot.y = 0
        check("Collide also tests a lone Sprite member of the Family",
              collide.run_one(shot) is game.lone)
    finally:
        _teardown()


def test_collide_family_construction_reads_members_exactly_once():
    """The grounding note's zero-allocation contract for a Family target:
    ``.members`` (the allocating, tuple-rebuilding property) must be read
    at most once, at construction -- never inside the per-tick path."""
    _setup()
    try:
        def build(scene):
            scene.hud = scene.layer("hud", projection=vs2.HUD)
            scene.shots = scene.hud.sprite_pool("ship.png", count=1)
            scene.pool_a = scene.hud.sprite_pool("ship.png", count=2)
            scene.pack = scene.family(scene.pool_a)

        game = _build_scene(build)
        shot = game.shots.spawn(10, 10)
        game.pool_a.spawn(11, 10)

        calls = [0]
        original_members = type(game.pack).members
        # Patch the *class* property so every access anywhere is counted --
        # construction is expected to touch it, the per-tick path must not.
        try:
            def counting_members(self):
                calls[0] += 1
                return original_members.fget(self)
            type(game.pack).members = property(counting_members)

            collide = actions.Collide(targets=game.pack)
            after_construction = calls[0]
            for _ in range(50):
                collide.run_one(shot)
            check("Collide.run_one() never touches Family.members after construction",
                  calls[0] == after_construction)
        finally:
            type(game.pack).members = original_members
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Zero-allocation acceptance: Move.run(pool) over 60 sprites, 1000 ticks.
# ---------------------------------------------------------------------------

def test_move_bulk_run_allocates_nothing_over_60_sprites_1000_ticks():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=60)
            for i in range(60):
                scene.pool.spawn(i, i % 50)

        game = _build_scene(build)
        move = actions.Move(speed_x=0.5, speed_y=-0.25)

        for _ in range(50):
            move.run(game.pool)  # warm-up

        mem_free = _mem_free()
        if mem_free is None:
            print("SKIP allocation assertion (no gc.mem_free() on this "
                  "interpreter -- this is CPython, not MicroPython)")
            for _ in range(1000):
                move.run(game.pool)
            check("functional readback (no-mem_free path)", len(game.pool) == 60)
            return

        gc.collect()
        before = gc.mem_free()
        for _ in range(1000):
            move.run(game.pool)
        gc.collect()
        after = gc.mem_free()
        allowance = 512
        delta = before - after
        print("Move.run(pool) over 60 sprites x 1000 ticks: before=%d after=%d delta=%d bytes"
              % (before, after, delta))
        check("Move.run(pool) over 60 sprites x 1000 ticks allocates ~0 bytes "
              "(delta=%d, allowance=%d)" % (delta, allowance), delta <= allowance)
    finally:
        _teardown()


def test_collide_against_family_allocates_nothing_per_tick():
    _setup()
    try:
        def build(scene):
            scene.hud = scene.layer("hud", projection=vs2.HUD)
            scene.shots = scene.hud.sprite_pool("ship.png", count=1)
            scene.pool_a = scene.hud.sprite_pool("ship.png", count=8)
            scene.pool_b = scene.hud.sprite_pool("ship.png", count=8)
            scene.pack = scene.family(scene.pool_a, scene.pool_b)

        game = _build_scene(build)
        shot = game.shots.spawn(10, 10)
        for i in range(8):
            game.pool_a.spawn(200 + i * 5, 10)
        for i in range(8):
            game.pool_b.spawn(200 + i * 5, 10)
        near = game.pool_b.spawn(11, 10)

        collide = actions.Collide(targets=game.pack)
        check("sanity: family target is actually found",
              collide.run_one(shot) is near)

        for _ in range(20):
            collide.run_one(shot)  # warm-up

        mem_free = _mem_free()
        if mem_free is None:
            print("SKIP allocation assertion (no gc.mem_free())")
            for _ in range(1000):
                collide.run_one(shot)
            return

        gc.collect()
        before = gc.mem_free()
        for _ in range(1000):
            collide.run_one(shot)
        gc.collect()
        after = gc.mem_free()
        allowance = 512
        delta = before - after
        print("Collide against a Family x 1000 run_one() calls: delta=%d bytes" % (delta,))
        check("Collide against a Family allocates ~0 bytes per tick "
              "(delta=%d, allowance=%d)" % (delta, allowance), delta <= allowance)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Dispatch-cost benchmark, kept as a regression guard: column-wise
# action.run(pool) must be at or under a hand-written inline loop doing the
# same work, and per-sprite run_one() dispatch must be measurably slower, in
# the same direction as the proposal's own MicroPython measurements. Printed
# on every interpreter; hard-asserted only on MicroPython, the deployment
# target -- see tests/test_vs2_params.py's identical convention for why a
# CPython threshold here would be measuring the wrong interpreter's cost
# model instead of a real regression.
# ---------------------------------------------------------------------------

class _PlainMove:
    """A hand-written stand-in for ``Move`` with none of the Action layer's
    machinery -- no ``params`` descriptors, no ``field=``, no accel/Var
    bookkeeping -- just the exact worked example from the proposal's own
    ``Move.run()``, so the comparison below is apples-to-apples: it re-reads
    ``pool._live`` fresh every call (never a cached reference from outside
    the timed loop, which would flatter the baseline and unfairly cost
    ``Move.run(sprites)`` the very ``sprites._live`` lookup it necessarily
    repeats on every call since ``sprites`` arrives as a fresh argument),
    and it reads its speed off plain instance attributes the same way
    ``Move`` reads them off params-declared ones (already shown by
    ``tests/test_vs2_params.py`` to cost the same as a plain attribute once
    shadowed)."""

    def __init__(self, speed_x, speed_y):
        self.speed_x = speed_x
        self.speed_y = speed_y

    def apply(self, pool):
        dx = self.speed_x
        dy = self.speed_y
        live = pool._live
        index = 0
        count = len(live)
        while index < count:
            sprite = live[index]
            sprite.dx += dx
            sprite.dy += dy
            index += 1


def test_column_wise_dispatch_cost_vs_hand_written_inline_and_per_sprite():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=60)
            for i in range(60):
                scene.pool.spawn(i, i % 50)

        game = _build_scene(build)
        move = actions.Move(speed_x=0.5, speed_y=-0.25)
        plain = _PlainMove(0.5, -0.25)
        live = game.pool._live
        ticks = 1000

        def bench_inline():
            start = utime.ticks_us()
            for _ in range(ticks):
                plain.apply(game.pool)
            return utime.ticks_diff(utime.ticks_us(), start)

        def bench_bulk():
            start = utime.ticks_us()
            for _ in range(ticks):
                move.run(game.pool)
            return utime.ticks_diff(utime.ticks_us(), start)

        def bench_per_sprite():
            start = utime.ticks_us()
            for _ in range(ticks):
                index = 0
                count = len(live)
                while index < count:
                    move.run_one(live[index])
                    index += 1
            return utime.ticks_diff(utime.ticks_us(), start)

        # Warm-up every path once before measuring.
        bench_inline()
        bench_bulk()
        bench_per_sprite()

        trials = 5
        inline_times = sorted(bench_inline() for _ in range(trials))
        bulk_times = sorted(bench_bulk() for _ in range(trials))
        per_sprite_times = sorted(bench_per_sprite() for _ in range(trials))
        inline_med = inline_times[trials // 2]
        bulk_med = bulk_times[trials // 2]
        per_sprite_med = per_sprite_times[trials // 2]

        print("inline trial times (us):", inline_times)
        print("bulk action.run(pool) trial times (us):", bulk_times)
        print("per-sprite run_one() dispatch trial times (us):", per_sprite_times)
        print("medians (us) -- inline: %d, bulk: %d (%.3fx inline), "
              "per_sprite: %d (%.3fx inline)"
              % (inline_med, bulk_med, bulk_med / float(inline_med),
                 per_sprite_med, per_sprite_med / float(inline_med)))

        if _is_micropython():
            check("column-wise action.run(pool) is at or under hand-written "
                  "inline (%.3fx, allowed <= 1.05x)" % (bulk_med / float(inline_med)),
                  bulk_med <= inline_med * 1.05)
            check("per-sprite run_one() dispatch is measurably slower than "
                  "inline (%.3fx, must exceed 1.05x)" % (per_sprite_med / float(inline_med)),
                  per_sprite_med > inline_med * 1.05)
        else:
            print("NOTE: dispatch-cost thresholds are only asserted on "
                  "MicroPython (the deployment target); CPython's numbers "
                  "are printed for visibility only, matching "
                  "test_vs2_params.py's own precedent for interpreter-"
                  "specific timing thresholds.")
    finally:
        _teardown()


TESTS = [
    test_move_accumulates_into_dx_dy_and_the_scene_commit_applies_it,
    test_move_composes_with_a_second_movement_action_on_one_pool,
    test_move_accel_updates_speed_once_per_run_call_not_per_sprite,
    test_move_rejects_var_bound_speed_combined_with_literal_accel,
    test_move_var_bound_speed_forces_the_per_sprite_path_and_reads_per_sprite,
    test_moveto_clamps_its_step_and_returns_done_on_arrival,
    test_moveto_wraps_the_shorter_way_around_the_circular_x_axis,
    test_moveto_bulk_run_hoists_and_matches_run_one,
    test_animate_loop_mode_cycles_and_wraps_forever,
    test_animate_ticks_holds_each_frame,
    test_animate_once_mode_holds_on_last_and_run_one_reports_done,
    test_animate_pingpong_mode_bounces_between_first_and_last,
    test_animate_field_writes_a_declared_instance_variable_not_frame,
    test_animate_rejects_var_bound_clock_parameters,
    test_animate_rejects_non_string_field,
    test_collide_box_on_hud_matches_sprite_overlaps_exactly,
    test_collide_against_a_single_sprite_target,
    test_collide_radius_does_a_circular_test_not_a_box_test,
    test_collide_cross_layer_target_is_an_error_naming_both_layers,
    test_collide_rejects_an_unsupported_target_type,
    test_collide_against_a_family_spanning_two_pools_and_a_sprite,
    test_collide_family_construction_reads_members_exactly_once,
    test_move_bulk_run_allocates_nothing_over_60_sprites_1000_ticks,
    test_collide_against_family_allocates_nothing_per_tick,
    test_column_wise_dispatch_cost_vs_hand_written_inline_and_per_sprite,
]


def main():
    for test in TESTS:
        print("--- %s ---" % test.__name__)
        test()
    print("ALL PASS: %d checks" % len(TESTS))


if __name__ == "__main__":
    main()
