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
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.vs2_behavior_gen import build_behavior, checksum, detach, generator, linemap
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

    def test_fast_fixture_matches_current_generator_output(self):
        """T17 Phase 3: tests/fixtures/generated_projectile_fast_fixture.py,
        the same drift guard as the readable fixture above, for the
        checked-in ``backend="fast"`` render
        tests/test_vs2_behavior_gen_fast_backend_micropython.py loads."""
        fixture_path = Path(ROOT) / "tests" / "fixtures" / "generated_projectile_fast_fixture.py"
        current = generator.generate_source(projectile_model(), fixture_path.name, backend="fast")
        self.assertEqual(
            fixture_path.read_text(), current,
            "regenerate tests/fixtures/generated_projectile_fast_fixture.py "
            "from the current generator (backend='fast')")

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



# ---------------------------------------------------------------------------
# binary_op expressions (added while porting games/vs2_examples/vyruss_vs2's
# hand-written choreography math to blocks) -- pure text, CPython only.
# ---------------------------------------------------------------------------

class ExprRenderingTests(unittest.TestCase):
    def test_arithmetic_ops_render_as_plain_infix(self):
        for op, symbol in (("+", "+"), ("-", "-"), ("*", "*"), ("//", "//"), ("%", "%")):
            expr = {"kind": "binary_op", "op": op,
                    "left": _param_ref("speed_y"), "right": {"kind": "literal", "value": 3}}
            self.assertEqual(
                generator.render_expr(expr), "(self.speed_y %s 3)" % (symbol,))

    def test_min_max_render_as_builtin_calls(self):
        for op in ("min", "max"):
            expr = {"kind": "binary_op", "op": op,
                    "left": {"kind": "literal", "value": 0}, "right": _state_ref("y")}
            self.assertEqual(generator.render_expr(expr), "%s(0, sprite.y)" % (op,))

    def test_binary_op_nests_arbitrarily_deep(self):
        expr = {
            "kind": "binary_op", "op": "max",
            "left": {"kind": "literal", "value": 0},
            "right": {"kind": "binary_op", "op": "-",
                      "left": _state_ref("y"), "right": _param_ref("rim_y")},
        }
        self.assertEqual(generator.render_expr(expr), "max(0, (sprite.y - self.rim_y))")

    def test_binary_op_honours_hoisted_params_in_its_operands(self):
        """A hoisted param nested inside binary_op still renders as the
        hoisted local, not self.<name> -- render_expr() threads `hoisted`
        through its own recursive calls, it does not just check the
        top-level expr."""
        expr = {"kind": "binary_op", "op": "+",
                "left": _param_ref("speed_y"), "right": {"kind": "literal", "value": 1}}
        self.assertEqual(
            generator.render_expr(expr, hoisted={"speed_y": "_h_speed_y"}),
            "(_h_speed_y + 1)")


# ---------------------------------------------------------------------------
# T17 Phase 3: block-id trailing comments -- pure text, CPython only.
# ---------------------------------------------------------------------------

class BlockCommentTests(unittest.TestCase):
    def test_action_decl_and_apply_to_all_share_one_comment(self):
        """The same 'do'-flavor Action block produces both the attached()
        line and the apply-to-all run() line -- see
        web/vs2-behavior-blocks.js's own serializeApplyToAll."""
        model = projectile_model()
        model["actions"][0]["block_id"] = "BLK_MOVE"
        body = generator.render_body(model)
        attached_line = next(l for l in body.splitlines() if "self.move = self.action" in l)
        apply_line = next(l for l in body.splitlines() if "self.move.run(sprites)" in l)
        self.assertTrue(attached_line.rstrip().endswith("# block: BLK_MOVE"), attached_line)
        self.assertTrue(apply_line.rstrip().endswith("# block: BLK_MOVE"), apply_line)

    def test_accumulate_node_gets_its_own_comment(self):
        model = projectile_model()
        model["per_sprite"][0]["block_id"] = "BLK_ACC"
        body = generator.render_body(model)
        line = next(l for l in body.splitlines() if "shot_flown +=" in l)
        self.assertTrue(line.rstrip().endswith("# block: BLK_ACC"), line)

    def test_if_else_comments_both_the_if_and_else_headers_not_the_body(self):
        model = projectile_model()
        model["per_sprite"][1]["block_id"] = "BLK_IF"
        body = generator.render_body(model)
        lines = body.splitlines()
        if_line = next(l for l in lines if l.strip().startswith("if sprite.shot_flown"))
        else_line = next(l for l in lines if l.strip() == "else:  # block: BLK_IF")
        despawn_line = next(l for l in lines if l.strip() == "sprite.despawn()")
        self.assertTrue(if_line.rstrip().endswith("# block: BLK_IF"), if_line)
        self.assertIsNotNone(else_line)
        # The despawn inside "then" has no block_id of its own in this
        # model, and must not inherit the if_else's -- confirms the
        # comment stays scoped to the node that actually produced the line.
        self.assertNotIn("# block:", despawn_line)

    def test_if_action_comments_both_result_and_none_check_lines(self):
        model = projectile_model()
        model["per_sprite"][1]["else"][0]["block_id"] = "BLK_COLLIDE_CHECK"
        body = generator.render_body(model)
        result_line = next(l for l in body.splitlines() if "_hit_result = self.hit.run_one" in l)
        check_line = next(l for l in body.splitlines() if "if _hit_result is not None:" in l)
        self.assertTrue(result_line.rstrip().endswith("# block: BLK_COLLIDE_CHECK"))
        self.assertTrue(check_line.rstrip().endswith("# block: BLK_COLLIDE_CHECK"))

    def test_no_block_id_means_no_comment_anywhere(self):
        body = generator.render_body(projectile_model())
        self.assertNotIn("# block:", body)

    def test_state_hat_nodes_get_comments_too(self):
        model = state_machine_model()
        model["state_machine"]["bodies"]["exploding"]["step"][0]["block_id"] = "BLK_DESPAWN"
        body = generator.render_body(model)
        self.assertIn("sprite.despawn()  # block: BLK_DESPAWN", body)


# ---------------------------------------------------------------------------
# T17 Phase 3: the fast backend -- structural checks, pure text, CPython
# only. Behavioral parity (the check that actually matters, per the task
# brief) is FastBackendParityTests, further down, which imports the real
# vs2 package and runs both backends' output against identical scenarios.
# ---------------------------------------------------------------------------

class FastBackendStructureTests(unittest.TestCase):
    def test_unknown_backend_rejected(self):
        with self.assertRaises(generator.GeneratorError):
            generator.render_body(projectile_model(), backend="ludicrous")

    def test_fast_hoists_every_param_read_inside_the_pool_loop(self):
        readable = generator.render_body(projectile_model(), backend="readable")
        fast = generator.render_body(projectile_model(), backend="fast")
        self.assertNotIn("_h_speed_y", readable)
        self.assertIn("_h_speed_y = self.speed_y", fast)
        self.assertIn("_h_range = self.range", fast)
        # Hoisted locals are used inside the loop instead of self.<param>...
        loop_body = fast.split("while index >= 0:", 1)[1]
        self.assertIn("_h_speed_y", loop_body)
        self.assertIn("_h_range", loop_body)
        # ...and attached()'s own Action-construction args are untouched:
        # those run once, at attach time, not per iteration.
        attached_body = fast.split("def attached", 1)[1].split("def step", 1)[0]
        self.assertIn("self.speed_y", attached_body)
        self.assertNotIn("_h_speed_y", attached_body)

    def test_fast_does_not_hoist_for_a_sprite_subject_kind(self):
        # step_one() has no explicit loop in the generated code -- see
        # generator.py's own docstring on why hoisting is skipped there.
        model = projectile_model()
        model["subject_kind"] = "sprite"
        del model["apply_to_all"][:]  # Move already applies to the lone sprite fine either way
        fast = generator.render_body(model, backend="fast")
        self.assertNotIn("_h_", fast)

    def test_fast_does_not_hoist_inside_state_hat_methods(self):
        fast = generator.render_body(state_machine_model(), backend="fast")
        self.assertNotIn("_h_", fast)

    def test_fast_inlines_if_action_result_when_despawn_hit_is_absent(self):
        model = projectile_model()
        # Replace the despawn_hit-using else branch with one that never
        # references the Collide result at all.
        model["per_sprite"][1]["else"] = [
            {"kind": "if_action", "bind": "hit", "then": [{"kind": "despawn"}], "else": []},
        ]
        readable = generator.render_body(model, backend="readable")
        fast = generator.render_body(model, backend="fast")
        self.assertIn("_hit_result", readable)
        self.assertNotIn("_hit_result", fast)
        self.assertIn("if self.hit.run_one(sprite) is not None:", fast)

    def test_fast_does_not_inline_if_action_result_when_despawn_hit_present(self):
        # The real Projectile model -- despawn_hit is present, so the
        # local must survive (see this module's docstring's "inline"
        # bullet for why).
        fast = generator.render_body(projectile_model(), backend="fast")
        self.assertIn("_hit_result", fast)

    def test_fast_does_not_inline_across_a_nested_if_action_scope(self):
        # A despawn_hit inside a NESTED if_action must not make the
        # OUTER if_action's own local survive when nothing in the outer
        # scope itself references it -- _references_hit_var must not
        # descend into the nested if_action's own scope.
        model = {
            "version": 1, "class_name": "X", "subject_kind": "pool",
            "params": [{"name": "a", "type": "pool", "default": None},
                       {"name": "b", "type": "pool", "default": None}],
            "state": [], "apply_to_all": [],
            "actions": [
                {"bind": "hit_a", "action_class": "Collide", "args": {"targets": _param_ref("a")}},
                {"bind": "hit_b", "action_class": "Collide", "args": {"targets": _param_ref("b")}},
            ],
            "per_sprite": [
                {"kind": "if_action", "bind": "hit_a", "then": [
                    {"kind": "if_action", "bind": "hit_b",
                     "then": [{"kind": "despawn_hit"}], "else": []},
                ], "else": []},
            ],
        }
        fast = generator.render_body(model, backend="fast")
        # Outer (hit_a) result is never referenced by a despawn_hit in its
        # OWN scope (only the inner hit_b's despawn_hit is) -- so it must
        # be inlined, while the inner one must not be.
        self.assertNotIn("_hit_a_result", fast)
        self.assertIn("_hit_b_result", fast)
        self.assertIn("if self.hit_a.run_one(sprite) is not None:", fast)

    def test_fast_folds_a_literal_vs_literal_compare_condition(self):
        model = {
            "version": 1, "class_name": "X", "subject_kind": "pool",
            "params": [], "state": [], "actions": [], "apply_to_all": [],
            "per_sprite": [
                {"kind": "if_else",
                 "condition": {"kind": "compare", "op": ">",
                                "left": {"kind": "literal", "value": 5},
                                "right": {"kind": "literal", "value": 3}},
                 "then": [{"kind": "despawn"}], "else": []},
            ],
        }
        fast = generator.render_body(model, backend="fast")
        readable = generator.render_body(model, backend="readable")
        self.assertIn("if True:", fast)
        self.assertIn("if 5 > 3:", readable)

    def test_fast_never_hoists_call_callback_spawn_or_play_sound_locals(self):
        # These deliberately keep their own local -- see this module's
        # per-kind rendering comments on why inlining them would
        # reintroduce a torn (double) read of a mutable attribute.
        fast = generator.render_body(state_machine_model(), backend="fast")
        self.assertIn("_cb_on_death = self.on_death", fast)
        self.assertIn("_spawn_explosion = self.explosion", fast)
        self.assertIn("_sound_sound = self.sound", fast)

    def test_fast_backend_is_a_near_no_op_when_nothing_is_foldable_or_hoistable(self):
        # A model with no per-sprite work at all (apply-to-all only) has
        # nothing for any of the three transforms to touch.
        model = {
            "version": 1, "class_name": "X", "subject_kind": "pool",
            "params": [{"name": "speed_x", "type": "number", "default": 1}],
            "state": [], "apply_to_all": ["move"], "per_sprite": [],
            "actions": [{"bind": "move", "action_class": "Move",
                         "args": {"speed_x": _param_ref("speed_x")}}],
        }
        self.assertEqual(
            generator.render_body(model, backend="fast"),
            generator.render_body(model, backend="readable"))


# ---------------------------------------------------------------------------
# T17 Phase 3: linemap.py -- pure text, CPython only. The real-MicroPython
# half of this same acceptance bar (a deliberately-broken block program, a
# CAPTURED REAL traceback, resolved back to the right block id) is
# RealTracebackLineMapTests, further down (after FastBackendParityTests),
# which shells out to a real micropython subprocess the same way
# tools/vs2_scene_gen/recover.py does.
# ---------------------------------------------------------------------------

class LineMapTests(unittest.TestCase):
    def test_build_line_map_and_resolve_traceback_end_to_end(self):
        model = projectile_model()
        model["per_sprite"][0]["block_id"] = "BLK_ACC"
        source = generator.generate_source(model, "generated_projectile.py")
        lines = source.splitlines()
        line_no = next(i + 1 for i, l in enumerate(lines) if l.rstrip().endswith("BLK_ACC"))

        line_map = linemap.build_line_map(source)
        self.assertEqual(line_map[line_no], "BLK_ACC")

        tb = ('Traceback (most recent call last):\n'
              '  File "generated_projectile.py", line %d, in step\n'
              "AttributeError: x\n") % (line_no,)
        result = linemap.resolve_traceback_blocks(tb, "generated_projectile.py", source)
        self.assertEqual(result, [{"line": line_no, "block_id": "BLK_ACC"}])

    def test_resolves_by_basename_when_the_frame_names_a_longer_path(self):
        model = projectile_model()
        model["per_sprite"][0]["block_id"] = "BLK_ACC"
        source = generator.generate_source(model, "generated_projectile.py")
        lines = source.splitlines()
        line_no = next(i + 1 for i, l in enumerate(lines) if l.rstrip().endswith("BLK_ACC"))
        tb = 'File "games/x/code/generated_projectile.py", line %d, in step' % (line_no,)
        result = linemap.resolve_traceback_blocks(tb, "generated_projectile.py", source)
        self.assertEqual(result, [{"line": line_no, "block_id": "BLK_ACC"}])

    def test_a_line_with_no_block_id_resolves_to_nothing(self):
        source = generator.generate_source(projectile_model(), "generated_projectile.py")
        tb = 'File "generated_projectile.py", line 1, in step'  # the banner line
        result = linemap.resolve_traceback_blocks(tb, "generated_projectile.py", source)
        self.assertEqual(result, [])

    def test_fast_backend_output_still_carries_its_block_comments(self):
        # The line-map must keep working regardless of which backend
        # rendered the file -- block-id comments are emitted identically
        # by both (see generator.py's _with_block_comment).
        model = projectile_model()
        model["per_sprite"][1]["block_id"] = "BLK_IF"
        source = generator.generate_source(model, "generated_projectile.py", backend="fast")
        line_map = linemap.build_line_map(source)
        self.assertIn("BLK_IF", line_map.values())


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

    def test_fast_fixture_matches_current_generator_output(self):
        fixture_path = Path(ROOT) / "tests" / "fixtures" / "generated_enemy_fast_fixture.py"
        current = generator.generate_source(
            state_machine_model(), fixture_path.name, backend="fast")
        self.assertEqual(
            fixture_path.read_text(), current,
            "regenerate tests/fixtures/generated_enemy_fast_fixture.py from "
            "the current generator (backend='fast')")

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


def _load_generated_class(model, tmpdir, basename="generated_projectile.py", backend="readable"):
    """Write ``model``'s generated source to a real file under ``tmpdir``
    and import it with ``importlib`` -- proving the generator's *actual
    file output* runs, not merely the in-memory ``render_body()`` string.
    ``backend`` (T17 Phase 3, :data:`generator.BACKENDS`) -- passed
    straight through to :func:`generator.write_behavior_file`, so a
    caller can load the readable and fast renders of the same model as
    two distinct classes (see ``FastBackendParityTests`` below)."""
    path = Path(tmpdir) / basename
    generator.write_behavior_file(model, path, backend=backend)
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


def _travel_by_model():
    """A small pool-subject Behavior exercising binary_op at runtime: each
    tick, move ``sprite.y`` by ``min(speed, remaining)`` and subtract that
    same amount from ``remaining``, despawning once it reaches zero. This
    is exactly the shape games/vs2_examples/vyruss_vs2's hand-written
    ``TravelCloser``/``TravelAway`` classes use (``distance = min(SPEED,
    self.remaining); sprite.y -= distance; self.remaining -= distance``),
    the real motivating case for adding binary_op -- see this task's
    report."""
    moved = {"kind": "binary_op", "op": "min",
             "left": _param_ref("speed"), "right": _state_ref("remaining")}
    return {
        "version": 1,
        "class_name": "GeneratedTravelBy",
        "subject_kind": "pool",
        "params": [
            _param("speed", "number", 2, min=0, max=32, step=1),
        ],
        "state": ["remaining"],
        "actions": [],
        "apply_to_all": [],
        "per_sprite": [
            {"kind": "accumulate", "state": "y", "amount": moved},
            {"kind": "accumulate", "state": "remaining",
             "amount": {"kind": "binary_op", "op": "-",
                        "left": {"kind": "literal", "value": 0}, "right": moved}},
            {"kind": "if_else",
             "condition": {"kind": "compare", "op": "<=",
                            "left": _state_ref("remaining"), "right": {"kind": "literal", "value": 0}},
             "then": [{"kind": "despawn"}], "else": []},
        ],
    }


class BinaryOpBehaviorTests(unittest.TestCase):
    """Runtime proof that binary_op computes real values correctly --
    ExprRenderingTests above only checks the rendered *text*. Covers both
    backends (readable and fast), since the fast backend's own hoisting
    pass walks the same per-sprite tree independently -- see
    generator.py's _collect_hoistable_params docstring on why a param
    nested inside binary_op is deliberately left un-hoisted rather than
    silently mishandled."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="vs2_behavior_gen_binop_test_")
        reset_runtime()
        api_guard.reset()
        self.runtime = configure_runtime("headless")
        stripes.clear()
        stripes["ship.png"] = 0
        self.runtime.platform.sprites.stripes[0] = {
            "width": 4, "height": 4, "frames": 4, "palette": 0,
        }
        api_guard.begin_app("games.test_vs2_behavior_gen", "vs2")

    def tearDown(self):
        reset_runtime()
        api_guard.reset()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, backend):
        cls = _load_generated_class(
            _travel_by_model(), self.tmpdir,
            basename="generated_travel_by_%s.py" % (backend,), backend=backend)

        class Game(vs2.Scene):
            idle_timeout = None
            back_button = False

            def build(self):
                self.world = self.layer("world", projection=vs2.TUNNEL)
                self.movers = self.world.sprite_pool("ship.png", count=1)
                self.movers.behave(cls(speed=2))
                sprite = self.movers.spawn(0, 0)
                sprite.remaining = 5

            def update(self):
                pass

        game = Game()
        director.push(game)
        behavior = game.movers.behavior(cls)
        # remaining=5, speed=2: ticks move 2, 2, 1 (min(2, 1) on the last
        # tick) -- total y == 5, despawned exactly on the tick remaining
        # hits zero, never one tick early or late.
        ys = []
        for _ in range(3):
            behavior.step(game.movers)
            ys.append(game.movers._live[0].y if len(game.movers) else None)
        self.assertEqual(ys, [2, 4, None])
        self.assertEqual(len(game.movers), 0)

    def test_readable_backend(self):
        self._run("readable")

    def test_fast_backend(self):
        self._run("fast")


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

    def test_fast_fixture_matches_current_generator_output(self):
        fixture_path = Path(ROOT) / "tests" / "fixtures" / "generated_damageable_fast_fixture.py"
        current = generator.generate_source(
            damageable_model(), fixture_path.name, backend="fast")
        self.assertEqual(
            fixture_path.read_text(), current,
            "regenerate tests/fixtures/generated_damageable_fast_fixture.py "
            "from the current generator (backend='fast')")

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
# T17 Phase 3: the check that actually matters for the fast backend, per
# the task brief -- not "assert the transform looks right by reading the
# generator", but "run the exact same behavioral scenario against both
# backends' *actual generated file output* and confirm identical results",
# on the real (CPython-shimmed) vs2 package. The real-MicroPython version
# of this same check is
# tests/test_vs2_behavior_gen_fast_backend_micropython.py.
#
# Two live scenes cannot coexist under this codebase's own director (see
# director.push()'s own reset_sprites() call -- entering a second scene
# wipes the first one's pool), so each backend's run is a complete,
# separately-reset scenario; the two runs are compared by their captured
# per-tick snapshots afterward rather than interleaved live.
# ---------------------------------------------------------------------------

class FastBackendParityTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="vs2_behavior_gen_fast_parity_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _load_both(self, model, basename):
        readable_cls = _load_generated_class(
            model, self.tmpdir, basename=basename + "_readable.py", backend="readable")
        fast_cls = _load_generated_class(
            model, self.tmpdir, basename=basename + "_fast.py", backend="fast")
        return readable_cls, fast_cls

    def _fresh_runtime(self):
        reset_runtime()
        api_guard.reset()
        runtime = configure_runtime("headless")
        stripes.clear()
        stripes["ship.png"] = 0
        runtime.platform.sprites.stripes[0] = {
            "width": 4, "height": 4, "frames": 4, "palette": 0,
        }
        api_guard.begin_app("games.test_vs2_behavior_gen", "vs2")
        return runtime

    def _snapshot_pool(self, pool, fields):
        """The pool's own current sprite order, and every ``field`` of
        each live sprite -- position-for-position, not just set-equal,
        since both backends' runs start from an identical spawn order and
        must despawn/swap identically at every tick if they are truly
        behaviorally equivalent."""
        return [
            {field: getattr(sprite, field, "<missing>") for field in fields}
            for sprite in pool._live
        ]

    def test_projectile_parity_over_many_ticks_with_hits_and_despawns(self):
        readable_cls, fast_cls = self._load_both(projectile_model(), "generated_projectile_parity")
        fields = ("x", "y", "dx", "dy", "shot_flown")

        def run(behavior_cls):
            self._fresh_runtime()

            class Game(vs2.Scene):
                idle_timeout = None
                back_button = False

                def build(self):
                    self.world = self.layer("world", projection=vs2.TUNNEL)
                    self.shots = self.world.sprite_pool("ship.png", count=5)
                    self.targets = self.world.sprite_pool("ship.png", count=3)
                    self.shots.behave(behavior_cls(
                        speed_x=1, speed_y=3, range=30, hits=self.targets))

                def update(self):
                    pass

            game = Game()
            director.push(game)
            for x, y in ((0, 0), (5, 5), (10, 10), (2, 2), (8, 1)):
                game.shots.spawn(x, y)
            for x, y in ((10, 10), (8, 1), (60, 60)):
                game.targets.spawn(x, y)

            behavior = game.shots.behavior(behavior_cls)
            snapshots = []
            for _ in range(15):
                behavior.step(game.shots)
                snapshots.append(self._snapshot_pool(game.shots, fields))
                snapshots.append(len(game.targets))
            return snapshots

        readable_snapshots = run(readable_cls)
        fast_snapshots = run(fast_cls)
        self.assertEqual(readable_snapshots, fast_snapshots)
        # Sanity: this scenario actually exercises despawn (past range or
        # on a hit) at least once -- otherwise the comparison above would
        # be trivially true without ever reaching the fast backend's own
        # inlined if_action/hoisted-param code paths under real despawn
        # pressure.
        self.assertLess(len(readable_snapshots[-2]), 5)

    def test_state_machine_parity_through_a_full_orbit_fall_explode_cycle(self):
        readable_cls, fast_cls = self._load_both(state_machine_model(), "generated_enemy_parity")
        fields = ("x", "y", "fsm_state", "fsm_hold", "fsm_then", "frames_left")

        def run(behavior_cls):
            self._fresh_runtime()
            calls = []

            class Game(vs2.Scene):
                idle_timeout = None
                back_button = False

                def build(self):
                    self.world = self.layer("world", projection=vs2.TUNNEL)
                    self.enemies = self.world.sprite_pool("ship.png", count=1)
                    self.targets = self.world.sprite_pool("ship.png", count=1)
                    self.explosions = self.world.sprite_pool("ship.png", count=1)
                    self.enemies.behave(behavior_cls(
                        ground_y=50, explosion=self.explosions, hits=self.targets,
                        on_death=lambda sprite: calls.append(True)))

                def update(self):
                    pass

            game = Game()
            director.push(game)
            game.enemies.spawn(10, 10)
            game.targets.spawn(200, 200)  # far away: never hit -- exercises
                                           # the hold()-driven timed path,
                                           # not the Collide short-circuit.

            behavior = game.enemies.behavior(behavior_cls)
            snapshots = []
            for tick in range(6):
                if tick == 3:
                    # Mirrors GeneratedStateMachineBehaviorTests's own
                    # test_falling_transitions_to_exploding_past_ground_y:
                    # after 3 steps (the hold-driven orbiting -> falling
                    # transition has happened), force the sprite past
                    # ground_y so this scenario actually reaches
                    # "exploding" within a handful of ticks, exercising
                    # the enter_exploding hook (spawn + call_callback) and
                    # the despawn-on-the-following-tick path too --
                    # identically in both runs, since both are driven by
                    # this same scripted sequence.
                    game.enemies._live[0].y = 60
                behavior.step(game.enemies)
                snapshots.append(self._snapshot_pool(game.enemies, fields))
                snapshots.append(len(game.explosions))
                snapshots.append(len(calls))
            return snapshots

        readable_snapshots = run(readable_cls)
        fast_snapshots = run(fast_cls)
        self.assertEqual(readable_snapshots, fast_snapshots)
        # Sanity: the scenario really does reach "exploding" (spawn +
        # call_callback + eventual despawn), not just "orbiting"/"falling".
        self.assertGreater(readable_snapshots[-1], 0)  # on_death called

    def test_damageable_parity_across_hits_invulnerability_and_death(self):
        readable_cls, fast_cls = self._load_both(damageable_model(), "generated_damageable_parity")
        fields = ("x", "y", "damage_taken", "invuln_left", "visible")

        def run(behavior_cls):
            self._fresh_runtime()
            deaths = []

            class Game(vs2.Scene):
                idle_timeout = None
                back_button = False

                def build(self):
                    self.world = self.layer("world", projection=vs2.TUNNEL)
                    self.enemies = self.world.sprite_pool("ship.png", count=1)
                    self.bullets = self.world.sprite_pool("ship.png", count=1)
                    self.explosions = self.world.sprite_pool("ship.png", count=1)
                    self.enemies.behave(behavior_cls(
                        hp=2, invulnerable_ticks=2, blink=True,
                        hits=self.bullets, explosion=self.explosions, score=40,
                        on_death=lambda sprite, points: deaths.append(points)))

                def update(self):
                    pass

            game = Game()
            director.push(game)
            game.enemies.spawn(10, 10)
            game.bullets.spawn(10, 10)  # stays overlapping throughout

            behavior = game.enemies.behavior(behavior_cls)
            snapshots = []
            for _ in range(6):
                behavior.step(game.enemies)
                snapshots.append(self._snapshot_pool(game.enemies, fields))
                snapshots.append(len(game.explosions))
                snapshots.append(tuple(deaths))
            return snapshots

        readable_snapshots = run(readable_cls)
        fast_snapshots = run(fast_cls)
        self.assertEqual(readable_snapshots, fast_snapshots)
        self.assertEqual(readable_snapshots[-1], (40,))  # died once, score 40


# ---------------------------------------------------------------------------
# T17 Phase 3: the line-map's real-MicroPython half. "CPython-side is
# enough" for the *resolver itself* (see linemap.py's own docstring) --
# what genuinely needs a real interpreter is proving that the traceback a
# real MicroPython process actually raises (line numbers, ``File "..."``
# spelling) is exactly what LineMapTests's own synthetic examples assume.
# Shells out to a real ``micropython`` unix-port subprocess the same way
# tools/vs2_scene_gen/recover.py does, and for the identical reason (this
# is specifically about what the *real* interpreter reports, so a CPython
# approximation would defeat the point) -- skipped outright when
# ``micropython`` is not on PATH, matching that module's own test's
# convention.
# ---------------------------------------------------------------------------

MICROPYTHON_AVAILABLE = shutil.which("micropython") is not None


@unittest.skipUnless(MICROPYTHON_AVAILABLE, "micropython (unix port) not on PATH")
class RealTracebackLineMapTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="vs2_behavior_gen_linemap_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _minimal_broken_model(self):
        """A deliberately minimal model -- one param, one accumulate node,
        no Actions at all -- so ``attached()`` is a plain ``pass`` and the
        driver script below needs no real Sprite/SpritePool/Family
        machinery to construct a usable instance. The point of this test
        is the line map, not full Behavior semantics -- Projectile's own
        richer model is already exercised behaviorally elsewhere
        (GeneratedProjectileBehaviorTests, FastBackendParityTests)."""
        return {
            "version": 1,
            "class_name": "GeneratedProjectile",
            "subject_kind": "pool",
            "params": [{"name": "speed_y", "type": "number", "default": 8}],
            "state": ["shot_flown"],
            "actions": [],
            "apply_to_all": [],
            "per_sprite": [
                {"kind": "accumulate", "state": "shot_flown", "block_id": "BLK_ACC",
                 "amount": {"kind": "param", "name": "speed_y"}},
            ],
        }

    def _capture_real_traceback(self, generated_path):
        """Run a driver script under the real ``micropython`` unix port
        that imports ``generated_path``, deliberately triggers an
        exception *inside* the generated ``step()`` (a pool sprite
        missing the ``state`` attribute the ``accumulate`` node reads/
        writes -- a plain ``AttributeError``, nothing model-specific),
        and prints the real traceback text via
        ``sys.print_exception(exc, io.StringIO())`` between two marker
        lines this method then extracts. Returns that traceback text."""
        driver_path = self.tmpdir / "run_broken.py"
        driver_path.write_text(
            "import io\n"
            "import sys\n"
            "sys.path.insert(0, 'apps/micropython')\n"
            "sys.path.insert(0, %r)\n"
            "\n"
            "from generated_projectile import GeneratedProjectile\n"
            "\n"
            "\n"
            "class FakeSprite:\n"
            "    pass  # deliberately missing shot_flown\n"
            "\n"
            "\n"
            "class FakePool:\n"
            "    _live = [FakeSprite()]\n"
            "\n"
            "\n"
            "behavior = GeneratedProjectile()\n"
            "try:\n"
            "    behavior.step(FakePool())\n"
            "except Exception as exc:\n"
            "    buf = io.StringIO()\n"
            "    sys.print_exception(exc, buf)\n"
            "    print('===TRACEBACK-START===')\n"
            "    print(buf.getvalue())\n"
            "    print('===TRACEBACK-END===')\n"
            % (str(self.tmpdir),)
        )
        result = subprocess.run(
            ["micropython", str(driver_path)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        stdout = result.stdout
        start = stdout.index("===TRACEBACK-START===") + len("===TRACEBACK-START===\n")
        end = stdout.index("===TRACEBACK-END===")
        return stdout[start:end]

    def test_real_micropython_traceback_resolves_to_the_right_block(self):
        model = self._minimal_broken_model()
        generated_path = self.tmpdir / "generated_projectile.py"
        generator.write_behavior_file(model, generated_path)
        source = generated_path.read_text()

        traceback_text = self._capture_real_traceback(generated_path)
        self.assertIn("AttributeError", traceback_text)
        self.assertIn("generated_projectile.py", traceback_text)

        result = linemap.resolve_traceback_blocks(
            traceback_text, "generated_projectile.py", source)
        self.assertEqual(len(result), 1, (traceback_text, result))
        self.assertEqual(result[0]["block_id"], "BLK_ACC")

        # And the resolved line is genuinely the accumulate line, not a
        # coincidence -- cross-checked against the file's own text.
        lines = source.splitlines()
        self.assertIn("shot_flown +=", lines[result[0]["line"] - 1])

    def test_real_micropython_traceback_resolves_correctly_for_the_fast_backend_too(self):
        # Same scenario, fast backend -- the accumulate line now reads a
        # hoisted local instead of self.speed_y, but it is still the
        # exact line the AttributeError is raised on, and it still
        # carries BLK_ACC's own trailing comment (see generator.py's
        # _with_block_comment: hoisting doesn't touch block comments).
        model = self._minimal_broken_model()
        generated_path = self.tmpdir / "generated_projectile.py"
        generator.write_behavior_file(model, generated_path, backend="fast")
        source = generated_path.read_text()

        traceback_text = self._capture_real_traceback(generated_path)
        result = linemap.resolve_traceback_blocks(
            traceback_text, "generated_projectile.py", source)
        self.assertEqual(len(result), 1, (traceback_text, result))
        self.assertEqual(result[0]["block_id"], "BLK_ACC")


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
