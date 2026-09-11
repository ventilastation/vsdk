"""Tests for ``ventilastation/behavior_control.py``: the ``vs2beh``
live-tune protocol.

Spec: ``docs/vs2-behaviors-proposal.md``, ``## The live-tune loop`` and
``## State machines``. Work-breakdown card:
``docs/vs2-behaviors-implementation.md`` T11.

Deliberately **not** unittest-based, matching ``tests/test_vs2_behaviors.py``
(T8) and ``tests/test_vs2_actions.py`` (T4)'s precedent: this needs a real
``vs2`` scene (pools, sprites, families, Behaviors, Actions) to exercise the
protocol against, and writing it as a plain script means it can be run for
real on the MicroPython unix port too, not merely simulated under CPython:

    python3 tests/test_vs2beh.py
    micropython tests/test_vs2beh.py

Only the CPython run is wired into ``tests/run_tests.py`` (``CPYTHON_TESTS``),
matching T4/T8's own precedent.

**"Works over serial against the physical console"**: this environment has
no physical hardware. Every test here calls ``behavior_control.handle_command``
directly with a capturing ``send`` callback and inspects the exact wire text
it produces -- the same level of "serial" verification
``tests/test_povperf_controls.py``/``tests/test_povcal_state.py`` achieve
for the sibling ``povperf``/``povcal`` protocols (they, too, only ever call
``handle_command`` directly or exercise the emulator-side command composer;
neither has a real serial-loopback harness). One test additionally drives
the real ``director._dispatch_control()`` end to end, exercising the one
``elif cmd == "vs2beh":`` branch this task added to ``director.py`` --
genuine hardware confirmation remains outstanding (see this task's report).
"""

import os
import sys

sys.path.insert(0, "apps/micropython")

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

import json  # noqa: E402

from ventilastation import api_guard  # noqa: E402
from ventilastation import behavior_control  # noqa: E402
from ventilastation.director import configure_runtime, director, reset_runtime, stripes  # noqa: E402

import vs2  # noqa: E402
from vs2 import actions  # noqa: E402
from vs2.behaviors import Behavior  # noqa: E402
from vs2.params import Number, PoolRef, Var  # noqa: E402


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


def _setup():
    reset_runtime()
    api_guard.reset()
    runtime = configure_runtime("headless")
    stripes.clear()
    stripes["ship.png"] = 0
    runtime.platform.sprites.stripes[0] = {
        "width": 4, "height": 4, "frames": 4, "palette": 0,
    }
    api_guard.begin_app("games.test_vs2beh", "vs2")
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


def _send_capture():
    sent = []

    def send(data):
        sent.append(data)
    return sent, send


def _last_json(sent):
    return json.loads(sent[-1].decode())


def _find_subject(payload, name):
    for subject in payload["subjects"]:
        if subject["name"] == name:
            return subject
    return None


def _find_param(params, name):
    for param in params:
        if param["name"] == name:
            return param
    return None


# ---------------------------------------------------------------------------
# A test Action (T4 shipped Move/MoveTo/Animate/Collide only; the catalog's
# own Blink is T9's job, not built yet) -- gives ``list`` something nested
# under a Behavior to name and introspect, matching the spec's
# ``damageable.blink.on_ticks`` example.
# ---------------------------------------------------------------------------

class _Blink(actions.Action):
    on_ticks = Number(2, min=1, max=60)

    def run_one(self, sprite):
        return None


class Damageable(Behavior):
    hp = Number(1, min=1, max=99, step=1)
    score = Number(40, min=0, max=9999)
    explosion = PoolRef(None, label="Explosion pool")

    def attached(self, subject):
        self.blink = self.action(_Blink(on_ticks=2))

    def step(self, sprites):
        pass


class Wobbler(Behavior):
    speed_y = Number(1, min=0, max=8, step=0.25)

    def step(self, sprites):
        pass


# ---------------------------------------------------------------------------
# list: subjects, vars, behaviors, actions, PoolRef rendering.
# ---------------------------------------------------------------------------

def test_list_allocates_only_when_called_and_never_during_ticks():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.explosions = scene.world.sprite_pool("ship.png", count=2)
            scene.enemies = scene.world.sprite_pool("ship.png", count=6)
            scene.enemies.var("kind", 0, min=0, max=2)
            scene.enemies.behave(Damageable(explosion=scene.explosions))

        game = _build_scene(build)
        # 1000 ticks with no vs2beh command ever issued: behavior_control is
        # never invoked from the Step at all (director only reaches it from
        # _dispatch_control, driven by an in-band text command), so nothing
        # here should allocate on its behalf.
        for _ in range(1000):
            game.scene_step()
        sent, send = _send_capture()
        behavior_control.handle_command(["list"], send, scene=game)
        check("list produced exactly one line", len(sent) == 1)
        payload = _last_json(sent)
        check("list payload has a subjects list", "subjects" in payload)
    finally:
        _teardown()


def test_list_reports_pool_vars_behaviors_and_nested_action_params():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.explosions = scene.world.sprite_pool("ship.png", count=2)
            scene.enemies = scene.world.sprite_pool("ship.png", count=6)
            scene.enemies.var("kind", 0, min=0, max=2)
            scene.enemies.behave(Damageable(explosion=scene.explosions), name="damageable")

        game = _build_scene(build)
        sent, send = _send_capture()
        behavior_control.handle_command(["list"], send, scene=game)
        payload = _last_json(sent)

        enemies = _find_subject(payload, "enemies")
        check("enemies pool is listed", enemies is not None)
        check("enemies reports kind=pool", enemies["kind"] == "pool")
        check("enemies reports its declared capacity as count", enemies["count"] == 6)
        kind_var = _find_param(enemies["vars"], "kind")
        check("enemies.kind var is listed", kind_var is not None
              and kind_var["type"] == "number" and kind_var["value"] == 0
              and kind_var["min"] == 0 and kind_var["max"] == 2)

        damageable = _find_param(enemies["behaviors"], "damageable") \
            if False else next(
                (b for b in enemies["behaviors"] if b["name"] == "damageable"), None)
        check("damageable behavior is listed", damageable is not None)
        check("damageable class name is reported", damageable["class"] == "Damageable")
        hp = _find_param(damageable["params"], "hp")
        check("hp param default value is 1", hp is not None and hp["value"] == 1
              and hp["min"] == 1 and hp["max"] == 99 and hp["step"] == 1)
        explosion = _find_param(damageable["params"], "explosion")
        check("explosion PoolRef renders as the target pool's own name",
              explosion is not None and explosion["value"] == "explosions"
              and explosion["type"] == "pool")

        blink = next((a for a in damageable["actions"] if a["name"] == "blink"), None)
        check("the registered Blink action is named after its self.blink attribute",
              blink is not None)
        check("blink class name is reported", blink["class"] == "_Blink")
        on_ticks = _find_param(blink["params"], "on_ticks")
        check("nested action param on_ticks is listed",
              on_ticks is not None and on_ticks["value"] == 2)
    finally:
        _teardown()


def test_a_pool_with_neither_vars_nor_behaviors_is_not_listed():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.decor = scene.world.sprite_pool("ship.png", count=3)

        game = _build_scene(build)
        sent, send = _send_capture()
        behavior_control.handle_command(["list"], send, scene=game)
        payload = _last_json(sent)
        check("a pool with nothing to tune is omitted from list",
              _find_subject(payload, "decor") is None)
    finally:
        _teardown()


def test_a_pool_reachable_through_no_scene_attribute_is_not_addressable():
    """The second documented edge case in _discover_names: built and used
    only as a local variable inside build(), never assigned to self.<name>
    -- there is no name to address it by, so it is silently omitted."""
    _setup()
    try:
        local_pools = []

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            local_pool = scene.world.sprite_pool("ship.png", count=2)
            local_pool.var("hp", 5)
            local_pool.behave(Wobbler())
            local_pools.append(local_pool)

        game = _build_scene(build)
        sent, send = _send_capture()
        behavior_control.handle_command(["list"], send, scene=game)
        payload = _last_json(sent)
        check("an unassigned pool contributes no subject entry at all",
              len(payload["subjects"]) == 0)
    finally:
        _teardown()


def test_two_attributes_referencing_one_pool_use_the_first_sorted_name():
    """The first documented edge case: ambiguous aliasing resolves
    deterministically to whichever attribute name sorts first."""
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            pool = scene.world.sprite_pool("ship.png", count=2)
            pool.var("hp", 5)
            scene.zzz_alias = pool
            scene.aaa_first = pool

        game = _build_scene(build)
        sent, send = _send_capture()
        behavior_control.handle_command(["list"], send, scene=game)
        payload = _last_json(sent)
        check("only one subject entry exists for the aliased pool",
              len(payload["subjects"]) == 1)
        check("the alphabetically-first attribute name wins",
              payload["subjects"][0]["name"] == "aaa_first")
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# set: writes one attribute, visible on the next tick, no restart.
# ---------------------------------------------------------------------------

def test_set_writes_exactly_one_attribute_and_leaves_others_unchanged():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=6)
            scene.enemies.behave(Damageable(), name="damageable")

        game = _build_scene(build)
        behavior = game.enemies.behavior("damageable")
        sent, send = _send_capture()
        behavior_control.handle_command(
            ["set", "enemies.damageable.hp", "2"], send, scene=game)
        check("vs2beh_ok echoes the exact path=value",
              sent[-1] == b"vs2beh_ok enemies.damageable.hp=2")
        check("hp was written", behavior.hp == 2)
        check("score (a sibling param) is untouched", behavior.score == 40)
    finally:
        _teardown()


def test_set_is_visible_on_the_next_tick_with_no_restart():
    _setup()
    try:
        seen = []

        class ReadsHp(Behavior):
            hp = Number(1, min=1, max=99)

            def step(self, sprites):
                seen.append(self.hp)

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=1)
            scene.enemies.behave(ReadsHp(), name="reads_hp")

        game = _build_scene(build)
        game.scene_step()
        sent, send = _send_capture()
        behavior_control.handle_command(
            ["set", "enemies.reads_hp.hp", "7"], send, scene=game)
        game.scene_step()
        check("the Step before set() read the original default", seen[0] == 1)
        check("the very next Step after set() -- no restart -- reads the new value",
              seen[1] == 7)
    finally:
        _teardown()


def test_set_validates_out_of_range_via_the_declared_parameter():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=1)
            scene.enemies.behave(Damageable(), name="damageable")

        game = _build_scene(build)
        sent, send = _send_capture()
        behavior_control.handle_command(
            ["set", "enemies.damageable.hp", "999"], send, scene=game)
        check("an out-of-range set reports vs2beh_error",
              sent[-1].startswith(b"vs2beh_error"))
        check("the error names the declared range",
              b"1..99" in sent[-1])
        check("the invalid value was never written",
              game.enemies.behavior("damageable").hp == 1)
    finally:
        _teardown()


def test_set_on_a_nested_action_param():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=1)
            scene.enemies.behave(Damageable(), name="damageable")

        game = _build_scene(build)
        behavior = game.enemies.behavior("damageable")
        sent, send = _send_capture()
        behavior_control.handle_command(
            ["set", "enemies.damageable.blink.on_ticks", "4"], send, scene=game)
        check("vs2beh_ok for the nested action path",
              sent[-1] == b"vs2beh_ok enemies.damageable.blink.on_ticks=4")
        check("on_ticks was written on the live Blink Action instance",
              behavior.blink.on_ticks == 4)
    finally:
        _teardown()


def test_reset_restores_the_declared_default():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=1)
            scene.enemies.behave(Damageable(), name="damageable")

        game = _build_scene(build)
        behavior = game.enemies.behavior("damageable")
        sent, send = _send_capture()
        behavior_control.handle_command(
            ["set", "enemies.damageable.hp", "50"], send, scene=game)
        check("hp was changed away from its default", behavior.hp == 50)
        behavior_control.handle_command(
            ["reset", "enemies.damageable.hp"], send, scene=game)
        check("vs2beh_ok reports the restored default",
              sent[-1] == b"vs2beh_ok enemies.damageable.hp=1")
        check("hp is back to its declared default", behavior.hp == 1)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Scene and project variables ride the same protocol.
# ---------------------------------------------------------------------------

def test_scene_and_project_variables_are_listed_and_settable():
    _setup()
    try:
        vs2.project.var("high_score", 0, min=0, max=999999)

        def build(scene):
            scene.var("score", 0, min=0, max=999999)
            scene.world = scene.layer("world", projection=vs2.TUNNEL)

        game = _build_scene(build)
        sent, send = _send_capture()
        behavior_control.handle_command(["list"], send, scene=game)
        payload = _last_json(sent)
        scene_subject = _find_subject(payload, "scene")
        check("the scene itself is listed as a subject", scene_subject is not None)
        check("scene.score is one of its vars",
              _find_param(scene_subject["vars"], "score") is not None)
        project_subject = _find_subject(payload, "project")
        check("vs2.project is listed as its own subject", project_subject is not None)
        check("project.high_score is one of its vars",
              _find_param(project_subject["vars"], "high_score") is not None)

        behavior_control.handle_command(["set", "scene.score", "5"], send, scene=game)
        check("scene var set() echoes ok", sent[-1] == b"vs2beh_ok scene.score=5")
        check("the scene attribute itself changed", game.score == 5)

        behavior_control.handle_command(
            ["set", "project.high_score", "100"], send, scene=game)
        check("project var set() echoes ok",
              sent[-1] == b"vs2beh_ok project.high_score=100")
        check("vs2.project's own attribute changed", vs2.project.high_score == 100)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Var-bound parameters: shown, but not settable through this path.
# ---------------------------------------------------------------------------

def test_var_bound_parameter_is_shown_but_rejected_on_set():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=1)
            scene.enemies.var("speed_y", 1.0, min=0, max=8)
            scene.enemies.behave(Wobbler(speed_y=Var("speed_y")), name="wobbler")

        game = _build_scene(build)
        sent, send = _send_capture()
        behavior_control.handle_command(["list"], send, scene=game)
        payload = _last_json(sent)
        enemies = _find_subject(payload, "enemies")
        wobbler = next(b for b in enemies["behaviors"] if b["name"] == "wobbler")
        speed_y = _find_param(wobbler["params"], "speed_y")
        check("a Var-bound param renders as {'var': name} rather than a literal",
              speed_y["value"] == {"var": "speed_y"})

        behavior_control.handle_command(
            ["set", "enemies.wobbler.speed_y", "3"], send, scene=game)
        check("setting a Var-bound parameter directly is rejected",
              sent[-1].startswith(b"vs2beh_error"))
        check("the rejection names the instance variable to edit instead",
              b"speed_y" in sent[-1])
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Unknown path: names the closest valid one.
# ---------------------------------------------------------------------------

def test_unknown_path_names_the_closest_valid_one():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=1)
            scene.enemies.behave(Damageable(), name="damageable")

        game = _build_scene(build)
        sent, send = _send_capture()
        behavior_control.handle_command(
            ["set", "enemies.damagable.hp", "2"], send, scene=game)
        message = sent[-1].decode()
        check("the error names the typo'd path", "enemies.damagable.hp" in message)
        check("the error suggests the real path",
              "enemies.damageable.hp" in message)
    finally:
        _teardown()


def test_unknown_top_level_subject_is_also_reported_with_a_suggestion():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=1)
            scene.enemies.var("hp", 1)

        game = _build_scene(build)
        sent, send = _send_capture()
        behavior_control.handle_command(["set", "enemis.hp", "2"], send, scene=game)
        message = sent[-1].decode()
        check("an unknown subject name is reported",
              message.startswith("vs2beh_error unknown path"))
        check("the suggestion points at the real subject",
              "enemies.hp" in message)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# State machines: reading and forcing, via a hand-written stand-in for
# T10's StateMachine (a sibling Wave-5 task, not yet landed in this
# worktree -- see this task's report). Duck-typed against exactly the
# contract behavior_control.py relies on: a `states` tuple, a primed
# `fsm_state` byte per sprite, and enter_/exit_ hooks matched by name.
# ---------------------------------------------------------------------------

class _StubEnemyFSM(Behavior):
    """Minimal stand-in for T10's StateMachine -- see the module comment
    above. Primes fsm_state/fsm_hold by hand rather than via state=(...),
    since that declaration path reserves those exact names for T10's own
    priming mechanism (see vs2.StateConflictError)."""

    states = ("idle", "angry")
    initial = "idle"

    def __init__(self):
        Behavior.__init__(self)
        self.entered = []
        self.exited = []

    def attached(self, subject):
        if hasattr(subject, "_free"):
            for sprite in subject._free:
                sprite.fsm_state = 0
                sprite.fsm_hold = 0
            for sprite in subject._live:
                sprite.fsm_state = 0
                sprite.fsm_hold = 0
        else:
            subject.fsm_state = 0
            subject.fsm_hold = 0

    def enter_angry(self, sprite):
        self.entered.append("angry")

    def exit_idle(self, sprite):
        self.exited.append("idle")

    def step(self, sprites):
        pass

    def step_one(self, sprite):
        pass


def test_state_is_readable_from_list_and_reports_the_named_state():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=3)
            scene.enemies.spawn(0, 0)
            scene.enemies.behave(_StubEnemyFSM(), name="enemy")

        game = _build_scene(build)
        sent, send = _send_capture()
        behavior_control.handle_command(["list"], send, scene=game)
        payload = _last_json(sent)
        enemies = _find_subject(payload, "enemies")
        enemy = next(b for b in enemies["behaviors"] if b["name"] == "enemy")
        state = _find_param(enemy["params"], "state")
        check("a synthetic 'state' param is listed for a state-machine behavior",
              state is not None)
        check("it reports the primed initial state name", state["value"] == "idle")
        check("it lists every declared state as its options",
              state["options"] == ["idle", "angry"])
    finally:
        _teardown()


def test_state_can_be_forced_and_runs_the_enter_and_exit_hooks():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=3)
            scene.enemies.spawn(0, 0)
            scene.enemies.behave(_StubEnemyFSM(), name="enemy")

        game = _build_scene(build)
        behavior = game.enemies.behavior("enemy")
        sent, send = _send_capture()
        behavior_control.handle_command(
            ["set", "enemies.enemy.state", "angry"], send, scene=game)
        check("vs2beh_ok reports the forced state",
              sent[-1] == b"vs2beh_ok enemies.enemy.state=angry")
        check("the live sprite's fsm_state byte was written",
              game.enemies._live[0].fsm_state == 1)
        check("the outgoing state's exit hook ran", behavior.exited == ["idle"])
        check("the incoming state's enter hook ran", behavior.entered == ["angry"])
        check("any pending hold was cleared", game.enemies._live[0].fsm_hold == 0)

        behavior_control.handle_command(
            ["reset", "enemies.enemy.state"], send, scene=game)
        check("reset restores the declared initial state",
              sent[-1] == b"vs2beh_ok enemies.enemy.state=idle")
    finally:
        _teardown()


def test_forcing_an_unknown_state_name_is_rejected():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=1)
            scene.enemies.spawn(0, 0)
            scene.enemies.behave(_StubEnemyFSM(), name="enemy")

        game = _build_scene(build)
        sent, send = _send_capture()
        behavior_control.handle_command(
            ["set", "enemies.enemy.state", "furious"], send, scene=game)
        check("an unknown state name is rejected",
              sent[-1].startswith(b"vs2beh_error"))
        check("the rejection names the valid states",
              b"idle" in sent[-1] and b"angry" in sent[-1])
    finally:
        _teardown()


def test_state_on_a_lone_sprite_subject():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.boss = scene.world.sprite("ship.png")
            scene.boss.behave(_StubEnemyFSM(), name="enemy")

        game = _build_scene(build)
        sent, send = _send_capture()
        behavior_control.handle_command(
            ["set", "boss.enemy.state", "angry"], send, scene=game)
        check("state forces correctly on a lone-sprite subject",
              sent[-1] == b"vs2beh_ok boss.enemy.state=angry")
        check("the sprite's own fsm_state byte was written",
              game.boss.fsm_state == 1)
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Unsupported scenes fail cleanly rather than crashing the control loop.
# ---------------------------------------------------------------------------

def test_no_scene_reports_a_clean_error_rather_than_crashing():
    sent, send = _send_capture()
    behavior_control.handle_command(["list"], send, scene=None)
    check("no scene -> a clean vs2beh_error, not an exception",
          sent[-1].startswith(b"vs2beh_error"))


def test_a_non_vs2_scene_reports_a_clean_error():
    class NotVs2:
        pass

    sent, send = _send_capture()
    behavior_control.handle_command(["list"], send, scene=NotVs2())
    check("a non-vs2 scene -> a clean vs2beh_error, not an exception",
          sent[-1].startswith(b"vs2beh_error"))


# ---------------------------------------------------------------------------
# The one elif in director.py: end-to-end through _dispatch_control().
# ---------------------------------------------------------------------------

def test_director_dispatch_control_routes_vs2beh_to_the_handler():
    _setup()
    try:
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=1)
            scene.enemies.behave(Damageable(), name="damageable")

        game = _build_scene(build)
        behavior = game.enemies.behavior("damageable")
        sent = []
        original_send = director.platform.comms.send
        director.platform.comms.send = lambda data: sent.append(data)
        try:
            handled = director._dispatch_control("vs2beh set enemies.damageable.hp 9")
        finally:
            director.platform.comms.send = original_send
        check("_dispatch_control does not report a scene replacement",
              handled is None or handled is False)
        check("the vs2beh elif in director.py routed the command through",
              sent and sent[-1] == b"vs2beh_ok enemies.damageable.hp=9")
        check("the live behavior instance was actually written",
              behavior.hp == 9)
    finally:
        _teardown()


TESTS = [
    test_list_allocates_only_when_called_and_never_during_ticks,
    test_list_reports_pool_vars_behaviors_and_nested_action_params,
    test_a_pool_with_neither_vars_nor_behaviors_is_not_listed,
    test_a_pool_reachable_through_no_scene_attribute_is_not_addressable,
    test_two_attributes_referencing_one_pool_use_the_first_sorted_name,
    test_set_writes_exactly_one_attribute_and_leaves_others_unchanged,
    test_set_is_visible_on_the_next_tick_with_no_restart,
    test_set_validates_out_of_range_via_the_declared_parameter,
    test_set_on_a_nested_action_param,
    test_reset_restores_the_declared_default,
    test_scene_and_project_variables_are_listed_and_settable,
    test_var_bound_parameter_is_shown_but_rejected_on_set,
    test_unknown_path_names_the_closest_valid_one,
    test_unknown_top_level_subject_is_also_reported_with_a_suggestion,
    test_state_is_readable_from_list_and_reports_the_named_state,
    test_state_can_be_forced_and_runs_the_enter_and_exit_hooks,
    test_forcing_an_unknown_state_name_is_rejected,
    test_state_on_a_lone_sprite_subject,
    test_no_scene_reports_a_clean_error_rather_than_crashing,
    test_a_non_vs2_scene_reports_a_clean_error,
    test_director_dispatch_control_routes_vs2beh_to_the_handler,
]


def main():
    for test in TESTS:
        print("--- %s ---" % test.__name__)
        test()
    print("ALL PASS: %d checks" % len(TESTS))


if __name__ == "__main__":
    main()
