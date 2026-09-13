"""Tests for tools/vs2_event_gen/{model,generator,checksum,detach,build_events}.py
-- the T16 event-sheet -> ``on_enter()``/``update()`` generator.

Pure CPython, no MicroPython shims -- this pipeline never runs on-device,
exactly like tools/vs2_scene_gen. Run: ``python3 tests/test_vs2_event_gen.py``.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.vs2_event_gen import build_events, checksum, detach, generator
from tools.vs2_event_gen.model import ModelError, validate_model


def _literal(value):
    return {"kind": "literal", "value": value}


def _var(name):
    return {"kind": "var", "name": name}


def _small_model():
    return {
        "version": 1,
        "class_name": "DemoSceneEvents",
        "events": [
            {
                "kind": "on_start",
                "conditions": [],
                "actions": [{"kind": "set_variable", "name": "score", "value": _literal(0)}],
            },
            {
                "kind": "on_tick",
                "conditions": [{"kind": "timer_elapsed", "ticks": 5}],
                "actions": [{"kind": "set_variable", "name": "score", "value": _literal(10)}],
            },
            {
                "kind": "on_tick",
                "conditions": [
                    {"kind": "compare", "left": _var("score"), "op": ">=", "right": _literal(10)}
                ],
                "actions": [
                    {
                        "kind": "goto_scene",
                        "module": "games.vs2_examples.event_sheet_demo.code.gameover_scene",
                        "class_name": "GameOverScene",
                    }
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# model.py
# ---------------------------------------------------------------------------

class ValidModelTests(unittest.TestCase):
    def test_accepts_the_documented_shape(self):
        self.assertIsNone(validate_model(_small_model()))

    def test_accepts_random_and_set_label_text(self):
        model = _small_model()
        model["events"].append({
            "kind": "on_start",
            "conditions": [],
            "actions": [
                {
                    "kind": "set_variable",
                    "name": "score",
                    "value": {"kind": "random", "a": _literal(1), "b": _literal(5)},
                },
                {"kind": "set_label_text", "label_attr": "title_label", "text": _literal("HI")},
                {"kind": "set_label_text", "label_attr": "score_label", "text": _var("score")},
            ],
        })
        self.assertIsNone(validate_model(model))

    def test_two_on_tick_entries_are_both_allowed(self):
        model = _small_model()
        model["events"].append({
            "kind": "on_tick",
            "conditions": [{"kind": "timer_elapsed", "ticks": 1}],
            "actions": [{"kind": "set_variable", "name": "other", "value": _literal(1)}],
        })
        self.assertIsNone(validate_model(model))


class RejectModelTests(unittest.TestCase):
    def assert_rejects(self, model, path_fragment):
        with self.assertRaises(ModelError) as ctx:
            validate_model(model)
        self.assertIn(path_fragment, str(ctx.exception))

    def test_wrong_version(self):
        model = _small_model()
        model["version"] = 2
        self.assert_rejects(model, "model.version")

    def test_bad_class_name(self):
        model = _small_model()
        model["class_name"] = "not valid"
        self.assert_rejects(model, "model.class_name")

    def test_empty_events(self):
        model = _small_model()
        model["events"] = []
        self.assert_rejects(model, "model.events")

    def test_unknown_event_kind(self):
        model = _small_model()
        model["events"][0]["kind"] = "on_frame"
        self.assert_rejects(model, "events[0].kind")

    def test_actions_must_be_non_empty(self):
        model = _small_model()
        model["events"][0]["actions"] = []
        self.assert_rejects(model, "events[0].actions")

    def test_unknown_condition_kind(self):
        model = _small_model()
        model["events"][1]["conditions"][0]["kind"] = "flag_set"
        self.assert_rejects(model, "conditions[0].kind")

    def test_compare_bad_op(self):
        model = _small_model()
        model["events"][2]["conditions"][0]["op"] = "==="
        self.assert_rejects(model, ".op")

    def test_timer_elapsed_needs_positive_ticks(self):
        model = _small_model()
        model["events"][1]["conditions"][0]["ticks"] = 0
        self.assert_rejects(model, ".ticks")

    def test_literal_rejects_bool(self):
        model = _small_model()
        model["events"][0]["actions"][0]["value"] = _literal(True)
        self.assert_rejects(model, ".value")

    def test_literal_rejects_none(self):
        model = _small_model()
        model["events"][0]["actions"][0]["value"] = _literal(None)
        self.assert_rejects(model, ".value")

    def test_random_needs_a_and_b(self):
        model = _small_model()
        model["events"][0]["actions"][0]["value"] = {"kind": "random", "a": _literal(1)}
        self.assert_rejects(model, "random")

    def test_goto_scene_bad_module(self):
        model = _small_model()
        model["events"][2]["actions"][0]["module"] = "not a module!"
        self.assert_rejects(model, ".module")

    def test_goto_scene_bad_class_name(self):
        model = _small_model()
        model["events"][2]["actions"][0]["class_name"] = "class"  # keyword
        self.assert_rejects(model, ".class_name")

    def test_set_variable_reserved_name_rejected(self):
        model = _small_model()
        model["events"][0]["actions"][0]["name"] = "update"
        self.assert_rejects(model, ".name")

    def test_unknown_top_level_key(self):
        model = _small_model()
        model["bogus"] = 1
        self.assert_rejects(model, "model")

    def test_unknown_action_kind(self):
        model = _small_model()
        model["events"][0]["actions"][0]["kind"] = "play_sound"
        self.assert_rejects(model, ".kind")


# ---------------------------------------------------------------------------
# generator.py: rendering
# ---------------------------------------------------------------------------

class RenderExprTests(unittest.TestCase):
    def test_literal_number(self):
        self.assertEqual(generator.render_expr(_literal(5), set()), "5")

    def test_literal_string(self):
        self.assertEqual(generator.render_expr(_literal("hi"), set()), "'hi'")

    def test_var_reads_project_namespace(self):
        self.assertEqual(generator.render_expr(_var("score"), set()), "vs2.project.score")

    def test_random_is_inclusive_both_ends(self):
        imports = set()
        src = generator.render_expr(
            {"kind": "random", "a": _literal(1), "b": _literal(5)}, imports)
        self.assertEqual(src, "randrange(1, (5) + 1)")
        self.assertIn("randrange", imports)


class RenderBodyTests(unittest.TestCase):
    def test_body_defines_the_mixin_and_both_methods(self):
        body = generator.render_body(_small_model())
        self.assertIn("class DemoSceneEvents(vs2.Scene):", body)
        self.assertIn("    def on_enter(self):", body)
        self.assertIn("    def update(self):", body)
        self.assertIn("super().on_enter()", body)
        self.assertIn("super().update()", body)

    def test_declares_every_set_variable_name_once_in_on_enter(self):
        body = generator.render_body(_small_model())
        self.assertEqual(body.count("vs2.project.var('score', 0)"), 1)

    def test_goto_scene_imports_locally_and_propagates_api_attrs(self):
        body = generator.render_body(_small_model())
        self.assertIn(
            "import games.vs2_examples.event_sheet_demo.code.gameover_scene as _scene", body)
        self.assertIn("_target = _scene.GameOverScene()", body)
        self.assertIn("_target._vs_api_slug = self._vs_api_slug", body)
        self.assertIn("_target._vs_declared_api = self._vs_declared_api", body)
        self.assertIn("self.switch(_target)", body)
        # Indented (inside the guarding if-block), not at module scope --
        # scenes that transition to each other in a cycle would otherwise
        # deadlock importing each other at load time.
        import_line = next(
            line for line in body.splitlines() if "as _scene" in line and "import" in line)
        self.assertTrue(import_line.startswith("            "))

    def test_timer_elapsed_condition_and_set_variable_action(self):
        body = generator.render_body(_small_model())
        self.assertIn("if self._vs2_events_ticks >= 5:", body)
        self.assertIn("vs2.project.score = 10", body)

    def test_compare_condition_renders_operator_verbatim(self):
        body = generator.render_body(_small_model())
        self.assertIn("if vs2.project.score >= 10:", body)

    def test_set_label_text_renders_text_setter(self):
        model = _small_model()
        model["events"][0]["actions"].append(
            {"kind": "set_label_text", "label_attr": "title_label", "text": _literal("HI")})
        body = generator.render_body(model)
        self.assertIn("self.title_label.text = 'HI'", body)

    def test_two_goto_scene_targets_each_get_their_own_local_import(self):
        model = _small_model()
        model["events"].append({
            "kind": "on_tick",
            "conditions": [{"kind": "timer_elapsed", "ticks": 99}],
            "actions": [
                {
                    "kind": "goto_scene",
                    "module": "games.vs2_examples.event_sheet_demo.code.title_scene",
                    "class_name": "TitleScene",
                }
            ],
        })
        body = generator.render_body(model)
        self.assertIn(
            "import games.vs2_examples.event_sheet_demo.code.gameover_scene as _scene", body)
        self.assertIn(
            "import games.vs2_examples.event_sheet_demo.code.title_scene as _scene", body)

    def test_rendering_is_deterministic_regardless_of_dict_order(self):
        model = _small_model()
        reordered = json.loads(json.dumps(model))
        self.assertEqual(generator.render_body(model), generator.render_body(reordered))


# ---------------------------------------------------------------------------
# generator.py: the safe write path + checksum/detach round-trip
# ---------------------------------------------------------------------------

class GeneratorFixture(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="vs2_event_gen_test_"))
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def output_path(self, name="demo_scene_events.py"):
        return self.tmpdir / name


class ByteIdenticalRegenerationTests(GeneratorFixture):
    def test_second_write_reports_unchanged_and_is_byte_identical(self):
        model = _small_model()
        path = self.output_path()

        first = generator.write_events_file(model, path)
        self.assertEqual(first.status, "created")
        first_bytes = path.read_bytes()

        second = generator.write_events_file(model, path)
        self.assertEqual(second.status, "unchanged")
        self.assertEqual(path.read_bytes(), first_bytes)

    def test_blob_line_uses_the_blocks_prefix(self):
        model = _small_model()
        path = self.output_path()
        generator.write_events_file(model, path)
        text = path.read_text()
        blob_lines = [line for line in text.splitlines() if line.startswith("# blocks: ")]
        self.assertEqual(len(blob_lines), 1)
        self.assertFalse(text.startswith("# scene-model:"))


class HandEditDetectionTests(GeneratorFixture):
    def test_editing_the_body_is_detected_and_the_file_is_left_alone(self):
        model = _small_model()
        path = self.output_path()
        generator.write_events_file(model, path)
        original_text = path.read_text()

        edited = original_text.replace(
            "class DemoSceneEvents(vs2.Scene):",
            "class DemoSceneEvents(vs2.Scene):  # tweaked")
        self.assertNotEqual(edited, original_text)
        path.write_text(edited)

        result = generator.write_events_file(model, path)
        self.assertEqual(result.status, "hand_edited")
        self.assertEqual(path.read_text(), edited, "hand-edited file must not be overwritten")

    def test_checksum_is_hand_edited_predicate_agrees(self):
        model = _small_model()
        path = self.output_path()
        generator.write_events_file(model, path)
        text = path.read_text()
        self.assertFalse(checksum.is_hand_edited(text))

        edited = text.replace("super().update()", "super().update()  # noop", 1)
        self.assertTrue(checksum.is_hand_edited(edited))


class DetachRoundTripTests(GeneratorFixture):
    def test_detach_strips_banner_and_blob_one_way(self):
        model = _small_model()
        path = self.output_path()
        generator.write_events_file(model, path)

        detached_text = detach.detach_file(path)
        self.assertFalse(detach.is_generated(detached_text))
        self.assertNotIn("# blocks:", detached_text)
        self.assertNotIn("generated, do not edit", detached_text)

        with self.assertRaises(detach.DetachError):
            detach.detach(detached_text)

    def test_detached_file_is_not_overwritten_by_a_later_generate(self):
        model = _small_model()
        path = self.output_path()
        generator.write_events_file(model, path)
        detached_text = detach.detach_file(path)

        result = generator.write_events_file(model, path)
        self.assertEqual(result.status, "detached")
        self.assertEqual(path.read_text(), detached_text)


# ---------------------------------------------------------------------------
# build_events.py CLI
# ---------------------------------------------------------------------------

class BuildEventsCliTests(GeneratorFixture):
    def test_output_path_appends_events_suffix(self):
        model_path = self.tmpdir / "title_scene.vs2events.json"
        self.assertEqual(
            build_events.output_path_for(model_path), self.tmpdir / "title_scene_events.py")

    def test_build_one_writes_the_companion_file(self):
        model = _small_model()
        model_path = self.tmpdir / "demo_scene.vs2events.json"
        model_path.write_text(json.dumps(model))

        result = build_events.build_one(model_path)
        self.assertEqual(result.status, "created")
        output_path = self.tmpdir / "demo_scene_events.py"
        self.assertTrue(output_path.exists())
        self.assertIn("class DemoSceneEvents(vs2.Scene):", output_path.read_text())

    def test_main_reports_nonzero_on_missing_argument(self):
        self.assertEqual(build_events.main([]), 2)

    def test_main_reports_nonzero_on_bad_model(self):
        model_path = self.tmpdir / "bad.vs2events.json"
        model_path.write_text(json.dumps({"version": 2}))
        self.assertEqual(build_events.main([str(model_path)]), 1)


if __name__ == "__main__":
    unittest.main()
