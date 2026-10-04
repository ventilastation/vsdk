"""Smoke VS2 variables (T5) on the MicroPython unix runtime itself.

Companion to ``tests/test_vs2_variables.py`` (the full CPython suite,
functionally thorough but blind to real allocation since CPython's ``gc``
has no ``mem_free``). This file exists specifically for the numbers that
only mean something measured for real: the proposal's own
"first assignment of a name, N sprites: X bytes (~33 bytes each)" build-time
figure, and the zero-allocation-per-tick claim it rests on. It also re-runs
the functional core (recycle-never-inherits, reserved names, the
``vs2.project`` app-switch fix, a real store round trip) so a MicroPython-
specific bug (e.g. a ``dir()``/format-string difference) can't hide behind
the CPython suite alone.

Follows ``tests/test_vs2_api_micropython.py``'s plain-script pattern (no
``unittest`` -- the MicroPython unix port used by this repo's test runner
does not carry one).
"""

import sys

sys.path.insert(0, "apps/micropython")

import gc
import uos as os

from ventilastation import api_guard
from ventilastation.director import configure_runtime, director, reset_runtime, stripes


def _setup(slug):
    reset_runtime()
    api_guard.reset()
    runtime = configure_runtime("headless")
    stripes.clear()
    stripes["ship.png"] = 0
    runtime.platform.sprites.stripes[0] = {
        "width": 1, "height": 1, "frames": 4, "palette": 0,
    }
    api_guard.begin_app(slug, "vs2")
    import vs2
    return vs2


def test_pool_var_primes_and_spawn_resets_never_inherits():
    vs2 = _setup("games.micro_vs2_variables")

    class Game(vs2.Scene):
        def build(self):
            self.pool = self.layer("world").sprite_pool("ship.png", count=1)
            self.pool.var("hp", 5)
            self.pool.var("charge", 0.0)

    game = Game()
    director.push(game)
    assert game.pool._free[0].hp == 5, "priming must reach the free sprite"

    for _ in range(3):
        sprite = game.pool.spawn(0, 0)
        assert (sprite.hp, sprite.charge) == (5, 0.0), \
            "spawn() must reset declared vars to their defaults"
        sprite.hp = 0
        sprite.charge = 99.9
        game.pool.despawn(sprite)

    print("vs2 variables micropython: spawn() reset verified over 3 recycle cycles")


def test_kinds_applies_row_and_bad_arity_is_a_build_time_error():
    vs2 = _setup("games.micro_vs2_variables")

    class Game(vs2.Scene):
        def build(self):
            self.pool = self.layer("world").sprite_pool("ship.png", count=1,
                                                          on_empty=vs2.RECYCLE)
            self.pool.var("hp", 1)
            self.pool.var("score", 10)
            self.pool.kinds(driller=(3, 75), chiller=(1, 40))

    game = Game()
    director.push(game)
    driller = game.pool.spawn(0, 0, kind="driller")
    assert (driller.hp, driller.score) == (3, 75)
    chiller = game.pool.spawn(0, 0, kind="chiller")
    assert (chiller.hp, chiller.score) == (1, 40)
    assert chiller is driller, "one-slot pool must recycle the same sprite"

    class BadArity(vs2.Scene):
        def build(self):
            pool = self.layer("world").sprite_pool("ship.png", count=1)
            pool.var("hp", 1)
            pool.kinds(driller=(1, 2))  # hp is the pool's only variable

    raised = False
    try:
        director.push(BadArity())
    except ValueError as error:
        raised = True
        message = str(error)
        assert "driller" in message and "hp" in message, \
            "message must name the offending kind and the declared variables"
    assert raised, "a kinds() row with the wrong arity must be a build-time error"
    print("vs2 variables micropython: kinds() application and bad-arity error verified")


def test_reserved_names_rejected_on_pool_scene_and_project():
    vs2 = _setup("games.micro_vs2_variables")
    reserved = ("dx", "dy", "fsm_state", "fsm_hold", "fsm_then", "enabled")

    for name in reserved:
        class Game(vs2.Scene):
            _reserved_name = name

            def build(self):
                pool = self.layer("world").sprite_pool("ship.png", count=1)
                pool.var(self._reserved_name, 0)

        raised = False
        try:
            director.push(Game())
        except ValueError:
            raised = True
        assert raised, "pool.var(%r) must be rejected" % (name,)

    for name in reserved:
        class Game(vs2.Scene):
            _reserved_name = name

            def build(self):
                self.var(self._reserved_name, 0)

        raised = False
        try:
            director.push(Game())
        except ValueError:
            raised = True
        assert raised, "scene.var(%r) must be rejected" % (name,)

    vs2.project._vars = {}
    vs2.project._persisted = set()
    for name in reserved:
        raised = False
        try:
            vs2.project.var(name, 0)
        except ValueError:
            raised = True
        assert raised, "project.var(%r) must be rejected" % (name,)

    print("vs2 variables micropython: all 6 reserved names rejected on pool/scene/project")


def test_project_resets_on_app_switch_and_restores_on_switch_back():
    """The gap this task fixes: vs2.project must rebind its declared
    variables when a different app becomes current, the same way
    vs2.store already does -- otherwise a second game's declaration
    silently reads the first game's in-memory value."""
    vs2 = _setup("games.micro_vs2_variables")

    api_guard.begin_app("acme.gameA", "vs2")
    vs2.project._vars = {}
    vs2.project._persisted = set()
    value_a = vs2.project.var("high_score", 0)
    assert value_a == 0
    vs2.project.high_score = 111

    # No reset_runtime()/api_guard.reset() here -- exactly what a
    # launcher-hosted multi-game session does when it switches games.
    api_guard.begin_app("acme.gameB", "vs2")
    value_b = vs2.project.var("high_score", 0)
    assert value_b == 0, "gameB must not read gameA's in-memory value"
    vs2.project.high_score = 5

    api_guard.begin_app("acme.gameA", "vs2")
    value_again = vs2.project.var("high_score", 0)
    assert value_again == 0, \
        "declaring again after a switch is a fresh declare, not a stale read"

    print("vs2 variables micropython: vs2.project isolates declared vars across an app switch")


def test_project_persist_round_trips_through_the_real_store():
    vs2 = _setup("games.micro_vs2_variables")
    old_cwd = os.getcwd()
    scratch = "/tmp/vs2_project_persist_micropython_test"
    try:
        _rmtree(scratch)
    except OSError:
        pass
    os.mkdir(scratch)
    os.mkdir(scratch + "/games")
    os.chdir(scratch)
    try:
        api_guard.begin_app("acme.persisttest", "vs2")
        project_a = vs2._Project()
        value = project_a.var("high_score", 0, persist=True)
        assert value == 0, "nothing saved yet"
        project_a.high_score = 4242
        project_a.save()
        assert _exists("saves/acme.persisttest.json"), "save() must write the document"

        # Force a disk reload, simulating a fresh process's first access,
        # instead of trusting the store's in-memory cache from the write.
        vs2.store._rebind(vs2.store._slug)

        project_b = vs2._Project()
        reloaded = project_b.var("high_score", 0, persist=True)
        assert reloaded == 4242, \
            "a fresh declare after a disk reload must read back the saved value"
        print("vs2 variables micropython: vs2.project persist=True round-trips "
              "through the real store")
    finally:
        os.chdir(old_cwd)
        _rmtree(scratch)


def test_writing_a_primed_var_allocates_nothing_once_warm():
    vs2 = _setup("games.micro_vs2_variables")

    # var() is only legal inside build() (SceneSealedError otherwise), so
    # the build-time measurement bracket has to live there too.
    class Game(vs2.Scene):
        declare_cost = None

        def build(self):
            self.pool = self.layer("world").sprite_pool("ship.png", count=40)
            gc.collect()
            before = gc.mem_free()
            self.pool.var("hp", 3, min=0, max=99)
            gc.collect()
            after = gc.mem_free()
            Game.declare_cost = before - after

    game = Game()
    director.push(game)

    # The build-time cost, reported the same shape as the proposal's own
    # "Per-instance state" example ("first assignment of a name, 40
    # sprites: 1312 bytes (~33 bytes each)").
    sprite_count = len(game.pool._free)
    print("first assignment of a name, %d sprites: %d bytes (~%.1f bytes each)"
          % (sprite_count, game.declare_cost, game.declare_cost / sprite_count))
    assert game.declare_cost > 0, "the build-time declare must actually cost something"

    sprites = list(game.pool._free)
    for _ in range(50):
        for sprite in sprites:
            sprite.hp += 1
            sprite.hp -= 1

    gc.collect()
    before = gc.mem_free()
    for _ in range(1000):
        for sprite in sprites:
            sprite.hp += 1
            sprite.hp -= 1
    gc.collect()
    after = gc.mem_free()
    allowance = 64  # bytes; GC bookkeeping/arena rounding noise, not a real cost
    delta = before - after
    print("overwriting a primed name, %d sprites x 1000 ticks: %d bytes"
          % (sprite_count, delta))
    assert delta <= allowance, \
        "writing an already-primed variable in a tick must allocate ~0 bytes (delta=%d)" % delta


def test_spawn_with_kind_allocates_nothing_once_warm():
    vs2 = _setup("games.micro_vs2_variables")

    class Game(vs2.Scene):
        def build(self):
            self.pool = self.layer("world").sprite_pool("ship.png", count=1,
                                                          on_empty=vs2.RECYCLE)
            self.pool.var("hp", 1)
            self.pool.var("score", 10)
            self.pool.kinds(driller=(3, 75), chiller=(1, 40))

    game = Game()
    director.push(game)

    def spawn_alternating(count):
        for index in range(count):
            kind = "driller" if index % 2 == 0 else "chiller"
            game.pool.spawn(0, 0, kind=kind)

    spawn_alternating(200)  # warm-up: both kinds, well before measuring

    gc.collect()
    before = gc.mem_free()
    spawn_alternating(1000)
    gc.collect()
    after = gc.mem_free()
    allowance = 64
    delta = before - after
    print("kinds()-indexed spawn x 1000 ticks: %d bytes" % (delta,))
    assert delta <= allowance, \
        "kind resolution at spawn must allocate ~0 bytes once warm (delta=%d)" % delta


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _rmtree(path):
    try:
        entries = list(os.ilistdir(path))
    except OSError:
        return
    for name, kind, *_rest in entries:
        full = path + "/" + name
        if kind & 0x4000:
            _rmtree(full)
        else:
            os.remove(full)
    os.rmdir(path)


TESTS = [
    test_pool_var_primes_and_spawn_resets_never_inherits,
    test_kinds_applies_row_and_bad_arity_is_a_build_time_error,
    test_reserved_names_rejected_on_pool_scene_and_project,
    test_project_resets_on_app_switch_and_restores_on_switch_back,
    test_project_persist_round_trips_through_the_real_store,
    test_writing_a_primed_var_allocates_nothing_once_warm,
    test_spawn_with_kind_allocates_nothing_once_warm,
]


def main():
    for test in TESTS:
        test()
    reset_runtime()
    api_guard.reset()
    print("vs2 variables micropython: passed (%d checks)" % len(TESTS))


if __name__ == "__main__":
    main()
