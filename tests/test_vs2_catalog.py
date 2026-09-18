"""Tests for the VS2 Behavior catalog (``vs2/behaviors.py``'s "Attributes"
and "Movements" sections).

Spec: ``docs/vs2-behaviors-proposal.md``, ``## The catalog``. Work-breakdown
card: ``docs/vs2-behaviors-implementation.md`` T9 -- split into two parallel
agents that share no code: **T9a** (this file's "Attributes tests" section)
and **T9b** (Movements). Both write into this one file; see T9a's own
section banner below for how it is kept mergeable against T9b's
independently-written half.

Deliberately **not** unittest-based, matching ``tests/test_vs2_behaviors.py``
and ``tests/test_vs2_actions.py``'s precedent before it: this file needs a
real ``vs2`` scene (Layer, SpritePool, Sprite) to attach real catalog
Behaviors to, and writing it as a plain script means the allocation proofs
every catalog entry's acceptance bullet demands can be run for real on the
MicroPython unix port, not merely simulated under CPython::

    python3 tests/test_vs2_catalog.py
    micropython tests/test_vs2_catalog.py

Only the CPython run is wired into ``tests/run_tests.py`` (``CPYTHON_TESTS``),
matching T4's and T8's own precedent for keeping that shared file's diff
minimal -- the MicroPython run above is how the real allocation numbers in
T9a's report were produced.
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

from ventilastation import api_guard  # noqa: E402
from ventilastation.director import configure_runtime, director, reset_runtime, stripes  # noqa: E402

import vs2  # noqa: E402
from vs2.behaviors import (  # noqa: E402
    Animated,
    Behavior,
    Blinking,
    DespawnBeyond,
    Lifetime,
    Pinned,
    Recycling,
    Shaking,
    Transient,
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


def _check_zero_alloc(name, fn, ticks=1000, allowance=512):
    """Run ``fn()`` (one Step's worth of work) ``ticks`` times after a
    warm-up, asserting real ``gc.mem_free()`` on MicroPython does not drop
    by more than ``allowance`` bytes -- the shared allocation-proof idiom
    every catalog entry's acceptance bullet ("every entry ... allocates
    nothing per tick") is checked with. Skipped (with a note) under
    CPython, which has no ``gc.mem_free()``.
    """
    for _ in range(50):
        fn()  # warm-up any one-time caches
    mem_free = _mem_free()
    if mem_free is None:
        print("SKIP allocation assertion for %r (no gc.mem_free() on this "
              "interpreter -- this is CPython, not MicroPython)" % (name,))
        for _ in range(ticks):
            fn()
        return
    gc.collect()
    before = gc.mem_free()
    for _ in range(ticks):
        fn()
    gc.collect()
    after = gc.mem_free()
    delta = before - after
    print("%s over %d ticks: before=%d after=%d delta=%d bytes"
          % (name, ticks, before, after, delta))
    check("%s allocates ~0 bytes (delta=%d, allowance=%d)"
          % (name, delta, allowance), delta <= allowance)


# ---------------------------------------------------------------------------
# Scene/pool scaffolding, mirroring tests/test_vs2_behaviors.py's setUp/
# tearDown. Two images: "ship.png" (4 frames, the generic stand-in used by
# every other vs2 test file) and "explosion.png" (3 frames, so Transient's
# animate=True and Animated's bank/frames tests have more than one real
# frame to step through).
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
    stripes["explosion.png"] = 1
    runtime.platform.sprites.stripes[1] = {
        "width": 4, "height": 4, "frames": 3, "palette": 0,
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


# =============================================================================
# --- Attributes tests (T9a) ---
#
# Covers the eight Attributes vs2/behaviors.py's "--- Attributes ---" section
# builds: Transient, Animated, DespawnBeyond, Recycling, Lifetime, Blinking,
# Pinned, Shaking. Carried, Flashing and Cycling are not tested here because
# they are not built -- see that section's own module docstring (they "wait
# on named palette colours", a mechanism no task in the implementation plan
# builds).
#
# T9b's Movements tests (a sibling, concurrent task building the same
# catalog file's "### Movements" section) belong in their own similarly
# banner-delimited block elsewhere in this file -- this section does not
# touch or depend on anything T9b owns, so the two merge as two independent
# insertions.
# =============================================================================

# --- Transient ---------------------------------------------------------

def test_transient_despawns_after_ticks_and_calls_on_end():
    _setup()
    try:
        ended = []

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.explosions = scene.world.sprite_pool("ship.png", count=2)
            scene.explosions.behave(
                Transient(ticks=3, on_end=lambda sprite: ended.append(sprite)))
            scene.explosions.spawn(5, 5)

        game = _build_scene(build)
        behavior = game.explosions.behavior(Transient)
        sprite = game.explosions._live[0]
        for i in range(2):
            behavior.step(game.explosions)
            check("still alive before ticks elapse (step %d)" % i,
                  len(game.explosions) == 1)
        behavior.step(game.explosions)
        check("despawned exactly on the tick ticks elapsed",
              len(game.explosions) == 0)
        check("on_end fired with the sprite", ended == [sprite])
    finally:
        _teardown()


def test_transient_animates_frames_across_its_lifetime():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.explosions = scene.world.sprite_pool("explosion.png", count=1)
            scene.explosions.behave(Transient(animate=True, ticks=3))
            scene.explosions.spawn(5, 5)

        game = _build_scene(build)
        behavior = game.explosions.behavior(Transient)
        sprite = game.explosions._live[0]
        seen = []
        for _ in range(3):
            if len(game.explosions):
                seen.append(sprite.frame)
            behavior.step(game.explosions)
        check("explosion.png (3 frames) swept 0, 1, 2 over its 3-tick life",
              seen == [0, 1, 2])
        check("despawned once its lifetime elapsed", len(game.explosions) == 0)
    finally:
        _teardown()


def test_transient_plays_a_sound_on_expiry():
    _setup()
    try:
        played = []

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.explosions = scene.world.sprite_pool("ship.png", count=1)
            scene.explosions.behave(Transient(ticks=1, sound="boom"))
            scene.explosions.spawn(0, 0)

        game = _build_scene(build)
        original_sound_play = director.sound_play
        director.sound_play = lambda name: played.append(name)
        try:
            game.explosions.behavior(Transient).step(game.explosions)
        finally:
            director.sound_play = original_sound_play
        check("sound played once, on expiry", len(played) == 1)
        check("the qualified sound name ends with 'boom'",
              played[0].endswith("boom"))
    finally:
        _teardown()


def test_transient_allocates_nothing_over_many_ticks():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            # A large ticks= and RECYCLE keep the pool populated with live
            # sprites across the whole run without ever going empty.
            scene.explosions = scene.world.sprite_pool(
                "explosion.png", count=6, on_empty=vs2.RECYCLE)
            scene.explosions.behave(Transient(animate=True, ticks=10_000_000))
            for i in range(6):
                scene.explosions.spawn(i, i)

        game = _build_scene(build)
        behavior = game.explosions.behavior(Transient)
        _check_zero_alloc("Transient.step over 6 sprites",
                           lambda: behavior.step(game.explosions))
    finally:
        _teardown()


# --- Lifetime ------------------------------------------------------------

def test_lifetime_despawns_after_ticks_and_calls_on_expire():
    _setup()
    try:
        expired = []

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pickups = scene.world.sprite_pool("ship.png", count=1)
            scene.pickups.behave(
                Lifetime(ticks=2, on_expire=lambda sprite: expired.append(sprite)))
            scene.pickups.spawn(0, 0)

        game = _build_scene(build)
        behavior = game.pickups.behavior(Lifetime)
        sprite = game.pickups._live[0]
        behavior.step(game.pickups)
        check("still alive after 1 of 2 ticks", len(game.pickups) == 1)
        behavior.step(game.pickups)
        check("despawned exactly on tick 2", len(game.pickups) == 0)
        check("on_expire fired with the sprite", expired == [sprite])
    finally:
        _teardown()


def test_lifetime_on_a_lone_sprite_uses_step_one_and_hides_not_despawns():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.marker = scene.world.sprite("ship.png")
            scene.marker.behave(Lifetime(ticks=1))

        game = _build_scene(build)
        behavior = game.marker.behavior(Lifetime)
        check("visible before it expires", game.marker.visible)
        behavior.step_one(game.marker)
        check("a lone (non-pool) sprite is hidden, not despawned "
              "(despawn() would raise ValueError there)",
              game.marker.visible is False)
    finally:
        _teardown()


def test_lifetime_allocates_nothing_over_many_ticks():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pickups = scene.world.sprite_pool(
                "ship.png", count=6, on_empty=vs2.RECYCLE)
            scene.pickups.behave(Lifetime(ticks=10_000_000))
            for i in range(6):
                scene.pickups.spawn(i, i)

        game = _build_scene(build)
        behavior = game.pickups.behavior(Lifetime)
        _check_zero_alloc("Lifetime.step over 6 sprites",
                           lambda: behavior.step(game.pickups))
    finally:
        _teardown()


# --- DespawnBeyond ---------------------------------------------------------

def test_despawn_beyond_retires_a_sprite_past_its_bound_and_calls_on_leave():
    _setup()
    try:
        left = []

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.shots = scene.world.sprite_pool("ship.png", count=2)
            scene.shots.behave(
                DespawnBeyond(y_min=0, on_leave=lambda sprite: left.append(sprite)))
            scene.shots.spawn(0, 5)
            scene.shots.spawn(0, -1)  # already past the bound

        game = _build_scene(build)
        behavior = game.shots.behavior(DespawnBeyond)
        behavior.step(game.shots)
        check("only the out-of-bounds sprite despawned", len(game.shots) == 1)
        check("the surviving sprite is the in-bounds one",
              game.shots._live[0].y == 5)
        check("on_leave fired once", len(left) == 1)
    finally:
        _teardown()


def test_despawn_beyond_requires_at_least_one_bound():
    _setup()
    try:
        check_raises("no bound at all is a construction-time error",
                      ValueError, lambda: DespawnBeyond())
    finally:
        _teardown()


def test_despawn_beyond_allocates_nothing_over_many_ticks():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.shots = scene.world.sprite_pool(
                "ship.png", count=6, on_empty=vs2.RECYCLE)
            scene.shots.behave(DespawnBeyond(y_min=-1000))  # never triggers
            for i in range(6):
                scene.shots.spawn(i, i)

        game = _build_scene(build)
        behavior = game.shots.behavior(DespawnBeyond)
        _check_zero_alloc("DespawnBeyond.step over 6 sprites",
                           lambda: behavior.step(game.shots))
    finally:
        _teardown()


# --- Recycling --------------------------------------------------------

def test_recycling_repositions_a_sprite_that_leaves_its_range():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.stars = scene.world.sprite_pool("ship.png", count=1)
            scene.stars.behave(Recycling(x_range=(10, 20), y_range=(10, 20)))
            scene.stars.spawn(0, 0)  # outside both ranges immediately

        game = _build_scene(build)
        behavior = game.stars.behavior(Recycling)
        sprite = game.stars._live[0]
        behavior.step(game.stars)
        check("never despawned -- Recycling keeps the sprite alive",
              len(game.stars) == 1)
        check("repositioned within x_range", 10 <= sprite.x <= 20)
        check("repositioned within y_range", 10 <= sprite.y <= 20)
        # Now sitting inside the box: another Step should leave it alone.
        before = (sprite.x, sprite.y)
        behavior.step(game.stars)
        check("left untouched once back inside the box",
              (sprite.x, sprite.y) == before)
    finally:
        _teardown()


def test_recycling_rejects_an_inverted_range():
    _setup()
    try:
        check_raises("min > max in x_range is a construction-time error",
                      ValueError, lambda: Recycling(x_range=(20, 10)))
    finally:
        _teardown()


def test_recycling_allocates_nothing_over_many_ticks():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.stars = scene.world.sprite_pool("ship.png", count=6)
            scene.stars.behave(Recycling(x_range=(0, 255), y_range=(0, 255)))
            for i in range(6):
                scene.stars.spawn(i, i)

        game = _build_scene(build)
        behavior = game.stars.behavior(Recycling)
        _check_zero_alloc("Recycling.step over 6 sprites",
                           lambda: behavior.step(game.stars))
    finally:
        _teardown()


# --- Blinking --------------------------------------------------------

def test_blinking_toggles_visible_and_stops_after_duration():
    _setup()
    try:
        ended = []

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite("ship.png")
            scene.ship.behave(Blinking(
                on_ticks=2, off_ticks=1, duration=5,
                on_end=lambda sprite: ended.append(sprite)))

        game = _build_scene(build)
        behavior = game.ship.behavior(Blinking)
        # on_ticks=2, off_ticks=1 -> cycle "on, on, off" repeating, read
        # right after each Step (so index i is the result of the (i+1)th
        # Step): on,on,off,on,on across the first duration=5 ticks, with
        # the 5th also forcing visible back on and firing on_end.
        results = []
        for _ in range(5):
            behavior.step_one(game.ship)
            results.append(game.ship.visible)
        check("on/off pattern across the first 5 ticks",
              results == [True, True, False, True, True])
        check("on_end fired exactly once", len(ended) == 1)
        # A further Step, past duration, is a no-op.
        behavior.step_one(game.ship)
        check("stays visible once finished", game.ship.visible is True)
        check("on_end does not fire again", len(ended) == 1)
    finally:
        _teardown()


def test_blinking_forever_when_duration_is_zero():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite("ship.png")
            scene.ship.behave(Blinking(on_ticks=1, off_ticks=1))  # duration=0

        game = _build_scene(build)
        behavior = game.ship.behavior(Blinking)
        for _ in range(200):
            behavior.step_one(game.ship)
        check("still toggling after 200 ticks (never 'finishes')",
              game.ship.behaviors[0] is not None)  # ran with no exception
    finally:
        _teardown()


def test_blinking_allocates_nothing_over_many_ticks():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.lights = scene.world.sprite_pool("ship.png", count=6)
            scene.lights.behave(Blinking(on_ticks=3, off_ticks=3))
            for i in range(6):
                scene.lights.spawn(i, i)

        game = _build_scene(build)
        behavior = game.lights.behavior(Blinking)
        _check_zero_alloc("Blinking.step over 6 sprites",
                           lambda: behavior.step(game.lights))
    finally:
        _teardown()


# --- Pinned ----------------------------------------------------------

def test_pinned_tracks_a_lone_sprite_target_plus_offset_every_tick():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.boss = scene.world.sprite("ship.png", x=50, y=60)
            scene.turret = scene.world.sprite("ship.png")
            scene.turret.behave(Pinned(to=scene.boss, offset_x=4, offset_y=-2))

        game = _build_scene(build)
        behavior = game.turret.behavior(Pinned)
        behavior.step_one(game.turret)
        check("x tracks target + offset_x", game.turret.x == 54)
        check("y tracks target + offset_y", game.turret.y == 58)
        game.boss.x = 100
        game.boss.y = 10
        behavior.step_one(game.turret)
        check("re-tracks after the target moves (x)", game.turret.x == 104)
        check("re-tracks after the target moves (y)", game.turret.y == 8)
    finally:
        _teardown()


def test_pinned_hoists_the_target_read_once_for_a_whole_pool():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.anchor = scene.world.sprite("ship.png", x=20, y=30)
            scene.drones = scene.world.sprite_pool("ship.png", count=3)
            scene.drones.behave(Pinned(to=scene.anchor, offset_x=1, offset_y=1))
            for i in range(3):
                scene.drones.spawn(i, i)

        game = _build_scene(build)
        behavior = game.drones.behavior(Pinned)
        behavior.step(game.drones)
        for sprite in game.drones._live:
            check("every pool sprite lands on the same anchor + offset",
                  (sprite.x, sprite.y) == (21, 31))
    finally:
        _teardown()


def test_pinned_requires_a_sprite_target():
    _setup()
    try:
        check_raises("to= must be a Sprite, not None or a pool",
                      TypeError, lambda: Pinned())
    finally:
        _teardown()


def test_pinned_allocates_nothing_over_many_ticks():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.anchor = scene.world.sprite("ship.png", x=20, y=30)
            scene.drones = scene.world.sprite_pool("ship.png", count=6)
            scene.drones.behave(Pinned(to=scene.anchor, offset_x=1, offset_y=1))
            for i in range(6):
                scene.drones.spawn(i, i)

        game = _build_scene(build)
        behavior = game.drones.behavior(Pinned)
        _check_zero_alloc("Pinned.step over 6 sprites",
                           lambda: behavior.step(game.drones))
    finally:
        _teardown()


# --- Shaking -----------------------------------------------------------

def test_shaking_returns_exactly_to_the_true_position_once_finished():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite("ship.png", x=100, y=50)
            scene.ship.behave(Shaking(amplitude_x=5, amplitude_y=5, ticks=8))

        game = _build_scene(build)
        behavior = game.ship.behavior(Shaking)
        true_x, true_y = game.ship.x, game.ship.y
        saw_displacement = False
        for _ in range(8):
            behavior.step_one(game.ship)
            game.ship.x += game.ship.dx
            game.ship.y += game.ship.dy
            game.ship.dx = 0
            game.ship.dy = 0
            if game.ship.x != true_x or game.ship.y != true_y:
                saw_displacement = True
        check("the sprite actually moved from the jitter at some point",
              saw_displacement)
        # Telescoping cancellation is exact in real arithmetic (each tick
        # undoes the previous tick's offset before applying a new one, and
        # the final tick cancels outright with no new offset), but eight
        # sequential float additions can leave a ~1e-14 residue -- an
        # epsilon, not an exact-equality check, is the correct assertion.
        check("x lands back within float epsilon of the un-shaken position",
              abs(game.ship.x - true_x) < 1e-9)
        check("y lands back within float epsilon of the un-shaken position",
              abs(game.ship.y - true_y) < 1e-9)
        # A further Step (past ticks=8) is a no-op: dx/dy stay untouched.
        behavior.step_one(game.ship)
        check("no further jitter once finished", game.ship.dx == 0)
        check("no further jitter once finished (y)", game.ship.dy == 0)
    finally:
        _teardown()


def test_shaking_composes_with_a_concurrent_dx_dy_write():
    """Shaking must add on top of another Behavior's dx/dy contribution
    the same tick, not fight it -- the whole reason it goes through the
    accumulator instead of writing x/y directly like Pinned/Recycling."""
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite_pool("ship.png", count=1)
            scene.ship.behave(Shaking(amplitude_x=3, amplitude_y=0, ticks=100))
            scene.ship.spawn(0, 0)

        game = _build_scene(build)
        behavior = game.ship.behavior(Shaking)
        sprite = game.ship._live[0]
        sprite.dx += 10  # stand-in for some other Behavior's own write
        behavior.step(game.ship)
        check("Shaking added its jitter on top of the existing dx, not "
              "instead of it", sprite.dx != 10)
        check("the pre-existing +10 contribution is still present",
              sprite.dx >= 10 - 3 and sprite.dx <= 10 + 3 + 1e-9)
    finally:
        _teardown()


def test_shaking_allocates_nothing_over_many_ticks():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ships = scene.world.sprite_pool(
                "ship.png", count=6, on_empty=vs2.RECYCLE)
            scene.ships.behave(
                Shaking(amplitude_x=3, amplitude_y=3, ticks=10_000_000))
            for i in range(6):
                scene.ships.spawn(i, i)

        game = _build_scene(build)
        behavior = game.ships.behavior(Shaking)
        _check_zero_alloc("Shaking.step over 6 sprites",
                           lambda: behavior.step(game.ships))
    finally:
        _teardown()


# --- Animated ----------------------------------------------------------

def test_animated_reproduces_an_explicit_frames_sequence_exactly():
    """The flagship acceptance check: a specific, non-obvious frames=
    tuple no first/last/mode combination could produce, reproduced
    tick-by-tick exactly."""
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("explosion.png", count=1)
            scene.enemies.behave(
                Animated(frames=(0, 0, 1, 0, 2, 2, 1), ticks=1))
            scene.enemies.spawn(0, 0)

        game = _build_scene(build)
        behavior = game.enemies.behavior(Animated)
        sprite = game.enemies._live[0]
        shown = []
        for _ in range(7):
            behavior.step(game.enemies)
            shown.append(sprite.frame)
        check("exact tick-by-tick frame sequence reproduced",
              shown == [0, 0, 1, 0, 2, 2, 1])
    finally:
        _teardown()


def test_animated_loops_first_to_last():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("explosion.png", count=1)
            scene.enemies.behave(Animated(first=0, last=2, ticks=1, mode="loop"))
            scene.enemies.spawn(0, 0)

        game = _build_scene(build)
        behavior = game.enemies.behavior(Animated)
        sprite = game.enemies._live[0]
        shown = []
        for _ in range(7):
            behavior.step(game.enemies)
            shown.append(sprite.frame)
        check("0,1,2 loops back to 0", shown == [0, 1, 2, 0, 1, 2, 0])
    finally:
        _teardown()


def test_animated_pingpong_bounces_between_first_and_last():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("explosion.png", count=1)
            scene.enemies.behave(
                Animated(first=0, last=2, ticks=1, mode="pingpong"))
            scene.enemies.spawn(0, 0)

        game = _build_scene(build)
        behavior = game.enemies.behavior(Animated)
        sprite = game.enemies._live[0]
        shown = []
        for _ in range(7):
            behavior.step(game.enemies)
            shown.append(sprite.frame)
        check("bounces 0,1,2,1,0,1,2 with no double-hold at either end",
              shown == [0, 1, 2, 1, 0, 1, 2])
    finally:
        _teardown()


def test_animated_once_holds_on_last_frame():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("explosion.png", count=1)
            scene.enemies.behave(Animated(first=0, last=2, ticks=1, mode="once"))
            scene.enemies.spawn(0, 0)

        game = _build_scene(build)
        behavior = game.enemies.behavior(Animated)
        sprite = game.enemies._live[0]
        shown = []
        for _ in range(5):
            behavior.step(game.enemies)
            shown.append(sprite.frame)
        check("plays through once then holds on the last frame",
              shown == [0, 1, 2, 2, 2])
    finally:
        _teardown()


def test_animated_bank_offsets_the_frame_index():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            # 6-frame strip: bank 0 is frames 0-2, bank 1 is frames 3-5.
            scene.enemies = scene.world.sprite_pool("wide.png", count=1)
            scene.enemies.behave(
                Animated(first=0, last=2, ticks=1, bank=1, bank_size=3))
            scene.enemies.spawn(0, 0)

        stripes["wide.png"] = 2
        director.platform.sprites.stripes[2] = {
            "width": 4, "height": 4, "frames": 6, "palette": 0,
        }
        game = _build_scene(build)
        behavior = game.enemies.behavior(Animated)
        sprite = game.enemies._live[0]
        shown = []
        for _ in range(3):
            behavior.step(game.enemies)
            shown.append(sprite.frame)
        check("bank=1, bank_size=3 offsets 0,1,2 to 3,4,5",
              shown == [3, 4, 5])
    finally:
        _teardown()


def test_animated_images_swaps_whole_image_handles():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=1)
            scene.enemies.behave(
                Animated(images=("ship.png", "explosion.png"), ticks=1))
            scene.enemies.spawn(0, 0)

        game = _build_scene(build)
        behavior = game.enemies.behavior(Animated)
        sprite = game.enemies._live[0]
        names = []
        for _ in range(4):
            behavior.step(game.enemies)
            names.append(sprite.image.name)
        check("alternates between the two named images",
              names == ["ship.png", "explosion.png",
                         "ship.png", "explosion.png"])
    finally:
        _teardown()


def test_animated_rejects_frames_and_images_together():
    check_raises(
        "frames= and images= are mutually exclusive",
        ValueError,
        lambda: Animated(frames=(0, 1), images=("ship.png", "explosion.png")))


def test_animated_rejects_bank_size_with_images():
    check_raises(
        "bank_size and images= together is a construction-time error",
        ValueError,
        lambda: Animated(images=("ship.png",), bank_size=3))


def test_animated_allocates_nothing_over_many_ticks():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("explosion.png", count=6)
            scene.enemies.behave(
                Animated(first=0, last=2, ticks=3, mode="pingpong"))
            for i in range(6):
                scene.enemies.spawn(i, i)

        game = _build_scene(build)
        behavior = game.enemies.behavior(Animated)
        _check_zero_alloc("Animated.step over 6 sprites",
                           lambda: behavior.step(game.enemies))
    finally:
        _teardown()


def test_animated_duration_gives_a_continuous_fractional_speed():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("explosion.png", count=1)
            # duration=4: the whole 3-entry sequence plays once over 4
            # ticks -- a non-integer-per-frame speed no ticks= could give.
            scene.enemies.behave(
                Animated(frames=(0, 1, 2), duration=4, mode="loop"))
            scene.enemies.spawn(0, 0)

        game = _build_scene(build)
        behavior = game.enemies.behavior(Animated)
        sprite = game.enemies._live[0]
        shown = []
        for _ in range(8):
            behavior.step(game.enemies)
            shown.append(sprite.frame)
        # step_per_tick = 1/4 -> a whole step consumed every 4th tick.
        check("fractional duration= advance lands where expected",
              shown == [0, 0, 0, 0, 1, 1, 1, 1])
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# A modest integration proof: all eight Attributes attached at once, across
# several sprites, allocate nothing over many Steps. The fuller "thirty
# attributes stays inside the Step budget" and "two absolute-position
# movements is a build-time error" acceptance bullets belong to the
# combined T9 (see docs/vs2-behaviors-implementation.md's T9 acceptance
# list) and are left to whoever merges this file with T9b's half.
# ---------------------------------------------------------------------------

def test_all_eight_attributes_together_allocate_nothing_over_many_steps():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.anchor = scene.world.sprite("ship.png", x=10, y=10)

            scene.transients = scene.world.sprite_pool(
                "explosion.png", count=4, on_empty=vs2.RECYCLE)
            scene.transients.behave(Transient(animate=True, ticks=10_000_000))
            for i in range(4):
                scene.transients.spawn(i, i)

            scene.timed = scene.world.sprite_pool(
                "ship.png", count=4, on_empty=vs2.RECYCLE)
            scene.timed.behave(Lifetime(ticks=10_000_000))
            for i in range(4):
                scene.timed.spawn(i, i)

            scene.bounded = scene.world.sprite_pool("ship.png", count=4)
            scene.bounded.behave(DespawnBeyond(y_min=-1000))
            for i in range(4):
                scene.bounded.spawn(i, i)

            scene.perpetual = scene.world.sprite_pool("ship.png", count=4)
            scene.perpetual.behave(Recycling(x_range=(0, 255), y_range=(0, 255)))
            for i in range(4):
                scene.perpetual.spawn(i, i)

            scene.lights = scene.world.sprite_pool("ship.png", count=4)
            scene.lights.behave(Blinking(on_ticks=3, off_ticks=3))
            for i in range(4):
                scene.lights.spawn(i, i)

            scene.followers = scene.world.sprite_pool("ship.png", count=4)
            scene.followers.behave(Pinned(to=scene.anchor, offset_x=1, offset_y=1))
            for i in range(4):
                scene.followers.spawn(i, i)

            scene.shaken = scene.world.sprite_pool(
                "ship.png", count=4, on_empty=vs2.RECYCLE)
            scene.shaken.behave(Shaking(amplitude_x=2, amplitude_y=2,
                                         ticks=10_000_000))
            for i in range(4):
                scene.shaken.spawn(i, i)

            scene.animating = scene.world.sprite_pool("explosion.png", count=4)
            scene.animating.behave(Animated(first=0, last=2, ticks=3))
            for i in range(4):
                scene.animating.spawn(i, i)

        game = _build_scene(build)
        for _ in range(50):
            game.scene_step()  # warm-up any one-time caches

        mem_free = _mem_free()
        if mem_free is None:
            print("SKIP allocation assertion (no gc.mem_free() on this "
                  "interpreter -- this is CPython, not MicroPython)")
            for _ in range(1000):
                game.scene_step()
            check("scene still steps cleanly (no-mem_free path)", True)
            return

        gc.collect()
        before = gc.mem_free()
        for _ in range(1000):
            game.scene_step()
        gc.collect()
        after = gc.mem_free()
        allowance = 1024
        delta = before - after
        print("all 8 Attributes, 32 sprites total, x 1000 Steps: "
              "before=%d after=%d delta=%d bytes" % (before, after, delta))
        check("all eight Attributes attached together allocate ~0 bytes "
              "(delta=%d, allowance=%d)" % (delta, allowance),
              delta <= allowance)
    finally:
        _teardown()


ATTRIBUTES_TESTS = [
    test_transient_despawns_after_ticks_and_calls_on_end,
    test_transient_animates_frames_across_its_lifetime,
    test_transient_plays_a_sound_on_expiry,
    test_transient_allocates_nothing_over_many_ticks,
    test_lifetime_despawns_after_ticks_and_calls_on_expire,
    test_lifetime_on_a_lone_sprite_uses_step_one_and_hides_not_despawns,
    test_lifetime_allocates_nothing_over_many_ticks,
    test_despawn_beyond_retires_a_sprite_past_its_bound_and_calls_on_leave,
    test_despawn_beyond_requires_at_least_one_bound,
    test_despawn_beyond_allocates_nothing_over_many_ticks,
    test_recycling_repositions_a_sprite_that_leaves_its_range,
    test_recycling_rejects_an_inverted_range,
    test_recycling_allocates_nothing_over_many_ticks,
    test_blinking_toggles_visible_and_stops_after_duration,
    test_blinking_forever_when_duration_is_zero,
    test_blinking_allocates_nothing_over_many_ticks,
    test_pinned_tracks_a_lone_sprite_target_plus_offset_every_tick,
    test_pinned_hoists_the_target_read_once_for_a_whole_pool,
    test_pinned_requires_a_sprite_target,
    test_pinned_allocates_nothing_over_many_ticks,
    test_shaking_returns_exactly_to_the_true_position_once_finished,
    test_shaking_composes_with_a_concurrent_dx_dy_write,
    test_shaking_allocates_nothing_over_many_ticks,
    test_animated_reproduces_an_explicit_frames_sequence_exactly,
    test_animated_loops_first_to_last,
    test_animated_pingpong_bounces_between_first_and_last,
    test_animated_once_holds_on_last_frame,
    test_animated_bank_offsets_the_frame_index,
    test_animated_images_swaps_whole_image_handles,
    test_animated_rejects_frames_and_images_together,
    test_animated_rejects_bank_size_with_images,
    test_animated_allocates_nothing_over_many_ticks,
    test_animated_duration_gives_a_continuous_fractional_speed,
    test_all_eight_attributes_together_allocate_nothing_over_many_steps,
]


# =============================================================================
# --- end of Attributes tests (T9a) ---
#
# T9b's Movements tests are expected to define their own MOVEMENTS_TESTS
# list the same way, immediately below this banner; TESTS below concatenates
# both (or just this one, until T9b's half lands).
# =============================================================================

TESTS = list(ATTRIBUTES_TESTS)


def main():
    for test in TESTS:
        print("--- %s ---" % test.__name__)
        test()
    print("ALL PASS: %d checks" % len(TESTS))


if __name__ == "__main__":
    main()
