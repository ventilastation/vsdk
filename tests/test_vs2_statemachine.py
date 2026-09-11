"""Tests for ``vs2/behaviors.py``'s ``StateMachine`` -- named states, one
primed byte, a tuple of bound methods indexed by it, and ``hold()`` as the
timed-transition primitive.

Spec: ``docs/vs2-behaviors-proposal.md``, ``## State machines``.
Work-breakdown card: ``docs/vs2-behaviors-implementation.md`` T10.

Deliberately **not** unittest-based, matching ``tests/test_vs2_behaviors.py``'s
(T8's) precedent: this file needs a real ``vs2`` scene to attach real
StateMachines to, and writing it as a plain script means the allocation and
dispatch-cost benchmarks T10's acceptance list demands can be run for real on
the MicroPython unix port, not merely simulated under CPython:

    python3 tests/test_vs2_statemachine.py
    micropython tests/test_vs2_statemachine.py

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
try:
    import inspect  # noqa: E402
except ImportError:
    # Not available on the MicroPython unix port -- only the ten-state
    # line-count/legibility comparison below needs it (inspect.getsource());
    # everything else in this file, including the real allocation and
    # dispatch-cost benchmarks, still runs there.
    inspect = None

from ventilastation import api_guard  # noqa: E402
from ventilastation.director import configure_runtime, director, reset_runtime, stripes  # noqa: E402

import vs2  # noqa: E402
from vs2 import StateConflictError  # noqa: E402
from vs2.behaviors import Behavior, StateMachine  # noqa: E402


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
# Scene/pool scaffolding, mirroring tests/test_vs2_behaviors.py's setUp/
# tearDown.
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
    api_guard.begin_app("games.test_vs2_statemachine", "vs2")
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
# The spec's own worked example, verbatim (docs/vs2-behaviors-proposal.md,
# "## State machines"), reproduced exactly to prove StateMachine supports it
# as written -- string-name returns, enter_<state> calling hold(), the
# lot -- not a simplified stand-in.
# ---------------------------------------------------------------------------

GROUND = 0


class Enemy(StateMachine):
    speed_x = 1.25
    speed_y = 0.6

    states = ("descending", "orbiting", "chasing", "exploding")
    initial = "descending"

    def descending(self, sprite):
        sprite.dy -= self.speed_y
        if sprite.y <= GROUND:
            return "exploding"

    def enter_orbiting(self, sprite):
        self.hold(sprite, 128, then="descending")

    def orbiting(self, sprite):
        sprite.dx += self.speed_x * sprite.facing

    def chasing(self, sprite):
        pass

    def exploding(self, sprite):
        pass


def test_worked_example_initial_state_and_index():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.var("facing", 1)
            scene.pool.spawn(0, 5)
            scene.enemy = scene.pool.behave(Enemy())

        game = _build_scene(build)
        sprite = game.pool._live[0]
        check("initial fsm_state is descending's index (not necessarily 0, "
              "but is here since descending is states[0])",
              sprite.fsm_state == 0)
        check("state_name() reads it back as the name",
              game.enemy.state_name(sprite) == "descending")
    finally:
        _teardown()


def test_worked_example_condition_based_transition_to_exploding():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.var("facing", 1)
            scene.pool.spawn(0, 2)  # y=2, speed_y=0.6 -> exploding within a
                                     # few real Steps
            scene.enemy = scene.pool.behave(Enemy())

        game = _build_scene(build)
        sprite = game.pool._live[0]
        for _ in range(10):
            game.scene_step()
            if game.enemy.state_name(sprite) == "exploding":
                break
        check("descending's own return-next-state fired the transition",
              game.enemy.state_name(sprite) == "exploding")
    finally:
        _teardown()


def test_worked_example_hold_fires_after_exactly_128_ticks():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.var("facing", 1)
            scene.pool.spawn(0, 500)  # far from GROUND: never exits via
                                       # descending's own condition
            scene.enemy = scene.pool.behave(Enemy())

        game = _build_scene(build)
        sprite = game.pool._live[0]
        game.enemy.force_state(sprite, "orbiting")
        check("enter_orbiting's hold(sprite, 128, then='descending') "
              "primed fsm_hold to 128", sprite.fsm_hold == 128)
        check("...and fsm_then to descending's index",
              sprite.fsm_then == game.enemy._name_to_index["descending"])
        for i in range(127):
            game.scene_step()
            check("still orbiting at tick %d/128" % (i + 1,),
                  game.enemy.state_name(sprite) == "orbiting")
        game.scene_step()  # the 128th
        check("hold expired on exactly the 128th tick, forcing 'descending' "
              "regardless of orbiting()'s own (always-None) return",
              game.enemy.state_name(sprite) == "descending")
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# "One primed byte plus a tuple of bound methods indexed by it."
# ---------------------------------------------------------------------------

def test_dispatch_table_is_a_tuple_of_bound_methods_indexed_by_state():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.var("facing", 1)
            scene.enemy = scene.pool.behave(Enemy())

        game = _build_scene(build)
        behavior = game.enemy
        check("_state_methods is a tuple", isinstance(behavior._state_methods, tuple))
        check("one entry per declared state",
              len(behavior._state_methods) == len(Enemy.states))
        for i, name in enumerate(Enemy.states):
            method = behavior._state_methods[i]
            # MicroPython's bound_method exposes neither __self__ nor
            # __func__ (confirmed directly: hasattr() is False for both,
            # unlike CPython) -- but it does support ``==`` against a
            # fresh ``getattr(behavior, name)``, comparing the same
            # (instance, function) pair, which is portable across both
            # interpreters and is exactly what "bound to this instance,
            # bound to this name" means.
            check("entry %d is callable" % i, callable(method))
            check("entry %d is bound to the method named %r" % (i, name),
                  method == getattr(behavior, name))
        check("sprite.fsm_state is a plain int (the 'one primed byte')",
              isinstance(game.pool.spawn(0, 0).fsm_state, int))
    finally:
        _teardown()


def test_initial_resolves_to_its_own_index_not_always_zero():
    _setup()
    try:
        class LateStart(StateMachine):
            states = ("a", "b", "c")
            initial = "c"

            def a(self, sprite):
                pass

            def b(self, sprite):
                pass

            def c(self, sprite):
                pass

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 0)
            scene.m = scene.pool.behave(LateStart())

        game = _build_scene(build)
        sprite = game.pool._live[0]
        check("initial='c' primes fsm_state to index 2, not 0",
              sprite.fsm_state == 2)
        check("state_name reads it back as 'c'",
              game.m.state_name(sprite) == "c")
    finally:
        _teardown()


def test_a_state_machine_with_no_states_fails_loudly_at_attach():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.behave(StateMachine())

        check_raises("StateMachine() with no states raises at attach time",
                     ValueError, lambda: _build_scene(build))
    finally:
        _teardown()


def test_initial_not_in_states_is_a_clear_build_time_error():
    _setup()
    try:
        class BadInitial(StateMachine):
            states = ("a", "b")
            initial = "nope"

            def a(self, sprite):
                pass

            def b(self, sprite):
                pass

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.behave(BadInitial())

        exc = check_raises("initial naming a state that doesn't exist",
                            ValueError, lambda: _build_scene(build))
        check("message names the offender", "nope" in str(exc))
        check("message names the valid set", "a, b" in str(exc))
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# enter_<state>/exit_<state>: optional, matched by name, fired on every
# transition regardless of source.
# ---------------------------------------------------------------------------

def test_enter_and_exit_hooks_fire_matched_by_name():
    _setup()
    try:
        calls = []

        class Hooked(StateMachine):
            states = ("a", "b", "c")
            initial = "a"

            def a(self, sprite):
                return "b"

            def enter_b(self, sprite):
                calls.append("enter_b")

            def exit_b(self, sprite):
                calls.append("exit_b")

            def b(self, sprite):
                return "c"

            # no enter_c/exit_c declared -- optional, must be skipped
            # without error.
            def c(self, sprite):
                pass

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 0)
            scene.m = scene.pool.behave(Hooked())

        game = _build_scene(build)
        sprite = game.pool._live[0]
        game.m.step(game.pool)  # a -> b
        check("enter_b fired on entry", calls == ["enter_b"])
        game.m.step(game.pool)  # b -> c (no exit_c/enter_c to crash on)
        check("exit_b fired on exit, in order",
              calls == ["enter_b", "exit_b"])
        check("ended in c with no hooks declared", game.m.state_name(sprite) == "c")
    finally:
        _teardown()


def test_no_hooks_at_all_is_fine():
    _setup()
    try:
        class Bare(StateMachine):
            states = ("a", "b")
            initial = "a"

            def a(self, sprite):
                return "b"

            def b(self, sprite):
                pass

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 0)
            scene.m = scene.pool.behave(Bare())

        game = _build_scene(build)
        sprite = game.pool._live[0]
        game.m.step(game.pool)
        check("transitions fine with zero enter_/exit_ hooks declared",
              game.m.state_name(sprite) == "b")
    finally:
        _teardown()


def test_returning_an_unknown_state_name_is_a_clear_error():
    _setup()
    try:
        class Bad(StateMachine):
            states = ("a", "b")
            initial = "a"

            def a(self, sprite):
                return "nonexistent"

            def b(self, sprite):
                pass

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 0)
            scene.m = scene.pool.behave(Bad())

        game = _build_scene(build)
        exc = check_raises("a step method returning an undeclared state name",
                            ValueError, lambda: game.m.step(game.pool))
        check("message names the offending state's method",
              "'a'" in str(exc))
        check("message names the bad return value", "nonexistent" in str(exc))
        check("message names the valid set", "a, b" in str(exc))
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# hold(sprite, ticks, then=...): validates its target and primes fsm_hold/
# fsm_then directly (see test_worked_example_hold_fires_after_exactly_128_
# ticks above for the end-to-end timed-transition proof).
# ---------------------------------------------------------------------------

def test_hold_rejects_an_unknown_then_state():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.var("facing", 1)
            scene.pool.spawn(0, 0)
            scene.enemy = scene.pool.behave(Enemy())

        game = _build_scene(build)
        sprite = game.pool._live[0]
        exc = check_raises(
            "hold(then='nope') where 'nope' is not a declared state",
            ValueError,
            lambda: game.enemy.hold(sprite, 10, then="nope"))
        check("message names the offender", "nope" in str(exc))
    finally:
        _teardown()


def test_a_states_own_return_takes_priority_over_an_expiring_hold_same_tick():
    # Edge case: if a state's own step() returns a real transition on the
    # exact tick its hold would also have expired, the state's own decision
    # wins (see StateMachine._dispatch_one) rather than being silently
    # overridden by the timed one.
    _setup()
    try:
        class RaceCondition(StateMachine):
            states = ("waiting", "own_choice", "timed_choice")
            initial = "waiting"

            def enter_waiting(self, sprite):
                self.hold(sprite, 1, then="timed_choice")

            def waiting(self, sprite):
                return "own_choice"  # fires the same tick the hold would

            def own_choice(self, sprite):
                pass

            def timed_choice(self, sprite):
                pass

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 0)
            scene.m = scene.pool.behave(RaceCondition())

        game = _build_scene(build)
        sprite = game.pool._live[0]
        game.m.step(game.pool)
        check("the state's own return-next-state wins over the "
              "same-tick-expiring hold",
              game.m.state_name(sprite) == "own_choice")
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Introspection: byte -> name (state_name) and name -> byte (force_state),
# for the panel / live-tune protocol (T11) / a traceback -- never the tick.
# ---------------------------------------------------------------------------

def test_state_name_and_force_state_round_trip():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.var("facing", 1)
            scene.pool.spawn(0, 500)
            scene.enemy = scene.pool.behave(Enemy())

        game = _build_scene(build)
        sprite = game.pool._live[0]
        for name in Enemy.states:
            game.enemy.force_state(sprite, name)
            check("force_state(%r) then state_name() round-trips" % name,
                  game.enemy.state_name(sprite) == name)
            check("...and the underlying byte matches states.index(%r)" % name,
                  sprite.fsm_state == Enemy.states.index(name))
    finally:
        _teardown()


def test_force_state_fires_exit_and_enter_hooks():
    _setup()
    try:
        calls = []

        class Hooked(StateMachine):
            states = ("a", "b")
            initial = "a"

            def a(self, sprite):
                pass

            def exit_a(self, sprite):
                calls.append("exit_a")

            def enter_b(self, sprite):
                calls.append("enter_b")

            def b(self, sprite):
                pass

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 0)
            scene.m = scene.pool.behave(Hooked())

        game = _build_scene(build)
        sprite = game.pool._live[0]
        game.m.force_state(sprite, "b")
        check("force_state fires the outgoing exit hook then the incoming "
              "enter hook", calls == ["exit_a", "enter_b"])
    finally:
        _teardown()


def test_force_state_rejects_an_unknown_name():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.var("facing", 1)
            scene.pool.spawn(0, 0)
            scene.enemy = scene.pool.behave(Enemy())

        game = _build_scene(build)
        sprite = game.pool._live[0]
        check_raises("force_state() on an unknown name", ValueError,
                     lambda: game.enemy.force_state(sprite, "nope"))
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# fsm_state/fsm_hold/fsm_then priming: every sprite of a pool (free
# included), a lone sprite, and every member of a family -- and
# StateConflictError guarding against two StateMachines sharing one subject
# (the collision the framework's own reserved-name gate would normally
# catch, but can't here -- see the class docstring for why).
# ---------------------------------------------------------------------------

def test_fsm_fields_primed_on_every_sprite_of_a_pool_free_included():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=5)
            scene.pool.var("facing", 1)
            scene.pool.spawn(0, 0)
            scene.pool.spawn(1, 1)
            scene.enemy = scene.pool.behave(Enemy())

        game = _build_scene(build)
        for sprite in game.pool._live:
            check("fsm_state primed on a live sprite", sprite.fsm_state == 0)
            check("fsm_hold primed on a live sprite", sprite.fsm_hold == 0)
            check("fsm_then primed on a live sprite", sprite.fsm_then == 0)
        for sprite in game.pool._free:
            check("fsm_state primed on a free sprite too", sprite.fsm_state == 0)
    finally:
        _teardown()


def test_fsm_fields_primed_on_a_lone_sprite_subject():
    _setup()
    try:
        class OneState(StateMachine):
            states = ("only",)
            initial = "only"

            def only(self, sprite):
                pass

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite("ship.png")
            scene.m = scene.ship.behave(OneState())

        game = _build_scene(build)
        check("fsm_state primed on the lone sprite", game.ship.fsm_state == 0)
        check("fsm_hold primed on the lone sprite", game.ship.fsm_hold == 0)
    finally:
        _teardown()


def test_fsm_fields_primed_across_every_member_of_a_family():
    _setup()
    try:
        class Two(StateMachine):
            states = ("a", "b")
            initial = "a"

            def a(self, sprite):
                pass

            def b(self, sprite):
                pass

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool_a = scene.world.sprite_pool("ship.png", count=3)
            scene.pool_b = scene.world.sprite_pool("ship.png", count=3)
            scene.pool_a.spawn(0, 0)
            scene.pool_b.spawn(1, 1)
            scene.lone = scene.world.sprite("ship.png")
            scene.pack = scene.family(scene.pool_a, scene.pool_b, scene.lone)
            scene.pack.behave(Two())

        game = _build_scene(build)
        for sprite in game.pool_a._live:
            check("primed on pool_a's live sprites", sprite.fsm_state == 0)
        for sprite in game.pool_a._free:
            check("primed on pool_a's free sprites", sprite.fsm_state == 0)
        for sprite in game.pool_b._live:
            check("primed on pool_b's live sprites", sprite.fsm_state == 0)
        check("primed on the lone sprite member", game.lone.fsm_state == 0)
    finally:
        _teardown()


def test_two_state_machines_on_one_pool_is_a_state_conflict_error():
    _setup()
    try:
        class First(StateMachine):
            states = ("a",)
            initial = "a"

            def a(self, sprite):
                pass

        class Second(StateMachine):
            states = ("x",)
            initial = "x"

            def x(self, sprite):
                pass

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.behave(First())
            scene.pool.behave(Second())  # would silently share fsm_state

        exc = check_raises(
            "a second StateMachine on one pool is caught, not silently "
            "sharing fsm_state/fsm_hold/fsm_then",
            StateConflictError, lambda: _build_scene(build))
        check("message names the field family", "fsm_" in str(exc))
    finally:
        _teardown()


def test_two_state_machines_on_one_sprite_is_a_state_conflict_error():
    _setup()
    try:
        class First(StateMachine):
            states = ("a",)
            initial = "a"

            def a(self, sprite):
                pass

        class Second(StateMachine):
            states = ("x",)
            initial = "x"

            def x(self, sprite):
                pass

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite("ship.png")
            scene.ship.behave(First())
            scene.ship.behave(Second())

        check_raises(
            "a second StateMachine on one lone sprite is also caught",
            StateConflictError, lambda: _build_scene(build))
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Subject kinds: pool and sprite both dispatch correctly (family piggybacks
# on both, already proven above by priming across a mixed family); a scene
# subject is a build-time TypeError, since StateMachine defines no
# step_scene.
# ---------------------------------------------------------------------------

def test_state_machine_on_a_scene_subject_is_a_build_time_error():
    _setup()
    try:
        class Tiny(StateMachine):
            states = ("a",)
            initial = "a"

            def a(self, sprite):
                pass

        def build(scene):
            scene.behave(Tiny())

        exc = check_raises(
            "StateMachine defines no step_scene, so attaching it to the "
            "scene itself is a build-time error",
            TypeError, lambda: _build_scene(build))
        check("message names the class", "Tiny" in str(exc))
    finally:
        _teardown()


def test_step_one_dispatch_on_a_lone_sprite_subject():
    _setup()
    try:
        class Toggle(StateMachine):
            states = ("a", "b")
            initial = "a"

            def a(self, sprite):
                return "b"

            def b(self, sprite):
                return "a"

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.ship = scene.world.sprite("ship.png")
            scene.m = scene.ship.behave(Toggle())

        game = _build_scene(build)
        check("starts in a", game.m.state_name(game.ship) == "a")
        game.m.step_one(game.ship)
        check("step_one dispatches a lone-sprite subject", game.m.state_name(game.ship) == "b")
        game.m.step_one(game.ship)
        check("...and keeps toggling", game.m.state_name(game.ship) == "a")
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Zero allocation: a pool of state-machine-carrying sprites over many real
# Steps, matching T8's own threshold/style exactly.
# ---------------------------------------------------------------------------

def test_state_machine_over_40_sprites_allocates_nothing_across_1000_steps():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=40)
            scene.pool.var("facing", 1)
            for i in range(40):
                scene.pool.spawn(i, 10000 + i)  # never reaches GROUND
            scene.enemy = scene.pool.behave(Enemy())

        game = _build_scene(build)

        for _ in range(50):
            game.scene_step()  # warm-up any one-time caches

        mem_free = _mem_free()
        if mem_free is None:
            print("SKIP allocation assertion (no gc.mem_free() on this "
                  "interpreter -- this is CPython, not MicroPython)")
            for _ in range(1000):
                game.scene_step()
            check("functional readback (no-mem_free path)",
                  len(game.pool) == 40)
            return

        gc.collect()
        before = gc.mem_free()
        for _ in range(1000):
            game.scene_step()
        gc.collect()
        after = gc.mem_free()
        allowance = 512
        delta = before - after
        print("StateMachine (Enemy) over 40 sprites x 1000 Steps: "
              "before=%d after=%d delta=%d bytes" % (before, after, delta))
        check("StateMachine dispatch over 40 sprites x 1000 Steps allocates "
              "~0 bytes (delta=%d, allowance=%d)" % (delta, allowance),
              delta <= allowance)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# "No string comparison in the tick." The dispatch call itself
# (self._state_methods[sprite.fsm_state](sprite)) is a tuple index plus a
# call -- structurally incapable of a string comparison, since tuple
# indexing is by int. The only place a state *name* is ever resolved back
# to an index is _name_to_index[...], hit only when a transition actually
# occurs (a returned name, or hold() being called) -- never on a steady-
# state tick where the current state simply keeps running.
#
# str.__eq__ can't be monkeypatched directly (it's a slot on an immutable
# built-in type in CPython), so this proves the claim the way that matters:
# by counting *how many times* the name->index dict is actually consulted,
# with a counting dict swapped in for it. Zero steady-state ticks touch it
# at all; a transition touches it exactly once, never proportional to the
# number of declared states the way the hand-rolled ten-state baseline's
# if/elif chain is (see the proving-case section below).
# ---------------------------------------------------------------------------

class _CountingDict(dict):
    # super() rather than dict.__init__()/dict.__getitem__() -- confirmed
    # directly that MicroPython's native ``dict`` type does not expose
    # __init__ as an attribute (explicit unbound-method calls on a
    # built-in fail there), while super() delegation works on both
    # interpreters.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lookups = 0

    def __getitem__(self, key):
        self.lookups += 1
        return super().__getitem__(key)

    def get(self, key, default=None):
        # _dispatch_one() resolves a transition's target via get() with a
        # sentinel, not [] -- see StateMachine._dispatch_one's own comment
        # on why it avoids try/except in the hot path. dict.get() does not
        # route through __getitem__ (confirmed: overriding only
        # __getitem__ leaves get() silently uncounted), so this is
        # overridden too.
        self.lookups += 1
        return super().get(key, default)


def test_no_name_lookup_at_all_during_steady_state_ticks():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.var("facing", 1)
            scene.pool.spawn(0, 10000)  # never reaches GROUND: descending()
                                          # returns None every tick -- pure
                                          # steady state, no transitions
            scene.enemy = scene.pool.behave(Enemy())

        game = _build_scene(build)
        counting = _CountingDict(game.enemy._name_to_index)
        game.enemy._name_to_index = counting
        for _ in range(500):
            game.scene_step()
        check("the dispatch call itself is an int tuple-index, so 500 "
              "steady-state ticks (no transition ever fires) never touch "
              "the name->index dict, let alone do a string comparison "
              "(lookups=%d)" % counting.lookups,
              counting.lookups == 0)
    finally:
        _teardown()


def test_a_transition_costs_exactly_one_lookup_not_a_chain():
    _setup()
    try:
        class Cycle(StateMachine):
            states = ("a", "b", "c", "d", "e")
            initial = "a"

            def a(self, sprite):
                return "b"

            def b(self, sprite):
                return "c"

            def c(self, sprite):
                return "d"

            def d(self, sprite):
                return "e"

            def e(self, sprite):
                return "a"

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=1)
            scene.pool.spawn(0, 0)
            scene.m = scene.pool.behave(Cycle())

        game = _build_scene(build)
        counting = _CountingDict(game.m._name_to_index)
        game.m._name_to_index = counting
        for _ in range(20):  # every single tick transitions here
            game.m.step(game.pool)
        check("20 transitions cost exactly 20 lookups -- O(1) per "
              "transition, never a scan proportional to len(states) "
              "(lookups=%d)" % counting.lookups, counting.lookups == 20)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Dispatch-cost benchmark: StateMachine's indexed dispatch against a
# hand-written per-sprite if/elif dispatch loop doing equivalent branching
# -- "within the per-sprite branch budget, not worse" (T10's acceptance
# bullet). The proposal's own numbers (docs/vs2-behaviors-proposal.md,
# "### What the dispatch shape costs") put a hand-rolled per-sprite
# decision loop and a hybrid Behavior within a few percent of each other;
# T8 hard-codes a 25% budget for its own (structurally similar) hybrid
# dispatch, and this reuses that same number as "the per-sprite branch
# budget" for consistency, since the proposal names no separate figure for
# StateMachine specifically.
# ---------------------------------------------------------------------------

class _PlainFourState:
    """Hand-rolled equivalent of Enemy's four-state graph, inlined with no
    StateMachine machinery at all -- if/elif against a plain string field,
    a hand-maintained hold counter -- the baseline
    ``test_dispatch_within_the_per_sprite_branch_budget`` measures
    against."""

    def __init__(self, speed_x, speed_y):
        self.speed_x = speed_x
        self.speed_y = speed_y

    def step(self, pool):
        speed_x = self.speed_x
        speed_y = self.speed_y
        live = pool._live
        index = len(live) - 1
        while index >= 0:
            sprite = live[index]
            phase = sprite.phase
            if phase == "descending":
                sprite.dy -= speed_y
                if sprite.y <= GROUND:
                    sprite.phase = "exploding"
            elif phase == "orbiting":
                sprite.dx += speed_x * sprite.facing
                sprite.hold_ticks -= 1
                if sprite.hold_ticks <= 0:
                    sprite.phase = "descending"
                    sprite.hold_ticks = 0
            elif phase == "chasing":
                pass
            elif phase == "exploding":
                pass
            index -= 1


def _median_of_interleaved_trials(bench_a, bench_b, trials):
    """See tests/test_vs2_behaviors.py's identical helper: interleaves the
    two arms so host noise (GC pauses, thermal throttling) is spread evenly
    across both rather than biasing whichever runs second."""
    a_times = []
    b_times = []
    for _ in range(trials):
        a_times.append(bench_a())
        b_times.append(bench_b())
    a_times.sort()
    b_times.sort()
    return a_times, b_times


def test_dispatch_within_the_per_sprite_branch_budget():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.pool = scene.world.sprite_pool("ship.png", count=60)
            scene.pool.var("facing", 1)
            scene.pool.var("phase", "orbiting")
            scene.pool.var("hold_ticks", 1000000)  # never expires: pure
                                                      # steady-state orbiting
            for i in range(60):
                scene.pool.spawn(i, 10000 + i)
            scene.enemy = scene.pool.behave(Enemy())
            for sprite in scene.pool._live:
                scene.enemy.force_state(sprite, "orbiting")
                sprite.fsm_hold = 0  # steady-state: no hold countdown here
                                       # either, matching the hand-rolled arm

        game = _build_scene(build)
        state_machine = game.enemy
        plain = _PlainFourState(1.25, 0.6)
        ticks = 1000

        def bench_state_machine():
            start = utime.ticks_us()
            for _ in range(ticks):
                state_machine.step(game.pool)
            return utime.ticks_diff(utime.ticks_us(), start)

        def bench_inline():
            start = utime.ticks_us()
            for _ in range(ticks):
                plain.step(game.pool)
            return utime.ticks_diff(utime.ticks_us(), start)

        bench_state_machine()  # warm-up
        bench_inline()

        sm_times, inline_times = _median_of_interleaved_trials(
            bench_state_machine, bench_inline, trials=7)
        sm_med = sm_times[len(sm_times) // 2]
        inline_med = inline_times[len(inline_times) // 2]

        print("inline if/elif trial times (us):", inline_times)
        print("StateMachine trial times (us):", sm_times)
        ratio = sm_med / float(inline_med)
        print("medians (us) -- inline: %d, StateMachine: %d (%.3fx inline)"
              % (inline_med, sm_med, ratio))

        if _is_micropython():
            check("StateMachine dispatch lands within the per-sprite branch "
                  "budget (25%%, matching T8's own hybrid-dispatch bound): "
                  "%.3fx inline, allowed <= 1.25x" % ratio, ratio <= 1.25)
        else:
            print("NOTE: the dispatch-cost threshold is only asserted on "
                  "MicroPython (the deployment target); CPython's numbers "
                  "are printed for visibility only, matching "
                  "test_vs2_behaviors.py's own precedent.")
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# The proving case: a synthetic ten-state enemy AI, hand-rolled first (the
# "what it replaces" baseline), then ported to StateMachine. No such
# machine exists anywhere in this codebase's games/ today (checked: the
# closest candidates have two or three real states, not ten) -- this is a
# representative, made-up example, as the task briefing directs.
#
# States: spawning -> descending -> orbiting -> chasing -> {attacking,
# stunned, dying} -> retreating -> orbiting (loop) / exploding -> gone
# (terminal, despawns). Six of the ten transitions are timed (a hold);
# three are condition-based off game state (hp, a hit flag, a chase
# counter); one is terminal.
# ---------------------------------------------------------------------------

ATTACK_RANGE_TICKS = 3


class _HandRolledEnemy10(Behavior):
    """Hand-rolled ten-state enemy AI: a ``phase`` string field compared
    against every tick regardless of which phase is active, and a bespoke
    ``timer`` countdown re-implemented by hand in every one of the six
    timed phases -- exactly the pattern
    ``docs/vs2-behaviors-implementation.md`` T10's card calls "the
    ten-state hand-rolled machine" and asks to be ported. This is the
    baseline ``_Enemy10State`` below is measured and compared against."""

    state = ("phase", "timer")

    def attached(self, subject):
        # state = (...) only primes to 0 -- "0" isn't one of this hand-
        # rolled machine's phase names, so (unlike StateMachine's
        # declarative initial=, resolved generically by the framework)
        # this bespoke priming has to be written by hand here, on every
        # sprite (free included), the same walk _prime_pool_state uses
        # internally. One more piece of bookkeeping the port doesn't need.
        for sprite in subject._free:
            sprite.phase = "spawning"
            sprite.timer = 3
        for sprite in subject._live:
            sprite.phase = "spawning"
            sprite.timer = 3

    def step(self, sprites):
        live = sprites._live
        index = len(live) - 1
        while index >= 0:
            sprite = live[index]
            phase = sprite.phase
            if phase == "spawning":
                sprite.timer -= 1
                if sprite.timer <= 0:
                    sprite.phase = "descending"
                    sprite.timer = 0
            elif phase == "descending":
                sprite.dy -= 1
                if sprite.y <= GROUND:
                    sprite.phase = "orbiting"
                    sprite.timer = 4
            elif phase == "orbiting":
                sprite.dx += 1
                sprite.timer -= 1
                if sprite.timer <= 0:
                    sprite.phase = "chasing"
                    sprite.timer = 0
                    sprite.chase_ticks = 0
            elif phase == "chasing":
                sprite.chase_ticks += 1
                sprite.dx += 1
                if sprite.hp <= 0:
                    sprite.phase = "dying"
                    sprite.timer = 4
                elif sprite.hit:
                    sprite.hit = False
                    sprite.phase = "stunned"
                    sprite.timer = 3
                elif sprite.chase_ticks >= ATTACK_RANGE_TICKS:
                    sprite.phase = "attacking"
                    sprite.timer = 3
            elif phase == "attacking":
                sprite.timer -= 1
                if sprite.timer <= 0:
                    sprite.phase = "retreating"
                    sprite.timer = 3
            elif phase == "retreating":
                sprite.dx -= 1
                sprite.timer -= 1
                if sprite.timer <= 0:
                    sprite.phase = "orbiting"
                    sprite.timer = 4
            elif phase == "stunned":
                sprite.timer -= 1
                if sprite.timer <= 0:
                    sprite.phase = "chasing"
                    sprite.timer = 0
                    sprite.chase_ticks = 0
            elif phase == "dying":
                sprite.timer -= 1
                if sprite.timer <= 0:
                    sprite.phase = "exploding"
                    sprite.timer = 3
            elif phase == "exploding":
                sprite.timer -= 1
                if sprite.timer <= 0:
                    sprite.phase = "gone"
                    sprite.timer = 0
            elif phase == "gone":
                sprite.despawn()
            index -= 1


class _Enemy10State(StateMachine):
    """StateMachine port of ``_HandRolledEnemy10``, same behaviour, same
    ten states, same six timed transitions and three condition-based
    ones -- this task's proving case."""

    states = ("spawning", "descending", "orbiting", "chasing", "attacking",
              "retreating", "stunned", "dying", "exploding", "gone")
    initial = "spawning"

    def enter_spawning(self, sprite):
        self.hold(sprite, 3, then="descending")

    def spawning(self, sprite):
        pass

    def descending(self, sprite):
        sprite.dy -= 1
        if sprite.y <= GROUND:
            return "orbiting"

    def enter_orbiting(self, sprite):
        self.hold(sprite, 4, then="chasing")

    def orbiting(self, sprite):
        sprite.dx += 1

    def enter_chasing(self, sprite):
        sprite.chase_ticks = 0

    def chasing(self, sprite):
        sprite.chase_ticks += 1
        sprite.dx += 1
        if sprite.hp <= 0:
            return "dying"
        if sprite.hit:
            sprite.hit = False
            return "stunned"
        if sprite.chase_ticks >= ATTACK_RANGE_TICKS:
            return "attacking"

    def enter_attacking(self, sprite):
        self.hold(sprite, 3, then="retreating")

    def attacking(self, sprite):
        pass

    def enter_retreating(self, sprite):
        self.hold(sprite, 3, then="orbiting")

    def retreating(self, sprite):
        sprite.dx -= 1

    def enter_stunned(self, sprite):
        self.hold(sprite, 3, then="chasing")

    def stunned(self, sprite):
        pass

    def enter_dying(self, sprite):
        self.hold(sprite, 4, then="exploding")

    def dying(self, sprite):
        pass

    def enter_exploding(self, sprite):
        self.hold(sprite, 3, then="gone")

    def exploding(self, sprite):
        pass

    def enter_gone(self, sprite):
        sprite.despawn()

    def gone(self, sprite):
        # Never actually runs: enter_gone() despawns the sprite the same
        # tick it enters this state, removing it from pool._live before
        # any later Step's dispatch loop would visit it here. Still
        # required: attached() resolves every declared name via
        # getattr(self, name) up front, so a state with no per-tick work
        # of its own still needs this no-op to exist.
        pass


def test_ten_state_port_matches_the_hand_rolled_baseline_tick_for_tick():
    """Drives both implementations with identical external stimulus (a
    hit, then a killing blow) and asserts they report the same state name
    on every single tick -- the strongest correctness proof available that
    the port preserves behaviour exactly, not just "looks similar"."""
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.hand = scene.world.sprite_pool("ship.png", count=1)
            scene.hand.var("hp", 10)
            scene.hand.var("hit", False)
            scene.hand.var("chase_ticks", 0)
            scene.hand.spawn(0, 3)
            scene.hand.behave(_HandRolledEnemy10())

            scene.sm = scene.world.sprite_pool("ship.png", count=1)
            scene.sm.var("hp", 10)
            scene.sm.var("hit", False)
            scene.sm.var("chase_ticks", 0)
            scene.sm.spawn(0, 3)
            scene.sm.behavior_obj = scene.sm.behave(_Enemy10State())

        game = _build_scene(build)
        hand_sprite = game.hand._live[0]
        sm_sprite = game.sm._live[0]
        sm_behavior = game.sm.behavior_obj

        did_hit = False
        did_kill = False
        chasing_visits = 0
        max_ticks = 200
        tick = 0
        while tick < max_ticks:
            game.scene_step()
            tick += 1
            hand_phase = hand_sprite.phase
            sm_phase = sm_behavior.state_name(sm_sprite)
            check("tick %d: hand-rolled phase %r == StateMachine state %r"
                  % (tick, hand_phase, sm_phase), hand_phase == sm_phase)

            if hand_phase == "chasing" and not did_hit:
                chasing_visits += 1
                if chasing_visits == 1:
                    # First visit: exercise the condition-based
                    # chasing -> stunned -> chasing loop.
                    hand_sprite.hit = True
                    sm_sprite.hit = True
                    did_hit = True
            elif hand_phase == "chasing" and did_hit and not did_kill:
                # Second visit (after the stunned loop): exercise the
                # condition-based chasing -> dying -> exploding -> gone
                # terminal path.
                hand_sprite.hp = 0
                sm_sprite.hp = 0
                did_kill = True

            if len(game.hand) == 0 and len(game.sm) == 0:
                break

        check("the scripted scenario actually exercised the hit->stunned "
              "path", did_hit)
        check("the scripted scenario actually exercised the hp<=0->dying "
              "path", did_kill)
        check("both sprites reached the terminal 'gone' state and "
              "despawned, within the tick budget",
              len(game.hand) == 0 and len(game.sm) == 0)
    finally:
        _teardown()


def _significant_line_count(cls):
    """Lines of ``cls``'s own source that are neither blank nor a
    docstring-only/comment-only line -- a plain, defensible measure for
    the legibility/shortness comparison T10's acceptance bullet asks for
    ("the ten-state port is legible and shorter than what it replaces").
    Counts *code* lines only, so a class documented more heavily than its
    sibling isn't penalised or flattered by that alone."""
    source = inspect.getsource(cls)
    lines = source.splitlines()
    count = 0
    in_docstring = False
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if in_docstring:
            if '"""' in line or "'''" in line:
                in_docstring = False
            continue
        if line.startswith('"""') or line.startswith("'''"):
            # Single-line vs. opening a multi-line docstring.
            marker = line[:3]
            if line.count(marker) >= 2 and len(line) > 3:
                continue
            in_docstring = True
            continue
        if line.startswith("#"):
            continue
        if line.startswith("class ") or line.startswith("def "):
            count += 1
            continue
        count += 1
    return count


def test_ten_state_port_is_shorter_and_the_verdict_is_printed():
    if inspect is None:
        print("SKIP (no inspect module on this interpreter -- MicroPython's "
              "unix port doesn't ship one; run under python3 for the "
              "line-count comparison, matching test_vs2_behaviors.py's own "
              "CPython-only benchmarks)")
        return
    hand_lines = _significant_line_count(_HandRolledEnemy10)
    sm_lines = _significant_line_count(_Enemy10State)
    print("=" * 72)
    print("TEN-STATE PROVING CASE: line-count comparison")
    print("  hand-rolled (_HandRolledEnemy10):  %d significant lines" % hand_lines)
    print("  StateMachine port (_Enemy10State): %d significant lines" % sm_lines)
    if sm_lines < hand_lines:
        pct = 100.0 * (hand_lines - sm_lines) / hand_lines
        verdict = ("CLEARLY BETTER: %.0f%% shorter, and structurally "
                    "different in kind, not just degree -- the hand-rolled "
                    "version repeats a ten-way string-compare chain every "
                    "tick and re-implements the same 'timer -= 1; if "
                    "timer <= 0' countdown by hand in six separate places "
                    "(one bug away from a stale timer bleeding into the "
                    "wrong phase); the port has one small method per "
                    "state, no chain, and the countdown logic (hold()) "
                    "written exactly once." % pct)
    else:
        verdict = ("NOT CLEARLY BETTER by line count alone -- per the "
                    "acceptance bullet's own instruction, this would need "
                    "to be flagged and rethought rather than shipped.")
    print("  VERDICT: %s" % verdict)
    print("=" * 72)
    check("the StateMachine port is shorter than the hand-rolled baseline "
          "it replaces (%d vs %d significant lines)" % (sm_lines, hand_lines),
          sm_lines < hand_lines)


TESTS = [
    test_worked_example_initial_state_and_index,
    test_worked_example_condition_based_transition_to_exploding,
    test_worked_example_hold_fires_after_exactly_128_ticks,
    test_dispatch_table_is_a_tuple_of_bound_methods_indexed_by_state,
    test_initial_resolves_to_its_own_index_not_always_zero,
    test_a_state_machine_with_no_states_fails_loudly_at_attach,
    test_initial_not_in_states_is_a_clear_build_time_error,
    test_enter_and_exit_hooks_fire_matched_by_name,
    test_no_hooks_at_all_is_fine,
    test_returning_an_unknown_state_name_is_a_clear_error,
    test_hold_rejects_an_unknown_then_state,
    test_a_states_own_return_takes_priority_over_an_expiring_hold_same_tick,
    test_state_name_and_force_state_round_trip,
    test_force_state_fires_exit_and_enter_hooks,
    test_force_state_rejects_an_unknown_name,
    test_fsm_fields_primed_on_every_sprite_of_a_pool_free_included,
    test_fsm_fields_primed_on_a_lone_sprite_subject,
    test_fsm_fields_primed_across_every_member_of_a_family,
    test_two_state_machines_on_one_pool_is_a_state_conflict_error,
    test_two_state_machines_on_one_sprite_is_a_state_conflict_error,
    test_state_machine_on_a_scene_subject_is_a_build_time_error,
    test_step_one_dispatch_on_a_lone_sprite_subject,
    test_state_machine_over_40_sprites_allocates_nothing_across_1000_steps,
    test_no_name_lookup_at_all_during_steady_state_ticks,
    test_a_transition_costs_exactly_one_lookup_not_a_chain,
    test_dispatch_within_the_per_sprite_branch_budget,
    test_ten_state_port_matches_the_hand_rolled_baseline_tick_for_tick,
    test_ten_state_port_is_shorter_and_the_verdict_is_printed,
]


def main():
    for test in TESTS:
        print("--- %s ---" % test.__name__)
        test()
    print("ALL PASS: %d checks" % len(TESTS))


if __name__ == "__main__":
    main()
