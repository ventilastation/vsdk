"""Dedicated tests for VS2 :class:`Family` (spec: ``docs/vs2-behaviors-proposal.md``
``## Families``; work-breakdown card: ``docs/vs2-behaviors-implementation.md``
T7).

``Family`` and ``Scene.family()`` were built by T3 (the ``__init__.py``
attachment-point pass, Wave 2) as a *real* implementation, not a stub --
T3's own ``tests/test_vs2_api.py`` already carries a couple of basic checks.
This file is T7's independent, thorough pass over every acceptance bullet
in the plan, written against the real implementation rather than trusting
the source reading:

- Build-time object over a sealed tuple of pools and sprites.
- Not iterable -- two-level indexed traversal instead.
- Legal as a ``Collide`` target and a ``PoolRef`` value.
- Behavior attachment to a family primes state across all members.
- Member order preserved and deterministic.
- A family spanning layers is a build-time error.

Follows ``tests/test_vs2_api.py``'s header and ``setUp`` pattern (same
mocked headless director/backend stack) since a ``Family`` cannot be built
without a real ``Scene``/``Layer``/``SpritePool``/``Sprite`` behind it --
unlike ``vs2/params.py``, which is a standalone leaf module and gets the
plain-script, dual-interpreter treatment in ``tests/test_vs2_params.py``.

The zero-allocation acceptance bullet ("Collide against a family inside a
per-sprite loop allocates zero bytes") is proven here as a **synthetic**
two-level indexed walk directly against ``Family`` -- ``Collide`` itself is
T4's Action (``vs2/actions.py``, a sibling task in progress, not this
file's to touch), so it cannot be exercised through the real thing yet. See
``test_family_two_level_walk_over_cached_members_allocates_nothing`` for
the walk and its docstring for exactly what this does and does not prove.
CPython has no ``gc.mem_free()``, so this file uses the same
``tracemalloc`` "retained memory after warm-up is exactly zero" convention
``test_vs2_api.py`` already established for its own
``test_scene_step_allocates_nothing_new_for_a_plain_scene``; the literal
``gc.collect()``/``gc.mem_free()`` convention from the plan's shared
conventions runs for real on the actual MicroPython interpreter in the
companion file ``tests/test_vs2_families_micropython.py``.
"""

import os
import sys
import tracemalloc
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
sys.modules.setdefault("uos", os)
if "utime" not in sys.modules:
    import time

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


class Vs2FamiliesTests(unittest.TestCase):
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
        stripes["ship.png"] = 0
        self.runtime_director.platform.sprites.stripes[0] = {
            "width": 8, "height": 8, "frames": 4, "palette": 0,
        }
        api_guard.begin_app("games.test_vs2_families", "vs2")
        import vs2
        self.vs2 = vs2

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def enter(self, scene):
        director.push(scene)
        return scene

    # -- Build-time object over a sealed tuple of pools and sprites --------

    def test_family_is_sealed_tuple_of_pools_and_sprites_in_declared_order(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.world = self.layer("world")
                self.pool_a = self.world.sprite_pool("ship.png", count=3)
                self.solo_1 = self.world.sprite("ship.png")
                self.pool_b = self.world.sprite_pool("ship.png", count=2)
                self.solo_2 = self.world.sprite("ship.png")
                self.squad = self.family(self.pool_a, self.solo_1,
                                          self.pool_b, self.solo_2)

        game = self.enter(Game())
        self.assertIsInstance(game.squad, vs2.Family)
        self.assertEqual(game.squad.members,
                         (game.pool_a, game.solo_1, game.pool_b, game.solo_2))
        self.assertEqual(game.squad._members,
                         (("pool", game.pool_a), ("sprite", game.solo_1),
                          ("pool", game.pool_b), ("sprite", game.solo_2)))
        self.assertEqual(len(game.squad), 4)
        self.assertIs(game.squad.layer, game.world)
        self.assertIs(game.squad.scene, game)

    def test_family_member_order_preserved_across_rebuilds(self):
        # Ten members, deliberately alternating kind and created in an
        # order that disagrees with any plausible accidental sort (by
        # id(), by name, by pool capacity) -- a reordering bug would have
        # to be very specifically wrong to survive this.
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.world = self.layer("world")
                members = []
                for i in range(10):
                    if i % 2 == 0:
                        members.append(self.world.sprite_pool(
                            "ship.png", count=(10 - i)))
                    else:
                        members.append(self.world.sprite("ship.png"))
                self.raw_members = tuple(members)
                self.squad = self.family(*members)

        game = self.enter(Game())
        self.assertEqual(game.squad.members, game.raw_members)
        first_order = game.squad.members

        # Rebuild the same scene (pop and re-enter) and check the exact
        # same declared order comes back -- determinism, not just an
        # accident of one run.
        director.pop()
        game2 = self.enter(Game())
        self.assertEqual(game2.squad.members, game2.raw_members)
        self.assertEqual(
            [type(m).__name__ for m in first_order],
            [type(m).__name__ for m in game2.squad.members],
        )

    # -- Not iterable --------------------------------------------------

    def test_family_not_iterable(self):
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.world = self.layer("world")
                self.pool = self.world.sprite_pool("ship.png", count=2)
                self.solo = self.world.sprite("ship.png")
                self.squad = self.family(self.pool, self.solo)

        game = self.enter(Game())
        with self.assertRaises(TypeError):
            iter(game.squad)
        with self.assertRaises(TypeError):
            for _ in game.squad:
                pass
        with self.assertRaises(TypeError):
            list(game.squad)

    # -- Build-time validation ------------------------------------------

    def test_family_requires_at_least_one_member(self):
        vs2 = self.vs2

        class Empty(vs2.Scene):
            def build(self):
                self.layer("world")
                self.family()

        with self.assertRaises(ValueError):
            self.enter(Empty())

    def test_family_rejects_non_pool_non_sprite_member_naming_offender(self):
        vs2 = self.vs2

        class BadMember(vs2.Scene):
            def build(self):
                pool = self.layer("world").sprite_pool("ship.png", count=1)
                self.family(pool, "not a sprite or pool")

        with self.assertRaises(TypeError) as ctx:
            self.enter(BadMember())
        self.assertIn("not a sprite or pool", str(ctx.exception))

    def test_family_cross_layer_members_is_build_time_error_naming_both(self):
        vs2 = self.vs2

        class CrossLayer(vs2.Scene):
            def build(self):
                self.a = self.layer("layer-a").sprite_pool("ship.png", count=1)
                self.b = self.layer("layer-b").sprite_pool("ship.png", count=1)
                self.family(self.a, self.b)

        with self.assertRaises(ValueError) as ctx:
            self.enter(CrossLayer())
        message = str(ctx.exception)
        self.assertIn("layer-a", message)
        self.assertIn("layer-b", message)

        # Unnamed layers fall back to "unnamed" rather than "None" or a
        # blank string, per Scene.family()'s own docstring/contract.
        class CrossLayerUnnamed(vs2.Scene):
            def build(self):
                a = self.layer().sprite_pool("ship.png", count=1)
                b = self.layer().sprite_pool("ship.png", count=1)
                self.family(a, b)

        with self.assertRaises(ValueError) as ctx2:
            self.enter(CrossLayerUnnamed())
        self.assertIn("unnamed", str(ctx2.exception))

    # -- The allocation-relevant distinction between .members and ._members --

    def test_members_property_reallocates_but_internal_tuple_is_stable(self):
        """``.members`` is documented as "read freely" but is a property
        that rebuilds a fresh tuple via a generator expression on every
        access -- so two reads are two different tuple objects. The sealed
        ``._members`` backing it is the *same* tuple object every time
        (it is a plain attribute, not a descriptor), which is exactly what
        makes caching it once outside a hot loop free and safe.
        """
        vs2 = self.vs2

        class Game(vs2.Scene):
            def build(self):
                self.world = self.layer("world")
                self.pool = self.world.sprite_pool("ship.png", count=2)
                self.squad = self.family(self.pool)

        game = self.enter(Game())
        self.assertIsNot(game.squad.members, game.squad.members,
                         "the .members property must build a fresh tuple "
                         "every access (documented behaviour) -- a per-tick "
                         "reader must cache it, not re-read it")
        self.assertIs(game.squad._members, game.squad._members,
                      "the sealed backing tuple itself is never rebuilt")

    # -- Behavior attachment reaches every member, in family order ---------

    def test_family_behave_dispatches_every_member_through_scene_step(self):
        """Not the "priming" mechanism itself (that is state priming, a
        Behavior-base-class concern that lands with T8 in Wave 4 -- see
        this file's module docstring and the task report) but the
        plumbing "priming" depends on: every member of a family with an
        attached Behavior is actually visited, in family order, through
        the real ``scene_step()`` path (``Scene._run_behaviors``), not by
        reaching into private dispatch internals.
        """
        vs2 = self.vs2
        calls = []

        class FamilyBehavior:
            def step(self, pool):
                calls.append(("pool", pool))

            def step_one(self, sprite):
                calls.append(("sprite", sprite))

        class Game(vs2.Scene):
            idle_timeout = None
            back_button = False

            def build(self):
                self.world = self.layer("world")
                self.pool_a = self.world.sprite_pool("ship.png", count=2)
                self.solo_1 = self.world.sprite("ship.png")
                self.pool_b = self.world.sprite_pool("ship.png", count=1)
                self.solo_2 = self.world.sprite("ship.png")
                self.squad = self.family(self.pool_a, self.solo_1,
                                          self.pool_b, self.solo_2)
                self.squad.behave(FamilyBehavior())

        game = self.enter(Game())
        game.scene_step()
        self.assertEqual(calls, [
            ("pool", game.pool_a),
            ("sprite", game.solo_1),
            ("pool", game.pool_b),
            ("sprite", game.solo_2),
        ])

        # A second Step dispatches again, in the same order -- this is a
        # per-tick pass, not a one-shot "attached()" style call.
        calls.clear()
        game.scene_step()
        self.assertEqual(calls, [
            ("pool", game.pool_a),
            ("sprite", game.solo_1),
            ("pool", game.pool_b),
            ("sprite", game.solo_2),
        ])

    # -- Zero-allocation traversal shape (the "not iterable" payoff) -------

    def test_family_two_level_walk_over_cached_members_allocates_nothing(self):
        """Synthetic proof standing in for ``Collide`` (T4, not landed in
        this worktree): a per-sprite loop over an unrelated pool
        ("shots"), each iteration doing a two-level indexed walk over a
        family target -- the exact shape ``Collide`` needs and the whole
        reason ``Family.__iter__`` raises instead of yielding.

        The load-bearing detail: ``members = family._members`` is read
        **once**, outside both loops, and reused for every tick and every
        outer sprite. If a caller instead re-read ``family.members`` (the
        property) inside the loop, this same walk would allocate a fresh
        tuple every single call -- see
        ``test_members_property_reallocates_but_internal_tuple_is_stable``
        above for the identity proof of *why*. This test only establishes
        that the traversal shape itself is zero-alloc-capable when used
        correctly; it does not prove ``Collide`` actually uses this shape
        once that Action lands, since this file cannot import
        ``vs2/actions.py`` (a sibling task's in-progress module). That is
        a real inter-task seam, not a gap in this test.

        Uses a small fixed ``ALLOWANCE`` rather than asserting exactly
        zero retained bytes, unlike ``test_vs2_api.py``'s analogous
        ``test_scene_step_allocates_nothing_new_for_a_plain_scene``.
        Measured empirically while writing this test: on this repo's
        CPython 3.14 interpreter, ``tracemalloc`` itself reports a few
        hundred bytes of *sustained, unavoidable* retained growth across
        repeated 1000-call batches for a completely empty no-op function
        with no loop body at all -- reproduced with ``walk_once`` replaced
        by ``pass``, isolating it as call-count-driven interpreter/
        tracemalloc bookkeeping, not anything this walk allocates. Below
        ~200 calls it does not appear (matching why the existing
        200-iteration ``test_vs2_api.py`` check gets away with a literal
        ``== 0``). ``ALLOWANCE`` is sized well above that measured noise
        floor and well below what a single real per-tick tuple/list
        allocation over 1000 iterations would cost (tens of thousands of
        bytes), so this still catches a real regression; see this task's
        report for the full isolation. The same convention (a documented
        allowance instead of a literal zero, for exactly this kind of
        interpreter noise) is already established in
        ``tests/test_vs2_params.py``.
        """
        vs2 = self.vs2

        class Game(vs2.Scene):
            idle_timeout = None
            back_button = False

            def build(self):
                self.world = self.layer("world")
                self.shots = self.world.sprite_pool("ship.png", count=40)
                self.hostiles_pool = self.world.sprite_pool("ship.png", count=30)
                self.boss_1 = self.world.sprite("ship.png")
                self.boss_2 = self.world.sprite("ship.png")
                self.hostiles = self.family(self.hostiles_pool,
                                             self.boss_1, self.boss_2)
                for i in range(40):
                    self.shots.spawn(x=i, y=i)
                for i in range(30):
                    self.hostiles_pool.spawn(x=i * 2, y=i * 3)

        game = self.enter(Game())

        def walk_once():
            # Cached exactly once per call to this function, mirroring
            # what a build-time-resolved Collide.run(pool) would do:
            # resolve its target family's member tuple once per call,
            # not once per sprite inside the loop.
            members = game.hostiles._members
            hits = 0
            shots_live = game.shots._live
            outer = len(shots_live) - 1
            while outer >= 0:
                shot = shots_live[outer]
                member_index = 0
                member_count = len(members)
                while member_index < member_count:
                    kind, member = members[member_index]
                    if kind == "pool":
                        inner_live = member._live
                        inner = len(inner_live) - 1
                        while inner >= 0:
                            target = inner_live[inner]
                            if shot.x == target.x and shot.y == target.y:
                                hits += 1
                            inner -= 1
                    else:
                        target = member
                        if shot.x == target.x and shot.y == target.y:
                            hits += 1
                    member_index += 1
                outer -= 1
            return hits

        for _ in range(50):  # warm-up: one-time caches, not a leak
            walk_once()

        ALLOWANCE = 4096  # bytes; see the docstring above for how this was sized

        tracemalloc.start()
        try:
            before, _peak = tracemalloc.get_traced_memory()
            for _ in range(1000):
                walk_once()
            current, _peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        delta = current - before
        self.assertLessEqual(
            delta, ALLOWANCE,
            "a two-level indexed walk caching family._members once "
            "outside the loop must not retain allocation proportional to "
            "iteration count (delta=%d, allowance=%d)" % (delta, ALLOWANCE))

    # -- Legal as a PoolRef value -----------------------------------------

    def test_family_round_trips_through_a_poolref_parameter(self):
        """``vs2/params.py`` (Wave 1, landed, not this task's file to
        edit) documents ``PoolRef`` as accepting "a pool, sprite or
        family" with **no runtime type check** -- it is carried through
        unvalidated because ``params.py`` cannot import ``vs2/__init__.py``
        (the dependency runs the other way). So "legal as a PoolRef value"
        is true by construction; this proves a real ``Family`` instance
        round-trips through a ``PoolRef``-typed parameter exactly like a
        bare ``SpritePool`` does: default, override, and introspection.
        """
        vs2 = self.vs2
        params = vs2.params

        class Projectile(params.Parameterized):
            hits = params.PoolRef(None, label="Hits")

        class Game(vs2.Scene):
            def build(self):
                self.world = self.layer("world")
                self.pool = self.world.sprite_pool("ship.png", count=2)
                self.solo = self.world.sprite("ship.png")
                self.hostiles = self.family(self.pool, self.solo)

        game = self.enter(Game())

        # Default: no override at all.
        self.assertIsNone(Projectile().hits)

        # A bare SpritePool, the case params.py's own test suite covers.
        pool_only = Projectile(hits=game.pool)
        self.assertIs(pool_only.hits, game.pool)

        # A Family -- the new case this task adds coverage for.
        family_ref = Projectile(hits=game.hostiles)
        self.assertIs(family_ref.hits, game.hostiles)
        self.assertIsInstance(family_ref.hits, vs2.Family)

        # Introspection (what the panel, the vs2beh protocol and the
        # reference docs all read) reports the same type_name and default
        # regardless of which kind of value happens to be bound at
        # runtime -- introspection describes the *declaration*, not a
        # particular instance's override.
        rows = {name: (type_name, default, metadata)
                for name, type_name, default, metadata in params.introspect(Projectile)}
        self.assertEqual(rows["hits"][0], "pool")
        self.assertIsNone(rows["hits"][1])


if __name__ == "__main__":
    unittest.main()
