"""Test-only stand-in for T11's `vs2beh` device-side handler, used ONLY by
tests/test_vs2beh_live_tune_e2e.mjs to verify T12's panel logic against a
real, running MicroPython scene.

This is **not** apps/micropython/ventilastation/behavior_control.py --
that file is T11's own deliverable (a sibling Wave-5 task building the
`vs2beh` serial protocol; see docs/vs2-behaviors-implementation.md, T11 and
T12) and does not exist in this worktree, by design: T12 must not create
it (that would collide with T11's own work when the two branches merge).
This script lives under tests/fixtures/ specifically so it is never swept
by tests/run_tests.py's mpy-cross compile check (which only walks
apps/micropython/, system/ and games/) and is never mistaken for a shipped
module.

What this script actually proves: T12's browser-side protocol client
(web/vs2beh-client.js) and widget-dispatch logic (web/vs2-widgets.js) work
against *the real* vs2/behaviors.py, vs2/params.py and vs2/__init__.py
(Waves 1-4, already landed) driving a real headless `micropython`
process -- not a JS-side mock of what a device would say. It implements
just enough of the documented wire contract (docs/vs2-behaviors-
proposal.md, "## The live-tune loop") to exercise `list` and `set` against
one hand-written pool + Behavior, reusing the exact
`handle_command(parts, send, scene)`-shaped duck: parse a line, look a
path up through the real subject/behavior/param structure, mutate a real
instance attribute with a plain `setattr` (exactly how a live parameter
already works post-`init_params()` -- see vs2/params.py's module
docstring), and print a reply line.

Run standalone for a quick manual smoke check:

    micropython tests/fixtures/vs2beh_stub_scene.py <<'EOF'
    vs2beh list
    vs2beh set enemies.damageable.hp 7
    tick
    hp_log
    EOF

Protocol (line in on stdin, line out on stdout, flushed after every line):
    vs2beh list                        -> one line of JSON (subjects tree)
    vs2beh set <path> <value>          -> "vs2beh_ok <path>=<value>" or
                                           "vs2beh_error <message>"
    tick                                -> runs one scene_step(), replies "tick_ok"
    hp_log                              -> JSON array of every HP value
                                           Damageable.step() has observed so
                                           far, oldest first -- this is how
                                           the test proves a `set` takes
                                           effect on the very next tick with
                                           no restart.
"""

import os
import sys

sys.path.insert(0, "apps/micropython")

# uos/utime shims for CPython -- unused on MicroPython, where both modules
# already exist. Copied verbatim from tests/test_vs2_behaviors.py's own
# header, which documents the same need.
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

try:
    import ujson as json
except ImportError:
    import json

from ventilastation import api_guard  # noqa: E402
from ventilastation.director import configure_runtime, director, reset_runtime, stripes  # noqa: E402

import vs2  # noqa: E402
from vs2.behaviors import Behavior  # noqa: E402
from vs2.params import Number, introspect  # noqa: E402


# ---------------------------------------------------------------------------
# The hand-written game: one pool, one Behavior with tunable Number
# parameters, matching the proposal's own "enemies"/"damageable"/"hp"
# example almost exactly.
# ---------------------------------------------------------------------------

#: Every HP value Damageable.step() has observed, oldest first. This is the
#: test's window into "did the live-tuned value actually take effect on a
#: running scene object" -- not a log line, an actual read of the live
#: instance attribute a real Step would read.
HP_LOG = []


class Damageable(Behavior):
    hp = Number(1, min=1, max=99, step=1, label="HP")
    score = Number(40, min=0, max=9999, label="Score")

    def step(self, sprites):
        HP_LOG.append(self.hp)


def _setup():
    reset_runtime()
    api_guard.reset()
    runtime = configure_runtime("headless")
    stripes.clear()
    stripes["enemy.png"] = 0
    runtime.platform.sprites.stripes[0] = {
        "width": 4, "height": 4, "frames": 4, "palette": 0,
    }
    api_guard.begin_app("games.vs2beh_stub_fixture", "vs2")
    return runtime


_setup()


class Game(vs2.Scene):
    idle_timeout = None
    back_button = False

    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.enemies = self.world.sprite_pool("enemy.png", count=6)
        # Pool-level vars + kinds(), matching docs/vs2-behaviors-proposal.md's
        # own "### Kinds: per-type defaults as a table" example.
        self.enemies.var("hp", 1, min=0, max=99)
        self.enemies.var("score", 40, min=0, max=9999)
        self.enemies.kinds(driller=(3, 75), chiller=(1, 40), tank=(9, 120))
        # Behavior-level params -- what `vs2beh set enemies.damageable.hp 2`
        # actually addresses in the proposal's own sample.
        self.enemies.damageable = self.enemies.behave(Damageable())

    def update(self):
        pass


_GAME = Game()
director.push(_GAME)

#: name -> SpritePool, the fixture's own stand-in for whatever subject
#: registry T11's real handler will use. Hand-declared here (not derived
#: generically) because that discovery mechanism is T11's to design, not
#: this test fixture's.
SUBJECTS = {"enemies": _GAME.enemies}


# ---------------------------------------------------------------------------
# The test-only `vs2beh` stand-in.
# ---------------------------------------------------------------------------

def _param_json(name, type_name, value, metadata):
    entry = {"name": name, "type": type_name, "value": value}
    for key in ("min", "max", "step", "label", "unit", "options"):
        val = metadata.get(key)
        if val is not None:
            entry[key] = val
    return entry


def _pool_vars_json(pool):
    result = []
    for var_name in pool._var_order:
        param = pool._var_defaults[var_name]
        result.append(_param_json(var_name, param.type_name, param.default, param.metadata()))
    return result


def _pool_kinds_json(pool):
    if not pool._kind_rows:
        return None
    # pool._kind_rows is a plain dict -- MicroPython's dict does not
    # preserve insertion order (see vs2/__init__.py's own comment on
    # SpritePool._var_order explaining exactly this hazard for var names).
    # Sorting by kind name here is this stub's deterministic choice, not
    # something vs2/__init__.py guarantees; a real T11 implementation
    # will need its own explicit order (e.g. tracking declaration order
    # the same way _var_order does) if the *originally authored* row
    # order ever needs to survive the wire, rather than an alphabetical
    # one.
    fields = list(pool._kind_fields)
    rows = [
        {"name": kind_name, "values": list(pool._kind_rows[kind_name])}
        for kind_name in sorted(pool._kind_rows.keys())
    ]
    return {"fields": fields, "rows": rows}


def _behaviors_json(pool):
    result = []
    for name, behavior in pool._behaviors.items():
        params_list = []
        for pname, type_name, _default, metadata in introspect(type(behavior)):
            value = getattr(behavior, pname)
            params_list.append(_param_json(pname, type_name, value, metadata))
        result.append({
            "name": name,
            "class": type(behavior).__name__,
            "params": params_list,
            "actions": [],
        })
    return result


def _handle_list():
    subjects = []
    for name, pool in SUBJECTS.items():
        entry = {
            "name": name,
            "kind": "pool",
            "count": len(pool),
            "vars": _pool_vars_json(pool),
            "behaviors": _behaviors_json(pool),
        }
        kinds = _pool_kinds_json(pool)
        if kinds is not None:
            entry["kinds"] = kinds
        subjects.append(entry)
    return json.dumps({"subjects": subjects})


def _coerce(raw):
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    if raw == "true":
        return True
    if raw == "false":
        return False
    return raw


def _handle_set(path, raw_value):
    parts = path.split(".")
    if len(parts) < 2:
        return "vs2beh_error malformed path %r" % (path,)
    pool = SUBJECTS.get(parts[0])
    if pool is None:
        return "vs2beh_error unknown subject %r; valid: %s" % (
            parts[0], ", ".join(sorted(SUBJECTS.keys())))
    value = _coerce(raw_value)
    if len(parts) == 2:
        var_name = parts[1]
        if var_name not in pool._var_defaults:
            return "vs2beh_error unknown var %r on %r" % (var_name, parts[0])
        for sprite in pool._live:
            setattr(sprite, var_name, value)
        for sprite in pool._free:
            setattr(sprite, var_name, value)
        return "vs2beh_ok %s=%s" % (path, raw_value)
    if len(parts) == 3:
        behavior_name, param_name = parts[1], parts[2]
        behavior = pool._behaviors.get(behavior_name)
        if behavior is None:
            return "vs2beh_error unknown behavior %r on %r" % (behavior_name, parts[0])
        if not hasattr(behavior, param_name):
            return "vs2beh_error unknown param %r on %r" % (param_name, behavior_name)
        # The live-tune contract in one line: a declared parameter is
        # already a plain instance attribute after init_params() ran (see
        # vs2/params.py's module docstring on non-data descriptors), so
        # "set" is exactly this -- an ordinary setattr, visible to the
        # very next Step with no restart.
        setattr(behavior, param_name, value)
        return "vs2beh_ok %s=%s" % (path, raw_value)
    return "vs2beh_error unsupported path %r" % (path,)


def _main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        if line == "tick":
            _GAME.scene_step()
            print("tick_ok")
        elif line == "hp_log":
            print(json.dumps(HP_LOG))
        elif line.startswith("vs2beh "):
            rest = line[len("vs2beh "):]
            parts = rest.split()
            sub = parts[0] if parts else ""
            if sub == "list":
                print(_handle_list())
            elif sub == "set" and len(parts) == 3:
                print(_handle_set(parts[1], parts[2]))
            else:
                print("vs2beh_error unknown subcommand %r" % (sub,))
        else:
            print("vs2beh_error unknown command %r" % (line,))
        sys.stdout.flush()


if __name__ == "__main__":
    _main()
