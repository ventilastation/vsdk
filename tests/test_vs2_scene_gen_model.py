"""Tests for tools/vs2_scene_gen/model.py -- the scene-model schema.

Pure CPython, no MicroPython shims: this package only ever runs under a
desktop toolchain, never on-device. Run: ``python3 tests/test_vs2_scene_gen_model.py``.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.vs2_scene_gen.model import ModelError, validate_model


def _valid_model():
    return {
        "version": 1,
        "class_name": "DemoScene",
        "vars": [{"name": "score", "default": 0, "min": 0}],
        "layers": [
            {
                "attr": "world",
                "projection": "TUNNEL",
                "drawables": [
                    {
                        "kind": "sprite_pool",
                        "attr": "enemies",
                        "image": "enemy.png",
                        "count": 6,
                        "on_empty": "RECYCLE",
                        "vars": [{"name": "kind", "default": 0, "min": 0, "max": 2}],
                        "kinds": {"rows": {"basic": [0], "tough": [2]}},
                        "behaviors": [
                            {"class": "Moving", "params": {"speed_y": -1}},
                            {
                                "class": "Transient",
                                "name": "burn",
                                "params": {"ticks": 18, "on_end": {"handler": "enemy_died"}},
                            },
                        ],
                    },
                    {"kind": "sprite", "attr": "boss", "image": "boss.png", "x": 10, "y": 5},
                ],
            }
        ],
        "families": [{"attr": "hostiles", "members": ["enemies"]}],
        "scene_behaviors": [],
    }


class ValidModelTests(unittest.TestCase):
    def test_accepts_the_documented_example(self):
        self.assertIsNone(validate_model(_valid_model()))

    def test_accepts_a_model_with_no_drawables_at_all(self):
        model = _valid_model()
        model["layers"][0]["drawables"] = []
        del model["families"]
        self.assertIsNone(validate_model(model))

    def test_accepts_tunnel_projection_dict_form(self):
        model = _valid_model()
        model["layers"][0]["projection"] = {"tunnel": {"gamma": 0.3, "near": 1, "far": 40}}
        self.assertIsNone(validate_model(model))

    def test_accepts_ref_and_var_and_handler_and_expr_values(self):
        model = _valid_model()
        model["layers"][0]["drawables"][1]["x"] = {"ref": "enemies"}
        model["layers"][0]["drawables"][1]["y"] = {"var": "score"}
        model["layers"][0]["drawables"][0]["behaviors"][1]["params"]["on_end"] = {
            "handler": "enemy_died"
        }
        model["layers"][0]["drawables"][1]["frame"] = {"expr": "vs2.display.width"}
        self.assertIsNone(validate_model(model))


class RejectModelTests(unittest.TestCase):
    def assert_rejects(self, model, path_fragment):
        with self.assertRaises(ModelError) as ctx:
            validate_model(model)
        self.assertIn(path_fragment, str(ctx.exception))

    def test_wrong_version(self):
        model = _valid_model()
        model["version"] = 2
        self.assert_rejects(model, "model.version")

    def test_class_name_is_a_keyword(self):
        model = _valid_model()
        model["class_name"] = "class"
        self.assert_rejects(model, "model.class_name")

    def test_class_name_not_an_identifier(self):
        model = _valid_model()
        model["class_name"] = "123Scene"
        self.assert_rejects(model, "model.class_name")

    def test_no_layers(self):
        model = _valid_model()
        model["layers"] = []
        self.assert_rejects(model, "model.layers")

    def test_duplicate_attr_across_layer_and_drawable(self):
        model = _valid_model()
        model["layers"][0]["drawables"][1]["attr"] = "world"
        self.assert_rejects(model, "layers[0].drawables[1].attr")

    def test_reserved_attr_leading_underscore(self):
        model = _valid_model()
        model["layers"][0]["drawables"][1]["attr"] = "_secret"
        self.assert_rejects(model, "layers[0].drawables[1].attr")

    def test_reserved_attr_on_build_prefix(self):
        model = _valid_model()
        model["layers"][0]["drawables"][1]["attr"] = "on_build_0"
        self.assert_rejects(model, "layers[0].drawables[1].attr")

    def test_unknown_drawable_kind(self):
        model = _valid_model()
        model["layers"][0]["drawables"][1]["kind"] = "particle"
        self.assert_rejects(model, "layers[0].drawables[1].kind")

    def test_sprite_pool_count_must_be_positive(self):
        model = _valid_model()
        model["layers"][0]["drawables"][0]["count"] = 0
        self.assert_rejects(model, "layers[0].drawables[0].count")

    def test_sprite_pool_kinds_row_length_mismatch(self):
        model = _valid_model()
        model["layers"][0]["drawables"][0]["kinds"]["rows"]["basic"] = [0, 1]
        self.assert_rejects(model, "layers[0].drawables[0].kinds.rows.basic")

    def test_unknown_key_on_drawable(self):
        model = _valid_model()
        model["layers"][0]["drawables"][1]["bogus"] = True
        self.assert_rejects(model, "layers[0].drawables[1]")

    def test_ref_to_undeclared_attr(self):
        model = _valid_model()
        model["layers"][0]["drawables"][1]["x"] = {"ref": "nonexistent"}
        self.assert_rejects(model, "layers[0].drawables[1].x.ref")

    def test_family_member_not_declared_earlier(self):
        model = _valid_model()
        model["families"][0]["members"] = ["nonexistent"]
        self.assert_rejects(model, "families[0].members")

    def test_behavior_missing_class(self):
        model = _valid_model()
        model["scene_behaviors"] = [{"params": {}}]
        self.assert_rejects(model, "scene_behaviors[0].class")

    def test_tilemap_requires_positive_columns_and_rows(self):
        model = _valid_model()
        model["layers"][0]["drawables"].append(
            {"kind": "tilemap", "attr": "grid", "image": "tiles.png", "columns": 0, "rows": 4}
        )
        self.assert_rejects(model, "layers[0].drawables[2].columns")

    def test_value_dict_with_wrong_tag(self):
        model = _valid_model()
        model["layers"][0]["drawables"][1]["x"] = {"literal": 3}
        self.assert_rejects(model, "layers[0].drawables[1].x")

    def test_model_is_not_a_dict(self):
        with self.assertRaises(ModelError):
            validate_model([])


if __name__ == "__main__":
    unittest.main()
