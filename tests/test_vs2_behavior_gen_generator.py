"""Tests for tools/vs2_behavior_gen/generator.py -- model -> generated
``Behavior`` subclass source, the checksum/hand-edit/Detach round-trip, and
-- the real acceptance bar this task's dispatch card sets -- building
``Projectile`` from blocks, generating its ``.py``, and running it through
the *exact same* behavioral checks ``tests/test_vs2_behaviors.py`` already
runs against the real, hand-written ``Projectile``: the hoisted ``Move``,
despawn past ``range``, and despawn on a ``Collide`` hit.

Two test classes:

- ``RoundTripTests`` -- pure text-level generator mechanics, pure CPython,
  no ``vs2`` import, mirroring ``tests/test_vs2_scene_gen_generator.py``/
  ``tests/test_vs2_event_gen.py``'s own structure.
- ``GeneratedProjectileBehaviorTests`` -- imports the real ``vs2`` package
  (the same ``uos``/``utime`` CPython shims ``tests/test_vs2_behaviors.py``
  installs), writes the generated source to a real temp file, imports it
  with ``importlib``, and runs it through a real ``vs2.Scene``. Not
  byte-identical to the hand-written ``Projectile`` (different authoring
  path, different local variable names inside the generated ``if``/``else``
  -- see ``generator.py``'s own docstring on why the loop shape is copied
  verbatim while the per-sprite body is generated) -- proven *behaviorally*
  equivalent instead, which is what the dispatch card actually asks for.

Run: ``python3 tests/test_vs2_behavior_gen_generator.py``
"""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.vs2_behavior_gen import build_behavior, checksum, detach, generator
from tools.vs2_behavior_gen.model import ModelError


def _param(name, type_="number", default=0, **extra):
    entry = {"name": name, "type": type_, "default": default}
    entry.update(extra)
    return entry


def _param_ref(name):
    return {"kind": "param", "name": name}


def _state_ref(name):
    return {"kind": "state", "name": name}


def projectile_model():
    """The block-program model for ``Projectile``, expressed exactly the
    way an author composing the two-zone tick skeleton in the block editor
    would produce it (see ``model.py``'s own module docstring, which shows
    this identical model as its worked example)."""
    return {
        "version": 1,
        "class_name": "GeneratedProjectile",
        "subject_kind": "pool",
        "params": [
            _param("speed_x", "angle", 0, min=-32, max=32, step=0.25,
                   label="Angular speed", unit="col/tick"),
            _param("speed_y", "number", 8, min=-32, max=32, step=0.25,
                   label="Radial speed", unit="led/tick"),
            _param("range", "number", 180, min=1, max=255, step=1,
                   label="Range", unit="led"),
            _param("hits", "pool", None, label="Hits what"),
        ],
        "state": ["shot_flown"],
        "actions": [
            {"bind": "move", "action_class": "Move",
             "args": {"speed_x": _param_ref("speed_x"), "speed_y": _param_ref("speed_y")}},
            {"bind": "hit", "action_class": "Collide",
             "args": {"targets": _param_ref("hits")}},
        ],
        "apply_to_all": ["move"],
        "per_sprite": [
            {"kind": "accumulate", "state": "shot_flown", "amount": _param_ref("speed_y")},
            {"kind": "if_else",
             "condition": {"kind": "compare", "op": ">",
                            "left": _state_ref("shot_flown"), "right": _param_ref("range")},
             "then": [{"kind": "despawn"}],
             "else": [{"kind": "if_action", "bind": "hit",
                        "then": [{"kind": "despawn_hit"}, {"kind": "despawn"}], "else": []}]},
        ],
    }


def damageable_model():
    """The Damageable reference model -- see test_vs2_behavior_gen_model.py's
    own ``_damageable_model`` (kept independent per this file's own
    precedent) and this task's report for the full design reasoning."""
    return {
        "version": 1,
        "class_name": "GeneratedDamageable",
        "subject_kind": "pool",
        "params": [
            _param("hp", "number", 1, min=1, max=99, step=1, label="Hit points"),
            _param("invulnerable_ticks", "number", 0, min=0, max=255, step=1,
                   label="Invulnerability", unit="tick"),
            _param("blink", "flag", False, label="Hide while invulnerable"),
            _param("explosion", "pool", None, label="Explosion pool"),
            _param("sound", "sound", None, label="Sound on death"),
            _param("score", "number", 0, min=0, max=9999, label="Points on death"),
            _param("on_death", "callback", None, label="On death"),
            _param("hits", "pool", None, label="Damaged by"),
        ],
        "state": ["damage_taken", "invuln_left"],
        "actions": [
            {"bind": "hit", "action_class": "Collide", "args": {"targets": _param_ref("hits")}},
        ],
        "apply_to_all": [],
        "per_sprite": [
            # One top-level if/else -- see test_vs2_behavior_gen_model.py's
            # own _damageable_model docstring comment for why "still
            # invulnerable" and "check for a fresh hit" must be mutually
            # exclusive branches of the SAME node, not two independent
            # top-level nodes (a hit that sets invuln_left this tick must
            # not also get decremented by a second node right after).
            {"kind": "if_else",
             "condition": {"kind": "compare", "op": ">",
                            "left": _state_ref("invuln_left"), "right": {"kind": "literal", "value": 0}},
             "then": [
                 {"kind": "accumulate", "state": "invuln_left",
                  "amount": {"kind": "literal", "value": -1}},
                 {"kind": "if_else",
                  "condition": {"kind": "compare", "op": "<=",
                                 "left": _state_ref("invuln_left"), "right": {"kind": "literal", "value": 0}},
                  "then": [
                      {"kind": "if_else",
                       "condition": {"kind": "compare", "op": "==",
                                      "left": _param_ref("blink"), "right": {"kind": "literal", "value": True}},
                       "then": [{"kind": "set_state", "state": "visible",
                                 "value": {"kind": "literal", "value": True}}],
                       "else": []},
                  ],
                  "else": []},
             ],
             "else": [
                 {"kind": "if_action", "bind": "hit",
                  "then": [
                      {"kind": "accumulate", "state": "damage_taken",
                       "amount": {"kind": "literal", "value": 1}},
                      {"kind": "set_state", "state": "invuln_left",
                       "value": _param_ref("invulnerable_ticks")},
                      {"kind": "if_else",
                       "condition": {"kind": "compare", "op": "==",
                                      "left": _param_ref("blink"), "right": {"kind": "literal", "value": True}},
                       "then": [{"kind": "set_state", "state": "visible",
                                 "value": {"kind": "literal", "value": False}}],
                       "else": []},
                      {"kind": "if_else",
                       "condition": {"kind": "compare", "op": ">=",
                                      "left": _state_ref("damage_taken"), "right": _param_ref("hp")},
                       "then": [
                           {"kind": "call_callback", "name": "on_death",
                            "args": [_param_ref("score")]},
                           {"kind": "play_sound", "name": "sound"},
                           {"kind": "spawn", "pool": "explosion",
                            "x": _state_ref("x"), "y": _state_ref("y")},
                           {"kind": "despawn"},
                       ],
                       "else": []},
                  ],
                  "else": []},
             ]},
        ],
    }


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="vs2_behavior_gen_test_"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_generate_source_has_the_banner_body_blob_shape(self):
        text = generator.generate_source(projectile_model(), "generated_projectile.py")
        parsed = checksum.split_generated_file(text)
        self.assertIsNotNone(parsed)
        banner_line, body, blob_line = parsed
        self.assertEqual(checksum.recorded_sha(banner_line), checksum.body_sha(body))
        self.assertIn("class GeneratedProjectile(Behavior):", body)
        self.assertIn("def step(self, sprites):", body)
        self.assertTrue(blob_line.startswith("# behavior-blocks: "))

    def test_uses_its_own_third_blob_prefix_not_the_other_two_generators(self):
        text = generator.generate_source(projectile_model(), "x.py")
        self.assertIn("# behavior-blocks: ", text)
        self.assertNotIn("\n# scene-model: ", text)
        self.assertNotIn("\n# blocks: ", text)

    def test_regenerating_an_unchanged_model_is_byte_identical(self):
        model = projectile_model()
        first = generator.generate_source(model, "x.py")
        second = generator.generate_source(model, "x.py")
        self.assertEqual(first, second)

    def test_fixture_matches_current_generator_output(self):
        """tests/fixtures/generated_projectile_fixture.py is a checked-in
        copy of one real generate_source() run, not generated at test
        time -- see tests/test_vs2_behavior_gen_micropython.py's own
        docstring for why (the generator itself isn't guaranteed
        MicroPython-importable, so that test needs a fixture it doesn't
        have to generate on the fly). This guards against that fixture
        silently drifting out of sync with what the generator actually
        produces today -- a failure here means regenerate the fixture,
        not edit this assertion."""
        fixture_path = Path(ROOT) / "tests" / "fixtures" / "generated_projectile_fixture.py"
        current = generator.generate_source(projectile_model(), fixture_path.name)
        self.assertEqual(
            fixture_path.read_text(), current,
            "regenerate tests/fixtures/generated_projectile_fixture.py from "
            "the current generator (see this test's docstring)")

    def test_blob_round_trips_the_exact_model(self):
        from tools.vs2_scene_gen.blob import decode_blob
        model = projectile_model()
        text = generator.generate_source(model, "x.py")
        _banner, _body, blob_line = checksum.split_generated_file(text)
        decoded = decode_blob(checksum.blob_data(blob_line))
        self.assertEqual(decoded, model)

    def test_invalid_model_raises_model_error(self):
        model = projectile_model()
        model["subject_kind"] = "nonsense"
        with self.assertRaises(ModelError):
            generator.generate_source(model, "x.py")

    def test_write_behavior_file_created_then_unchanged(self):
        path = self.tmpdir / "generated_projectile.py"
        first = generator.write_behavior_file(projectile_model(), path)
        self.assertEqual(first.status, "created")
        second = generator.write_behavior_file(projectile_model(), path)
        self.assertEqual(second.status, "unchanged")

    def test_write_behavior_file_updates_on_a_model_change(self):
        path = self.tmpdir / "generated_projectile.py"
        generator.write_behavior_file(projectile_model(), path)
        changed = projectile_model()
        changed["params"][2]["default"] = 220  # range
        result = generator.write_behavior_file(changed, path)
        self.assertEqual(result.status, "updated")
        self.assertIn("range = Number(220", path.read_text())

    def test_write_behavior_file_detects_hand_edit(self):
        path = self.tmpdir / "generated_projectile.py"
        generator.write_behavior_file(projectile_model(), path)
        text = path.read_text()
        path.write_text(text.replace("range", "distance"))
        result = generator.write_behavior_file(projectile_model(), path)
        self.assertEqual(result.status, "hand_edited")
        # and the file on disk was left untouched by the refused write
        self.assertIn("distance", path.read_text())

    def test_write_behavior_file_reports_detached_file_as_not_ours(self):
        path = self.tmpdir / "generated_projectile.py"
        path.write_text("class GeneratedProjectile:\n    pass\n")
        result = generator.write_behavior_file(projectile_model(), path)
        self.assertEqual(result.status, "detached")
        # left untouched
        self.assertEqual(path.read_text(), "class GeneratedProjectile:\n    pass\n")

    def test_detach_strips_banner_and_blob_one_way(self):
        path = self.tmpdir / "generated_projectile.py"
        generator.write_behavior_file(projectile_model(), path)
        detached_text = detach.detach_file(path)
        self.assertNotIn("behavior-blocks", detached_text)
        self.assertNotIn("generated, do not edit", detached_text)
        self.assertTrue(detach.is_generated(path.read_text()) is False)
        # regenerating no longer touches this file's shape at all -- it's
        # not generator-managed any more.
        result = generator.write_behavior_file(projectile_model(), path)
        self.assertEqual(result.status, "detached")

    def test_sprite_subject_kind_generates_step_one_with_no_loop(self):
        model = projectile_model()
        model["subject_kind"] = "sprite"
        text = generator.generate_source(model, "x.py")
        self.assertIn("def step_one(self, sprite):", text)
        self.assertNotIn("sprites._live", text)
        self.assertIn("self.move.run_one(sprite)", text)


def state_machine_model():
    """Same small state-hat model as test_vs2_behavior_gen_model.py's own
    ``_state_machine_model`` (kept independent, matching this file's own
    top-level ``projectile_model`` precedent rather than importing across
    test files)."""
    return {
        "version": 1,
        "class_name": "GeneratedEnemy",
        "subject_kind": "pool",
        "params": [
            _param("ground_y", "number", 100),
            _param("explosion", "pool", None),
            _param("sound", "sound", None),
            _param("on_death", "callback", None),
            _param("hits", "pool", None),
        ],
        "state": ["frames_left"],
        "actions": [
            {"bind": "hit", "action_class": "Collide",
             "args": {"targets": _param_ref("hits")}},
        ],
        "apply_to_all": [],
        "per_sprite": [],
        "state_machine": {
            "states": ["orbiting", "falling", "exploding"],
            "initial": "orbiting",
            "bodies": {
                "orbiting": {
                    "enter": [{"kind": "hold", "ticks": {"kind": "literal", "value": 3},
                               "then": "falling"}],
                    "step": [{"kind": "if_action", "bind": "hit",
                              "then": [{"kind": "goto_state", "name": "exploding"}],
                              "else": []}],
                },
                "falling": {
                    "step": [
                        {"kind": "accumulate", "state": "frames_left",
                         "amount": {"kind": "literal", "value": 1}},
                        {"kind": "if_else",
                         "condition": {"kind": "compare", "op": ">=",
                                        "left": _state_ref("y"), "right": _param_ref("ground_y")},
                         "then": [{"kind": "goto_state", "name": "exploding"}], "else": []},
                    ],
                },
                "exploding": {
                    "enter": [
                        {"kind": "play_sound", "name": "sound"},
                        {"kind": "spawn", "pool": "explosion",
                         "x": _state_ref("x"), "y": _state_ref("y")},
                        {"kind": "call_callback", "name": "on_death", "args": []},
                    ],
                    "step": [{"kind": "despawn"}],
                    "exit": [{"kind": "set_state", "state": "frames_left",
                              "value": {"kind": "literal", "value": 0}}],
                },
            },
        },
    }


class StateHatRoundTripTests(unittest.TestCase):
    """Phase 2: model.state_machine -> a StateMachine subclass, pure text
    mechanics, mirroring RoundTripTests above."""

    def test_generates_a_statemachine_subclass_not_a_behavior(self):
        text = generator.generate_source(state_machine_model(), "generated_enemy.py")
        self.assertIn("from vs2.behaviors import StateMachine", text)
        self.assertIn("class GeneratedEnemy(StateMachine):", text)
        self.assertNotIn("class GeneratedEnemy(Behavior):", text)

    def test_no_step_or_step_one_generated_at_all(self):
        """Every bit of dispatch is inherited from the real StateMachine --
        see generator.py's own "Phase 2" docstring section."""
        text = generator.generate_source(state_machine_model(), "x.py")
        self.assertNotIn("def step(self", text)
        self.assertNotIn("def step_one(self", text)

    def test_states_and_initial_are_plain_class_attributes(self):
        text = generator.generate_source(state_machine_model(), "x.py")
        self.assertIn("    states = ('orbiting', 'falling', 'exploding')", text)
        self.assertIn("    initial = 'orbiting'", text)

    def test_attached_calls_the_base_class_explicitly_not_via_super(self):
        """Composing Actions still needs the base class's own fsm-priming
        to run -- spelled as the real StateMachine docstring instructs
        (StateMachine.attached(self, subject)), never super(), matching
        this module's own docstring on the MicroPython super() gotcha."""
        text = generator.generate_source(state_machine_model(), "x.py")
        self.assertIn("    def attached(self, subject):", text)
        self.assertIn("        StateMachine.attached(self, subject)", text)
        self.assertNotIn("super()", text)

    def test_attached_omitted_entirely_when_no_actions_declared(self):
        """No Actions to compose -> no attached() override at all, so the
        base StateMachine.attached (fsm priming) runs unmodified -- see
        _render_state_machine_attached's own docstring."""
        model = state_machine_model()
        model["actions"] = []
        # "orbiting" used the "hit" action via if_action; drop that too,
        # since removing the action declaration alone would leave a
        # dangling bind reference.
        model["state_machine"]["bodies"]["orbiting"] = {
            "enter": model["state_machine"]["bodies"]["orbiting"]["enter"],
            "step": [],
        }
        text = generator.generate_source(model, "x.py")
        self.assertNotIn("def attached(self", text)

    def test_enter_and_exit_hooks_only_generated_when_declared(self):
        text = generator.generate_source(state_machine_model(), "x.py")
        self.assertIn("    def enter_orbiting(self, sprite):", text)
        self.assertIn("    def enter_exploding(self, sprite):", text)
        self.assertIn("    def exit_exploding(self, sprite):", text)
        # "falling" declares neither hook
        self.assertNotIn("def enter_falling(self", text)
        self.assertNotIn("def exit_falling(self", text)

    def test_goto_state_renders_a_plain_return(self):
        text = generator.generate_source(state_machine_model(), "x.py")
        self.assertIn("        return 'exploding'", text)

    def test_hold_renders_the_real_hold_call(self):
        text = generator.generate_source(state_machine_model(), "x.py")
        self.assertIn("self.hold(sprite, 3, then='falling')", text)

    def test_play_sound_imports_audio_and_choose_sound(self):
        text = generator.generate_source(state_machine_model(), "x.py")
        self.assertIn("from vs2 import audio", text)
        self.assertIn("from vs2.behaviors import StateMachine, _choose_sound", text)
        self.assertIn("audio.sound(_choose_sound(_sound_sound))", text)

    def test_play_sound_import_omitted_when_unused(self):
        model = projectile_model()
        text = generator.generate_source(model, "x.py")
        self.assertNotIn("_choose_sound", text)
        self.assertNotIn("from vs2 import audio", text)

    def test_spawn_renders_a_guarded_pool_spawn_call(self):
        text = generator.generate_source(state_machine_model(), "x.py")
        self.assertIn("_spawn_explosion = self.explosion", text)
        self.assertIn("if _spawn_explosion is not None:", text)
        self.assertIn("_spawn_explosion.spawn(sprite.x, sprite.y)", text)

    def test_call_callback_renders_a_guarded_call_with_sprite_first(self):
        text = generator.generate_source(state_machine_model(), "x.py")
        self.assertIn("_cb_on_death = self.on_death", text)
        self.assertIn("if _cb_on_death is not None:", text)
        self.assertIn("_cb_on_death(sprite)", text)

    def test_set_state_renders_a_plain_assignment(self):
        text = generator.generate_source(state_machine_model(), "x.py")
        self.assertIn("sprite.frames_left = 0", text)

    def test_fixture_matches_current_generator_output(self):
        """tests/fixtures/generated_enemy_fixture.py, mirroring
        RoundTripTests's own identical check for Projectile -- see that
        test's docstring for why a checked-in fixture exists at all."""
        fixture_path = Path(ROOT) / "tests" / "fixtures" / "generated_enemy_fixture.py"
        current = generator.generate_source(state_machine_model(), fixture_path.name)
        self.assertEqual(
            fixture_path.read_text(), current,
            "regenerate tests/fixtures/generated_enemy_fixture.py from "
            "the current generator")

    def test_blob_round_trips_the_exact_state_machine_model(self):
        from tools.vs2_scene_gen.blob import decode_blob
        model = state_machine_model()
        text = generator.generate_source(model, "x.py")
        _banner, _body, blob_line = checksum.split_generated_file(text)
        decoded = decode_blob(checksum.blob_data(blob_line))
        self.assertEqual(decoded, model)


# ---------------------------------------------------------------------------
# The real acceptance bar: import the real vs2 package, build a scene, run
# the GENERATED Projectile through the exact same assertions
# tests/test_vs2_behaviors.py runs against the HAND-WRITTEN one.
# ---------------------------------------------------------------------------

MICROPYTHON_ROOT = str(Path(ROOT) / "apps" / "micropython")
if MICROPYTHON_ROOT not in sys.path:
    sys.path.insert(0, MICROPYTHON_ROOT)

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

import gc  # noqa: E402

import vs2  # noqa: E402
from ventilastation import api_guard  # noqa: E402
from ventilastation.director import configure_runtime, director, reset_runtime, stripes  # noqa: E402


def _load_generated_class(model, tmpdir, basename="generated_projectile.py"):
    """Write ``model``'s generated source to a real file under ``tmpdir``
    and import it with ``importlib`` -- proving the generator's *actual
    file output* runs, not merely the in-memory ``render_body()`` string."""
    path = Path(tmpdir) / basename
    generator.write_behavior_file(model, path)
    module_name = "vs2_behavior_gen_test_" + basename[:-3]
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, model["class_name"])


class GeneratedProjectileBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="vs2_behavior_gen_exec_test_")
        reset_runtime()
        api_guard.reset()
        self.runtime = configure_runtime("headless")
        stripes.clear()
        stripes["ship.png"] = 0
        self.runtime.platform.sprites.stripes[0] = {
            "width": 4, "height": 4, "frames": 4, "palette": 0,
        }
        api_guard.begin_app("games.test_vs2_behavior_gen", "vs2")
        self.GeneratedProjectile = _load_generated_class(projectile_model(), self.tmpdir)

    def tearDown(self):
        reset_runtime()
        api_guard.reset()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_scene(self, build_fn):
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

    def test_generated_class_is_a_real_behavior_subclass(self):
        from vs2.behaviors import Behavior
        self.assertTrue(issubclass(self.GeneratedProjectile, Behavior))

    def test_moves_via_the_hoisted_move_action(self):
        """Mirrors tests/test_vs2_behaviors.py's
        test_projectile_moves_via_the_hoisted_move_action exactly, against
        the generated class instead of the hand-written one."""
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.shots = scene.world.sprite_pool("ship.png", count=2)
            scene.targets = scene.world.sprite_pool("ship.png", count=1)
            scene.shots.behave(self.GeneratedProjectile(
                speed_x=1, speed_y=2, range=200, hits=scene.targets))
            scene.shots.spawn(10, 10)

        game = self._build_scene(build)
        behavior = game.shots.behavior(self.GeneratedProjectile)
        behavior.step(game.shots)
        sprite = game.shots._live[0]
        self.assertEqual(sprite.dx, 1)
        self.assertEqual(sprite.dy, 2)
        self.assertEqual(sprite.shot_flown, 2)

    def test_despawns_past_its_range(self):
        """Mirrors test_projectile_despawns_past_its_range."""
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.shots = scene.world.sprite_pool("ship.png", count=1)
            scene.targets = scene.world.sprite_pool("ship.png", count=1)
            scene.shots.behave(self.GeneratedProjectile(
                speed_x=0, speed_y=10, range=25, hits=scene.targets))
            scene.shots.spawn(0, 0)

        game = self._build_scene(build)
        behavior = game.shots.behavior(self.GeneratedProjectile)
        for _ in range(3):
            behavior.step(game.shots)
        self.assertEqual(len(game.shots), 0)

    def test_despawns_both_sprites_on_a_hit(self):
        """Mirrors test_projectile_despawns_both_sprites_on_a_hit."""
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.shots = scene.world.sprite_pool("ship.png", count=1)
            scene.targets = scene.world.sprite_pool("ship.png", count=1)
            scene.shots.behave(self.GeneratedProjectile(
                speed_x=0, speed_y=0, range=200, hits=scene.targets))
            scene.shots.spawn(10, 10)
            scene.targets.spawn(10, 10)  # exactly overlapping

        game = self._build_scene(build)
        behavior = game.shots.behavior(self.GeneratedProjectile)
        behavior.step(game.shots)
        self.assertEqual(len(game.shots), 0)
        self.assertEqual(len(game.targets), 0)

    def test_does_not_despawn_or_hit_when_neither_condition_is_met(self):
        """A case the three mirrored tests above don't cover on their own:
        proves the if/else split is real (the Collide branch is only
        reached when the range branch is NOT taken), not an artifact of
        each test only ever exercising one arm."""
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.shots = scene.world.sprite_pool("ship.png", count=1)
            scene.targets = scene.world.sprite_pool("ship.png", count=1)
            scene.shots.behave(self.GeneratedProjectile(
                speed_x=0, speed_y=1, range=200, hits=scene.targets))
            scene.shots.spawn(0, 0)
            scene.targets.spawn(100, 100)  # far away: never hit

        game = self._build_scene(build)
        behavior = game.shots.behavior(self.GeneratedProjectile)
        for _ in range(5):
            behavior.step(game.shots)
        self.assertEqual(len(game.shots), 1)
        self.assertEqual(len(game.targets), 1)
        self.assertEqual(game.shots._live[0].shot_flown, 5)

    def test_zero_allocation_over_1000_steps(self):
        """The same allocation-regression shape every Behavior test in this
        repo uses (tests/test_vs2_behaviors.py's own
        test_scene_with_projectile_over_100_sprites_..., trimmed to one
        sprite + one target since this is a generator smoke test, not a
        fresh benchmark)."""
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.shots = scene.world.sprite_pool("ship.png", count=1)
            scene.targets = scene.world.sprite_pool("ship.png", count=1)
            scene.shots.behave(self.GeneratedProjectile(
                speed_x=0, speed_y=-0.25, range=255, hits=scene.targets))
            scene.shots.spawn(0, 0)
            scene.targets.spawn(250, 250)  # far away: Collide never hits

        game = self._build_scene(build)
        for _ in range(50):
            game.scene_step()  # warm up any one-time caches

        try:
            gc.mem_free()
        except AttributeError:
            self.skipTest("gc.mem_free() unavailable (this is CPython, not MicroPython)")

        gc.collect()
        before = gc.mem_free()
        for _ in range(1000):
            game.scene_step()
        gc.collect()
        after = gc.mem_free()
        self.assertGreaterEqual(after, before - 4096)


class GeneratedStateMachineBehaviorTests(unittest.TestCase):
    """The state-hat equivalent of GeneratedProjectileBehaviorTests above:
    the generated GeneratedEnemy actually attached to a real vs2.Scene,
    real dispatch (StateMachine.step, inherited unmodified -- see this
    class's own docstring), a real hold()-driven timed transition, a real
    Collide-driven early exit, and a real despawn+spawn+callback on death."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="vs2_behavior_gen_sm_test_")
        reset_runtime()
        api_guard.reset()
        self.runtime = configure_runtime("headless")
        stripes.clear()
        stripes["ship.png"] = 0
        self.runtime.platform.sprites.stripes[0] = {
            "width": 4, "height": 4, "frames": 4, "palette": 0,
        }
        api_guard.begin_app("games.test_vs2_behavior_gen", "vs2")
        self.GeneratedEnemy = _load_generated_class(
            state_machine_model(), self.tmpdir, basename="generated_enemy.py")

    def tearDown(self):
        reset_runtime()
        api_guard.reset()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_scene(self, build_fn):
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

    def test_generated_class_is_a_real_statemachine_subclass(self):
        from vs2.behaviors import StateMachine
        self.assertTrue(issubclass(self.GeneratedEnemy, StateMachine))

    def test_starts_in_the_declared_initial_state(self):
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=1)
            scene.targets = scene.world.sprite_pool("ship.png", count=1)
            scene.explosions = scene.world.sprite_pool("ship.png", count=1)
            scene.enemies.behave(self.GeneratedEnemy(
                ground_y=50, explosion=scene.explosions, hits=scene.targets))
            scene.enemies.spawn(10, 10)

        game = self._build_scene(build)
        behavior = game.enemies.behavior(self.GeneratedEnemy)
        sprite = game.enemies._live[0]
        self.assertEqual(behavior.state_name(sprite), "orbiting")

    def test_hold_transitions_to_falling_after_its_configured_ticks(self):
        """enter_orbiting calls self.hold(sprite, 3, then='falling') --
        the sprite stays in 'orbiting' for exactly 3 step()s (nothing else
        forces an earlier exit: the target is far away, never hit), then
        the 4th step lands in 'falling'."""
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=1)
            scene.targets = scene.world.sprite_pool("ship.png", count=1)
            scene.explosions = scene.world.sprite_pool("ship.png", count=1)
            scene.enemies.behave(self.GeneratedEnemy(
                ground_y=50, explosion=scene.explosions, hits=scene.targets))
            scene.enemies.spawn(10, 10)
            scene.targets.spawn(200, 200)  # far away: never hit

        game = self._build_scene(build)
        behavior = game.enemies.behavior(self.GeneratedEnemy)
        sprite = game.enemies._live[0]
        for _ in range(3):
            self.assertEqual(behavior.state_name(sprite), "orbiting")
            behavior.step(game.enemies)
        self.assertEqual(behavior.state_name(sprite), "falling")

    def test_collide_short_circuits_the_hold_into_exploding(self):
        """orbiting's own step body (not enter_orbiting's hold) checks the
        bound Collide action every tick, via if_action -- overlapping the
        target skips the hold entirely."""
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=1)
            scene.targets = scene.world.sprite_pool("ship.png", count=1)
            scene.explosions = scene.world.sprite_pool("ship.png", count=1)
            scene.enemies.behave(self.GeneratedEnemy(
                ground_y=50, explosion=scene.explosions, hits=scene.targets))
            scene.enemies.spawn(10, 10)
            scene.targets.spawn(10, 10)  # exactly overlapping: hit on tick 1

        game = self._build_scene(build)
        behavior = game.enemies.behavior(self.GeneratedEnemy)
        sprite = game.enemies._live[0]
        behavior.step(game.enemies)
        self.assertEqual(behavior.state_name(sprite), "exploding")

    def test_falling_transitions_to_exploding_past_ground_y(self):
        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=1)
            scene.targets = scene.world.sprite_pool("ship.png", count=1)
            scene.explosions = scene.world.sprite_pool("ship.png", count=1)
            scene.enemies.behave(self.GeneratedEnemy(
                ground_y=50, explosion=scene.explosions, hits=scene.targets))
            scene.enemies.spawn(10, 10)
            scene.targets.spawn(200, 200)

        game = self._build_scene(build)
        behavior = game.enemies.behavior(self.GeneratedEnemy)
        sprite = game.enemies._live[0]
        for _ in range(3):
            behavior.step(game.enemies)
        self.assertEqual(behavior.state_name(sprite), "falling")
        sprite.y = 60  # past ground_y=50
        behavior.step(game.enemies)
        self.assertEqual(behavior.state_name(sprite), "exploding")

    def test_exploding_enter_hook_spawns_and_calls_back_once_then_despawns_next_tick(self):
        """enter_exploding (spawn + call_callback) runs the tick the
        transition happens; despawn (exploding's own step) only runs the
        *next* tick -- see StateMachine._dispatch_one's own contract:
        entering a state never also calls that state's step in the same
        tick. Proves both halves, and that the callback/spawn fire exactly
        once, not once per tick while 'exploding'."""
        calls = []

        def build(scene):
            scene.world = scene.layer("world", projection=vs2.TUNNEL)
            scene.enemies = scene.world.sprite_pool("ship.png", count=1)
            scene.targets = scene.world.sprite_pool("ship.png", count=1)
            scene.explosions = scene.world.sprite_pool("ship.png", count=1)
            scene.enemies.behave(self.GeneratedEnemy(
                ground_y=50, explosion=scene.explosions, hits=scene.targets,
                on_death=lambda sprite: calls.append(sprite)))
            scene.enemies.spawn(10, 10)
            scene.targets.spawn(200, 200)

        game = self._build_scene(build)
        behavior = game.enemies.behavior(self.GeneratedEnemy)
        sprite = game.enemies._live[0]
        for _ in range(3):
            behavior.step(game.enemies)
        sprite.y = 60
        behavior.step(game.enemies)  # falling -> exploding: enter_exploding runs
        self.assertEqual(behavior.state_name(sprite), "exploding")
        self.assertEqual(len(game.enemies), 1)          # not despawned yet
        self.assertEqual(len(game.explosions), 1)       # but already spawned
        self.assertEqual(len(calls), 1)                 # and called back, once

        behavior.step(game.enemies)                      # exploding's own step
        self.assertEqual(len(game.enemies), 0)            # despawned now
        self.assertEqual(len(calls), 1)                   # still just once


class DamageableRoundTripTests(unittest.TestCase):
    """Phase 2: Damageable's model -> source, pure text mechanics."""

    def test_generates_a_plain_behavior_not_a_statemachine(self):
        text = generator.generate_source(damageable_model(), "generated_damageable.py")
        self.assertIn("class GeneratedDamageable(Behavior):", text)
        self.assertNotIn("StateMachine", text)

    def test_hp_is_not_declared_state_damage_taken_and_invuln_left_are(self):
        """hp is a Parameter (the configured max, shared/tunable) -- the
        real per-sprite progress lives in damage_taken/invuln_left."""
        text = generator.generate_source(damageable_model(), "x.py")
        self.assertIn("hp = Number(1", text)
        self.assertIn("state = ('damage_taken', 'invuln_left')", text)

    def test_fixture_matches_current_generator_output(self):
        fixture_path = Path(ROOT) / "tests" / "fixtures" / "generated_damageable_fixture.py"
        current = generator.generate_source(damageable_model(), fixture_path.name)
        self.assertEqual(
            fixture_path.read_text(), current,
            "regenerate tests/fixtures/generated_damageable_fixture.py from "
            "the current generator")

    def test_blob_round_trips_the_exact_damageable_model(self):
        from tools.vs2_scene_gen.blob import decode_blob
        model = damageable_model()
        text = generator.generate_source(model, "x.py")
        _banner, _body, blob_line = checksum.split_generated_file(text)
        decoded = decode_blob(checksum.blob_data(blob_line))
        self.assertEqual(decoded, model)


class GeneratedDamageableBehaviorTests(unittest.TestCase):
    """The real acceptance bar this task's own report demands: hp
    decreases on a hit, the sprite is not hit again during its
    invulnerability window, and it despawns/spawns-explosion/awards-score/
    calls-on_death exactly once when hp reaches 0."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="vs2_behavior_gen_dmg_test_")
        reset_runtime()
        api_guard.reset()
        self.runtime = configure_runtime("headless")
        stripes.clear()
        stripes["ship.png"] = 0
        self.runtime.platform.sprites.stripes[0] = {
            "width": 4, "height": 4, "frames": 4, "palette": 0,
        }
        api_guard.begin_app("games.test_vs2_behavior_gen", "vs2")
        self.GeneratedDamageable = _load_generated_class(
            damageable_model(), self.tmpdir, basename="generated_damageable.py")

    def tearDown(self):
        reset_runtime()
        api_guard.reset()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_scene(self, **behavior_kwargs):
        deaths = []

        class Game(vs2.Scene):
            idle_timeout = None
            back_button = False

            def build(self):
                self.world = self.layer("world", projection=vs2.TUNNEL)
                self.enemies = self.world.sprite_pool("ship.png", count=1)
                self.bullets = self.world.sprite_pool("ship.png", count=3)
                self.explosions = self.world.sprite_pool("ship.png", count=1)
                self.enemies.behave(self.behavior_cls(
                    hits=self.bullets, explosion=self.explosions,
                    on_death=lambda sprite, points: deaths.append(points),
                    **self.behavior_kwargs))

            def update(self):
                pass

        Game.behavior_cls = self.GeneratedDamageable
        Game.behavior_kwargs = behavior_kwargs
        game = Game()
        director.push(game)
        game.deaths = deaths
        return game

    def test_generated_class_is_a_real_behavior_subclass(self):
        from vs2.behaviors import Behavior
        self.assertTrue(issubclass(self.GeneratedDamageable, Behavior))

    def test_hp_decreases_on_a_hit(self):
        game = self._build_scene(hp=5, invulnerable_ticks=0)
        enemy = game.enemies.spawn(10, 10)
        game.bullets.spawn(10, 10)  # exactly overlapping
        behavior = game.enemies.behavior(self.GeneratedDamageable)
        behavior.step(game.enemies)
        self.assertEqual(enemy.damage_taken, 1)
        self.assertEqual(len(game.enemies), 1)  # still alive: hp=5, one hit

    def test_not_hit_again_during_its_invulnerability_window(self):
        game = self._build_scene(hp=99, invulnerable_ticks=3)
        enemy = game.enemies.spawn(10, 10)
        game.bullets.spawn(10, 10)  # stays overlapping the whole time
        behavior = game.enemies.behavior(self.GeneratedDamageable)
        behavior.step(game.enemies)
        self.assertEqual(enemy.damage_taken, 1)
        for _ in range(3):
            behavior.step(game.enemies)
            self.assertEqual(enemy.damage_taken, 1, "hit again while invulnerable")

    def test_blink_hides_then_restores_visibility(self):
        game = self._build_scene(hp=99, invulnerable_ticks=2, blink=True)
        enemy = game.enemies.spawn(10, 10)
        game.bullets.spawn(10, 10)
        behavior = game.enemies.behavior(self.GeneratedDamageable)
        self.assertTrue(enemy.visible)
        behavior.step(game.enemies)  # hit: hides
        self.assertFalse(enemy.visible)
        behavior.step(game.enemies)  # invuln_left 2 -> 1: still hidden
        self.assertFalse(enemy.visible)
        behavior.step(game.enemies)  # invuln_left 1 -> 0: restored
        self.assertTrue(enemy.visible)

    def test_dies_exactly_once_despawn_explosion_score_and_on_death(self):
        game = self._build_scene(hp=1, invulnerable_ticks=0, score=40)
        enemy = game.enemies.spawn(10, 10)
        game.bullets.spawn(10, 10)
        behavior = game.enemies.behavior(self.GeneratedDamageable)
        behavior.step(game.enemies)
        self.assertEqual(len(game.enemies), 0)
        self.assertEqual(len(game.explosions), 1)
        self.assertEqual(game.deaths, [40])
        # a second step() over the (now empty) pool must not re-trigger
        # anything -- the sprite is gone, not merely marked dead.
        behavior.step(game.enemies)
        self.assertEqual(len(game.explosions), 1)
        self.assertEqual(game.deaths, [40])

    def test_death_does_not_double_fire_when_a_hit_kills_in_one_tick(self):
        """hp=1: the very hit that brings damage_taken to 1 == hp must
        fire the death sequence exactly once in that same step(), not
        once for the hit and again for a separately-detected death."""
        game = self._build_scene(hp=1, invulnerable_ticks=0, score=10)
        game.enemies.spawn(10, 10)
        game.bullets.spawn(10, 10)
        behavior = game.enemies.behavior(self.GeneratedDamageable)
        behavior.step(game.enemies)
        self.assertEqual(game.deaths, [10])

    def test_two_hits_needed_when_hp_is_two(self):
        game = self._build_scene(hp=2, invulnerable_ticks=0)
        enemy = game.enemies.spawn(10, 10)
        behavior = game.enemies.behavior(self.GeneratedDamageable)
        game.bullets.spawn(10, 10)
        behavior.step(game.enemies)
        self.assertEqual(len(game.enemies), 1)
        self.assertEqual(enemy.damage_taken, 1)
        game.bullets.spawn(10, 10)  # a second, separate overlapping bullet
        behavior.step(game.enemies)
        self.assertEqual(len(game.enemies), 0)
        self.assertEqual(game.deaths, [0])  # default score


# ---------------------------------------------------------------------------
# build_behavior.py CLI -- mirrors tests/test_vs2_event_gen.py's own
# BuildEventsCliTests exactly (same three checks), against this package's
# CLI instead.
# ---------------------------------------------------------------------------

class BuildBehaviorCliTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="vs2_behavior_gen_cli_test_"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_output_path_substitutes_the_suffix_in_place(self):
        """Unlike build_events.py's own "_events.py" append (a companion
        mixin beside a hand-written scene), this generator's output is a
        whole drop-in class -- see build_behavior.py's own docstring."""
        model_path = self.tmpdir / "enemy_states.vs2behavior.json"
        self.assertEqual(
            build_behavior.output_path_for(model_path), self.tmpdir / "enemy_states.py")

    def test_build_one_writes_the_generated_file(self):
        import json

        model = projectile_model()
        model_path = self.tmpdir / "demo_behavior.vs2behavior.json"
        model_path.write_text(json.dumps(model))

        result = build_behavior.build_one(model_path)
        self.assertEqual(result.status, "created")
        output_path = self.tmpdir / "demo_behavior.py"
        self.assertTrue(output_path.exists())
        self.assertIn("class GeneratedProjectile(Behavior):", output_path.read_text())

    def test_main_reports_nonzero_on_missing_argument(self):
        self.assertEqual(build_behavior.main([]), 2)

    def test_main_reports_nonzero_on_bad_model(self):
        import json

        model_path = self.tmpdir / "bad.vs2behavior.json"
        model_path.write_text(json.dumps({"version": 2}))
        self.assertEqual(build_behavior.main([str(model_path)]), 1)


if __name__ == "__main__":
    unittest.main()
