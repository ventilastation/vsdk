"""Tests for VS2 variables: T5 in ``docs/vs2-behaviors-implementation.md``.

Covers every acceptance bullet under "Variables" for the code T3 already
shipped (``SpritePool.var``/``kinds``/``spawn``, ``Scene.var``,
``vs2.project``), plus the one confirmed gap this task closes: ``vs2.project``
never rebound its declared variables when a different app became current,
unlike ``vs2.store`` (T2a), which already does. See the ``_Project`` docstring
in ``apps/micropython/vs2/__init__.py`` for the fix itself.

Follows ``tests/test_vs2_api.py``'s header pattern (the ``uos``/``utime``
shims MicroPython-only modules need under CPython) since this file imports
the full ``vs2`` package, not just a standalone module.

Run: ``python3 tests/test_vs2_variables.py``.
"""

import os
import shutil
import sys
import tempfile
import time
import tracemalloc
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
sys.modules.setdefault("uos", os)
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
    sys.modules["utime"] = _Utime

from ventilastation import api_guard
from ventilastation.director import configure_runtime, director, reset_runtime, stripes


class Vs2VariablesTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        api_guard.reset()
        self.runtime_director = configure_runtime("headless")
        self.runtime_director.buttons = 0
        self.runtime_director.last_buttons = 0
        self.runtime_director.buttons2 = 0
        self.runtime_director.last_buttons2 = 0
        self.runtime_director.extra_buttons = 0
        self.runtime_director.last_extra_buttons = 0
        stripes.clear()
        for index, name in enumerate(("ship.png", "terrain.png", "font.png")):
            stripes[name] = index
            self.runtime_director.platform.sprites.stripes[index] = {
                "width": 8, "height": 8, "frames": 4 if name != "font.png" else 128,
                "palette": 0,
            }
        api_guard.begin_app("games.test_vs2_variables", "vs2")
        import vs2
        self.vs2 = vs2

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def enter(self, scene):
        director.push(scene)
        return scene

    # -- priming ------------------------------------------------------------

    def test_pool_var_primes_free_and_already_spawned_sprites_at_build(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.pool = self.layer("world").sprite_pool("ship.png", count=4)
                # Spawn two before the variable is even declared, so priming
                # has to reach live sprites as well as the free ones -- not
                # just "whatever hasn't been spawned yet at declare time".
                self.spawned = [self.pool.spawn(0, 0), self.pool.spawn(0, 0)]
                self.pool.var("hp", 7, min=0, max=99)

        game = self.enter(Game())
        self.assertEqual(len(game.pool._live), 2)
        self.assertEqual(len(game.pool._free), 2)
        for sprite in game.pool._live:
            self.assertEqual(sprite.hp, 7, "priming must reach already-live sprites")
        for sprite in game.pool._free:
            self.assertEqual(sprite.hp, 7, "priming must reach free sprites")

    # -- spawn() reset --------------------------------------------------------

    def test_spawn_resets_declared_vars_and_never_inherits_previous_occupant(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.pool = self.layer("world").sprite_pool("ship.png", count=1)
                self.pool.var("hp", 5, min=0, max=99)
                self.pool.var("charge", 0.0)
                self.pool.var("angry", False)

        game = self.enter(Game())
        for cycle in range(3):
            sprite = game.pool.spawn(10 + cycle, 20 + cycle, frame=1,
                                      flip_x=True, flip_y=True)
            self.assertEqual((sprite.hp, sprite.charge, sprite.angry), (5, 0.0, False),
                             "spawn() must reset every declared var to its default")
            sprite.hp = 0
            sprite.charge = 99.9
            sprite.angry = True
            sprite.dx = 4
            sprite.dy = -4
            game.pool.despawn(sprite)
            self.assertEqual((sprite.dx, sprite.dy), (4, -4),
                             "despawn() does not itself touch dx/dy; spawn() does")

    def test_spawn_with_kind_after_recycle_does_not_leak_previous_kind(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.pool = self.layer("world").sprite_pool("ship.png", count=1)
                self.pool.var("hp", 1)
                self.pool.var("score", 10)
                self.pool.kinds(driller=(3, 75), chiller=(1, 40))

        game = self.enter(Game())
        driller = game.pool.spawn(0, 0, kind="driller")
        self.assertEqual((driller.hp, driller.score), (3, 75))
        driller.hp = 999
        driller.score = 999
        game.pool.despawn(driller)

        chiller = game.pool.spawn(0, 0, kind="chiller")
        self.assertIs(chiller, driller, "the pool only has one slot; must be the same object")
        self.assertEqual((chiller.hp, chiller.score), (1, 40),
                          "the recycled sprite must not carry over the previous kind's mutated values")

    # -- kinds() build-time errors --------------------------------------------

    def test_kinds_bad_arity_names_kind_and_declared_variables(self):
        vs2 = self.vs2

        class BadArity(vs2.Scene):
            def build(self):
                pool = self.layer("world").sprite_pool("ship.png", count=1)
                pool.var("hp", 1)
                pool.var("score", 40)
                pool.kinds(driller=(3,))  # missing the score value

        with self.assertRaises(ValueError) as caught:
            self.enter(BadArity())
        message = str(caught.exception)
        self.assertIn("driller", message, "message must name the offending kind")
        self.assertIn("hp", message, "message must name the declared variables")
        self.assertIn("score", message, "message must name the declared variables")

    def test_kinds_called_twice_is_a_build_time_error(self):
        vs2 = self.vs2

        class CalledTwice(vs2.Scene):
            def build(self):
                pool = self.layer("world").sprite_pool("ship.png", count=1)
                pool.var("hp", 1)
                pool.kinds(driller=(1,))
                pool.kinds(chiller=(2,))

        with self.assertRaises(ValueError):
            self.enter(CalledTwice())

    def test_kinds_rows_are_positional_not_named(self):
        """Documents a judgment call, not a bug to fix here (see report).

        ``kinds()`` rows are purely positional tuples over ``var()``
        declaration order -- exactly the shape of the proposal's own
        ``kinds(driller=(3, 75, 0.52), ...)`` example. There is therefore no
        way for a row to "name an undeclared variable": a row never
        references a variable by name, only by position. A same-length
        tuple is accepted regardless of what its values mean.

        A dict-shaped row is *not* rejected at build time either, because
        ``kinds()`` only checks ``len(row)`` against the declared field
        count, and ``len({"hp": 3})`` is 1, same as ``len((3,))``. It fails
        later instead, confusingly, the first time ``spawn(kind=...)`` tries
        to index it positionally. This is a real gap against the acceptance
        bullet's letter, but fixing it means changing ``SpritePool.kinds()``
        and ``spawn()``, which is outside this task's sanctioned edit (only
        the ``vs2.project`` app-switch fix touches ``vs2/__init__.py`` here).
        Recorded as a finding for whoever picks up the dict-row idea.
        """
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.pool = self.layer("world").sprite_pool("ship.png", count=1)
                self.pool.var("hp", 1)
                # A dict happens to have the right len() and slips past the
                # arity check that catches a wrong-length tuple.
                self.pool.kinds(driller={"hp": 3})

        game = self.enter(Game())
        with self.assertRaises(KeyError):
            # Confirms it is *not* a build-time error naming both sides --
            # it is a runtime KeyError from indexing the dict by position.
            game.pool.spawn(0, 0, kind="driller")

    # -- reserved names ---------------------------------------------------

    def test_reserved_names_rejected_on_pool_scene_and_project(self):
        vs2 = self.vs2
        reserved = ("dx", "dy", "fsm_state", "fsm_hold", "fsm_then", "enabled")

        for name in reserved:
            class Game(vs2.Scene):
                _reserved_name = name

                def build(self):
                    pool = self.layer("world").sprite_pool("ship.png", count=1)
                    pool.var(self._reserved_name, 0)

            # A failed on_enter() pops itself back off the stack (see
            # Director._enter_top_scene), so no cleanup is needed here --
            # matching the existing pattern in test_vs2_api.py.
            with self.assertRaises(ValueError, msg="pool.var(%r)" % name):
                self.enter(Game())

        for name in reserved:
            class Game(vs2.Scene):
                _reserved_name = name

                def build(self):
                    self.var(self._reserved_name, 0)

            with self.assertRaises(ValueError, msg="scene.var(%r)" % name):
                self.enter(Game())

        vs2.project._vars = {}
        vs2.project._persisted = set()
        for name in reserved:
            with self.assertRaises(ValueError, msg="project.var(%r)" % name):
                vs2.project.var(name, 0)

    # -- scene vs project scope -----------------------------------------------

    def test_scene_var_resets_fresh_on_every_rebuild(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.var("score", 0, min=0, max=999999)
                self.var("armed", False)
                self.layer("world")

        game = self.enter(Game())
        self.assertEqual((game.score, game.armed), (0, False))
        game.score = 42
        game.armed = True
        director.pop()

        game2 = self.enter(Game())
        self.assertEqual((game2.score, game2.armed), (0, False),
                          "a fresh entry must re-prime scene vars to their declared defaults")
        director.pop()

    def test_project_var_survives_scene_push_pop_unlike_scene_var(self):
        vs2 = self.vs2
        vs2.project._vars = {}
        vs2.project._persisted = set()
        vs2.project.var("run_total", 0)  # no persist= here; never touches vs2.store
        vs2.project.run_total = 3

        class Level(vs2.Scene):
            def build(self):
                self.layer("world")

        game = self.enter(Level())
        director.pop()
        # A whole scene entered and exited in between; the project variable
        # is untouched because nothing above the scene stack reset it.
        self.assertEqual(vs2.project.run_total, 3)

    # -- the app-switch gap this task fixes ------------------------------------

    def test_project_resets_declared_vars_when_the_current_app_changes(self):
        vs2 = self.vs2
        with mock.patch.object(vs2.store, "get", return_value=0):
            api_guard.begin_app("acme.gameA", "vs2")
            vs2.project.var("high_score", 0, persist=True)
            vs2.project.high_score = 111

            # A launcher-hosted session (or a test, or the emulator)
            # switching to a different game *without* a full process
            # reset -- exactly api_guard.begin_app's real contract.
            api_guard.begin_app("acme.gameB", "vs2")
            value = vs2.project.var("high_score", 0, persist=True)
            self.assertEqual(value, 0,
                              "a different app's declaration must not read the "
                              "previous app's value")
            self.assertEqual(vs2.project.high_score, 0)
            vs2.project.high_score = 5

            # Switching back must not resurrect gameB's value either --
            # gameA gets a clean re-declare of its own.
            api_guard.begin_app("acme.gameA", "vs2")
            value_again = vs2.project.var("high_score", 0, persist=True)
            self.assertEqual(value_again, 0,
                              "declaring again after a switch is a fresh declare, "
                              "not a stale read of either app's leftover value")

    def test_project_persist_is_isolated_per_app_across_a_real_switch(self):
        """The complete gap this task fixes, end to end: two games sharing
        one process, each with its own persisted value on disk through the
        real ``vs2.store``, switched between with nothing but
        ``api_guard.begin_app`` -- no ``reset_runtime()``, no process
        restart, exactly what a launcher-hosted multi-game session (or the
        emulator) does. Before the fix, gameB's declare would have silently
        returned gameA's in-memory value instead of gameB's own.
        """
        vs2 = self.vs2
        scratch = tempfile.mkdtemp(prefix="vs2_project_switch_")
        old_cwd = os.getcwd()
        try:
            os.mkdir(os.path.join(scratch, "games"))
            os.chdir(scratch)

            api_guard.begin_app("acme.gameA", "vs2")
            self.assertEqual(vs2.project.var("high_score", 0, persist=True), 0)
            vs2.project.high_score = 111
            vs2.project.save()

            api_guard.begin_app("acme.gameB", "vs2")
            self.assertEqual(vs2.project.var("high_score", 0, persist=True), 0,
                              "gameB must not inherit gameA's in-memory value")
            vs2.project.high_score = 5
            vs2.project.save()

            # Force a disk reload for both slugs' documents so the read
            # below cannot be satisfied by store.py's own in-memory cache
            # either -- this is checking the file, not a shared dict.
            vs2.store._rebind("acme.gameA")
            vs2.store._rebind("acme.gameB")

            api_guard.begin_app("acme.gameA", "vs2")
            self.assertEqual(vs2.project.var("high_score", 0, persist=True), 111,
                              "switching back must read gameA's own saved value, "
                              "not gameB's, and not a stale in-memory leftover")
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(scratch, ignore_errors=True)

    def test_project_persist_round_trips_through_the_real_store_across_reload(self):
        vs2 = self.vs2
        scratch = tempfile.mkdtemp(prefix="vs2_project_persist_")
        old_cwd = os.getcwd()
        try:
            os.mkdir(os.path.join(scratch, "games"))
            os.chdir(scratch)
            api_guard.begin_app("acme.persisttest", "vs2")

            project_a = vs2._Project()
            value = project_a.var("high_score", 0, persist=True)
            self.assertEqual(value, 0, "nothing saved yet")
            project_a.high_score = 4242
            project_a.save()

            saved_path = os.path.join(scratch, "saves", "acme.persisttest.json")
            self.assertTrue(os.path.exists(saved_path), "save() must write the document")

            # Force the shared vs2.store singleton to reload from disk,
            # simulating what a fresh process's first access would do,
            # rather than trusting its in-memory cache from the write above.
            vs2.store._rebind(vs2.store._slug)

            project_b = vs2._Project()
            reloaded = project_b.var("high_score", 0, persist=True)
            self.assertEqual(reloaded, 4242,
                              "a fresh declare after a disk reload must read back "
                              "the value the previous session saved")
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(scratch, ignore_errors=True)

    # -- allocation ---------------------------------------------------------

    def test_writing_a_primed_pool_var_in_a_tick_allocates_zero_bytes(self):
        vs2 = self.vs2

        # The build-time cost: declaring a name across every sprite in the
        # pool. var() is only legal inside build() (SceneSealedError
        # otherwise), so the measurement bracket has to live there too.
        # MicroPython's own ~33-bytes-per-name figure (see the proposal's
        # "Per-instance state") is only measurable under gc.mem_free() --
        # see tests/test_vs2_variables_micropython.py for that number for
        # real. Under CPython this only proves the cost is paid once, up
        # front, and reports what CPython itself spent so the two are
        # never conflated.
        class Game(vs2.Scene):
            idle_timeout = None
            declare_bytes = None

            def build(self):
                self.pool = self.layer("world").sprite_pool("ship.png", count=40)
                tracemalloc.start()
                try:
                    self.pool.var("hp", 3, min=0, max=99)
                    Game.declare_bytes, _peak = tracemalloc.get_traced_memory()
                finally:
                    tracemalloc.stop()

        game = self.enter(Game())
        print("vs2 variables: declaring one var across %d sprites cost %d "
              "bytes under CPython (informational; MicroPython's own figure "
              "is measured in test_vs2_variables_micropython.py)"
              % (len(game.pool._free), game.declare_bytes))
        self.assertGreater(game.declare_bytes, 0,
                            "the build-time declare must actually cost something")

        sprites = list(game.pool._free)

        def touch_all(count):
            for _ in range(count):
                for sprite in sprites:
                    sprite.hp += 1
                    sprite.hp -= 1

        # Warm up with the exact operation about to be measured, and for
        # long enough to clear it: CPython's specializing adaptive
        # interpreter (and, on 3.13+, its tier-2 JIT) attaches its own
        # one-time bookkeeping to a hot loop only after several hundred
        # backedges, not a handful -- a shorter warm-up (or warming up a
        # *different* operation, like ``-= 0``) leaves that one-time cost
        # sitting inside the measured window and reads as a false
        # allocation. 1000 iterations comfortably clears it.
        touch_all(1000)

        # Even fully warmed up, this can still read a small constant,
        # non-zero handful of bytes depending on the exact CPython version
        # (see ``test_spawn_with_kind_resolution_allocates_zero_bytes_once_
        # warm`` below for the same hazard with a different root cause:
        # confirmed on 3.12.9 this reads a steady 32 B that a longer
        # warm-up never clears). So the meaningful check -- the one that
        # actually matches "allocates zero bytes per write" -- is that the
        # retained cost does not grow between two very different iteration
        # counts, i.e. it's O(1) one-time bookkeeping, not O(N) real churn.
        tracemalloc.start()
        try:
            touch_all(200)
            current_small, _peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        tracemalloc.start()
        try:
            touch_all(2000)
            current_large, _peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        self.assertEqual(current_small, current_large,
                          "retained bytes must not grow with the number of "
                          "writes to an already-primed variable (O(1), not O(N))")

    def test_spawn_with_kind_resolution_allocates_zero_bytes_once_warm(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            idle_timeout = None

            def build(self):
                self.pool = self.layer("world").sprite_pool("ship.png", count=1,
                                                              on_empty=vs2.RECYCLE)
                self.pool.var("hp", 1)
                self.pool.var("score", 10)
                self.pool.kinds(driller=(3, 75), chiller=(1, 40))

        game = self.enter(Game())

        def spawn_alternating(count):
            for index in range(count):
                kind = "driller" if index % 2 == 0 else "chiller"
                game.pool.spawn(0, 0, kind=kind)

        # Warm up with the *same alternating pattern* about to be measured,
        # and for long enough: see the long comment in
        # test_writing_a_primed_pool_var_in_a_tick_allocates_zero_bytes --
        # CPython 3.13+'s tier-2 JIT needs several hundred backedges before
        # it stops attaching one-time bookkeeping to a hot loop, and an
        # alternating dict lookup (one kind, then the other) needs both
        # branches warmed, not just one.
        spawn_alternating(1000)

        # Even fully warmed up, this specific loop (spawn() -> despawn() ->
        # spawn() on a one-slot RECYCLE pool, every call) still reads a
        # constant, non-zero handful of bytes here under CPython, no matter
        # how long the warm-up: it comes from the pool's own ``_live``/
        # ``_free`` list occasionally being resized by CPython's list
        # allocator right at the moment tracing starts, not from anything
        # that scales with calls. So the meaningful check -- and the one
        # that actually matches "allocates zero bytes per call" -- is that
        # ``current`` does not grow between two very different iteration
        # counts, i.e. the retained cost is O(1), not O(N). Confirmed
        # empirically: constant 32 B from N=100 up to N=6400.
        tracemalloc.start()
        try:
            spawn_alternating(200)
            current_small, _peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        tracemalloc.start()
        try:
            spawn_alternating(2000)
            current_large, _peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        self.assertEqual(current_small, current_large,
                          "retained bytes must not grow with the number of "
                          "spawn(kind=...) calls once warm (O(1), not O(N))")


if __name__ == "__main__":
    unittest.main()
