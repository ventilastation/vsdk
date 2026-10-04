"""Smoke ``vs2`` Families on the MicroPython unix runtime itself.

Companion to ``tests/test_vs2_families.py`` (the dedicated, thorough
CPython/unittest test suite -- read that file's module docstring first).
Follows ``tests/test_vs2_api_micropython.py``'s precedent: plain script,
``assert``, no ``unittest`` (MicroPython's unix port does not carry a full
``unittest`` module worth relying on), importing the whole ``vs2`` package
against the same headless director/backend stack.

This file exists because the CPython suite's zero-allocation proof has a
real gap it cannot close: CPython's ``gc`` module has no ``mem_free()``,
so that suite falls back to ``tracemalloc``, and while writing it, calling
any Python function (even a no-op) roughly 1000+ times under
``tracemalloc`` on this repo's CPython 3.14 was empirically found to
report a few hundred bytes of interpreter/measurement-tool noise --
unrelated to what is actually being measured (see that file's
``test_family_two_level_walk_over_cached_members_allocates_nothing``
docstring for the isolation). MicroPython has no such adaptive-interpreter
noise and a real ``gc.mem_free()``, so *this* file runs the plan's shared
allocation-test convention for real, literally:

    gc.collect()
    before = gc.mem_free()
    for _ in range(1000):
        ...
    gc.collect()
    assert gc.mem_free() >= before - ALLOWANCE

against the actual MicroPython unix port -- the authoritative version of
the "Collide against a family inside a per-sprite loop allocates zero
bytes" acceptance bullet, standing in for ``Collide`` itself the same way
the CPython suite's synthetic walk does (``vs2/actions.py`` is a sibling
task's in-progress module, not importable from here either).

Run directly: ``micropython tests/test_vs2_families_micropython.py``.
"""

import sys

sys.path.insert(0, "apps/micropython")

import gc

from ventilastation import api_guard
from ventilastation.director import configure_runtime, director, reset_runtime, stripes


def check(name, condition):
    if not condition:
        raise AssertionError("FAILED: " + name)
    print("ok:", name)


def main():
    reset_runtime()
    api_guard.reset()
    runtime = configure_runtime("headless")
    stripes.clear()
    stripes["ship.png"] = 0
    runtime.platform.sprites.stripes[0] = {
        "width": 1, "height": 1, "frames": 4, "palette": 0,
    }
    api_guard.begin_app("games.micro_vs2_families", "vs2")

    import vs2

    # -- Build-time object over a sealed tuple of pools and sprites,
    # member order preserved, not iterable -----------------------------
    #
    # FamilyBehavior is attached during build() -- behave() is structural,
    # only legal while the scene is building -- and used both for the
    # "dispatch reaches every member in order" check and the "Behavior
    # dispatch across a family allocates nothing" check further down.

    # A fixed 3-slot ring, not a growing list -- across 1000 measured Steps
    # a plain ``list.append()`` here would itself be the allocation this
    # test is trying to rule out (its backing array keeps reallocating as
    # it grows), a mistake this file's own author made and caught while
    # writing this test: see the report for the isolation. Cycling
    # ``seen[index % 3]`` records the same per-Step visit order with no
    # growth at all.
    seen = [None, None, None]
    visits = [0]

    class FamilyBehavior:
        def step(self, pool):
            seen[visits[0] % 3] = pool
            visits[0] += 1

        def step_one(self, sprite):
            seen[visits[0] % 3] = sprite
            visits[0] += 1

    class BuildGame(vs2.Scene):
        idle_timeout = None
        back_button = False

        def build(self):
            self.world = self.layer("world")
            self.shots = self.world.sprite_pool("ship.png", count=10)
            self.hostiles_pool = self.world.sprite_pool("ship.png", count=8)
            self.boss_1 = self.world.sprite("ship.png")
            self.boss_2 = self.world.sprite("ship.png")
            self.hostiles = self.family(self.hostiles_pool, self.boss_1, self.boss_2)
            self.hostiles.behave(FamilyBehavior())
            for i in range(10):
                self.shots.spawn(i, i)
            for i in range(8):
                self.hostiles_pool.spawn(i * 2, i * 3)

    game = BuildGame()
    director.push(game)

    check("family.members preserves declared order",
          game.hostiles.members == (game.hostiles_pool, game.boss_1, game.boss_2))
    check("len(family) counts top-level members, not flattened sprites",
          len(game.hostiles) == 3)
    check("family.layer is the shared layer", game.hostiles.layer is game.world)

    try:
        for _ in game.hostiles:
            pass
        raise AssertionError("Family must not be iterable")
    except TypeError:
        check("Family.__iter__ raises TypeError", True)

    # -- A family spanning layers is a build-time error --------------------

    class CrossLayerGame(vs2.Scene):
        def build(self):
            a = self.layer("layer-a").sprite_pool("ship.png", count=1)
            b = self.layer("layer-b").sprite_pool("ship.png", count=1)
            self.family(a, b)

    try:
        director.push(CrossLayerGame())
        raise AssertionError("cross-layer family must be a build-time error")
    except ValueError as exc:
        message = str(exc)
        check("cross-layer error names both layers",
              "layer-a" in message and "layer-b" in message)
        # Director._enter_top_scene() already recovers from a failed
        # on_enter() by popping the failed scene and re-entering the one
        # below (here, `game`) itself -- an extra pop() here would pop
        # `game` off an otherwise-empty stack instead.

    # -- Legal as a PoolRef value -------------------------------------------

    params = vs2.params

    class Projectile(params.Parameterized):
        hits = params.PoolRef(None, label="Hits")

    projectile = Projectile(hits=game.hostiles)
    check("a Family round-trips through a PoolRef parameter",
          projectile.hits is game.hostiles)

    # -- Behavior attachment reaches every member, in family order, and the
    # dispatch itself allocates nothing across repeated Steps -------------
    # (FamilyBehavior was attached above, during BuildGame.build().)

    game.scene_step()
    check("family Behavior dispatch visits every member in order",
          seen == [game.hostiles_pool, game.boss_1, game.boss_2])

    for _ in range(50):  # warm-up, not part of the measured allowance
        game.scene_step()
    gc.collect()
    before = gc.mem_free()
    for _ in range(1000):
        game.scene_step()
    gc.collect()
    after = gc.mem_free()
    allowance = 512  # bytes; see tests/test_vs2_params.py for this convention
    delta = before - after
    print("family-behavior scene_step x1000: before=%d after=%d delta=%d bytes"
          % (before, after, delta))
    check("Behavior dispatch across a family allocates ~0 bytes after warm-up "
          "(delta=%d, allowance=%d)" % (delta, allowance),
          delta <= allowance)

    # -- The zero-allocation traversal shape a per-sprite Collide against a
    # family target needs (the actual acceptance bullet, proven for real
    # with gc.mem_free() rather than CPython's noisier tracemalloc stand-in
    # -- see this module's docstring) --------------------------------------

    def walk_once():
        # Cached exactly once per call, mirroring a build-time-resolved
        # Collide.run(pool) resolving its target family's member tuple
        # once per call, not once per sprite inside the loop.
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

    for _ in range(50):
        walk_once()

    gc.collect()
    before = gc.mem_free()
    for _ in range(1000):
        walk_once()
    gc.collect()
    after = gc.mem_free()
    delta = before - after
    print("two-level indexed walk x1000: before=%d after=%d delta=%d bytes"
          % (before, after, delta))
    check("a two-level indexed walk caching family._members once outside "
          "the loop allocates ~0 bytes after warm-up "
          "(delta=%d, allowance=%d)" % (delta, allowance),
          delta <= allowance)

    print("vs2 families micropython: all checks passed")


if __name__ == "__main__":
    main()
