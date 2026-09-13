"""Tests for tools/vs2_behavior_gen/model.py -- the block-program schema.

Pure CPython, no MicroPython shims, no import of the real ``vs2`` package
(matching ``tools/vs2_scene_gen``/``tools/vs2_event_gen``'s own model
modules). Run: ``python3 tests/test_vs2_behavior_gen_model.py``.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.vs2_behavior_gen.model import ModelError, validate_model


def _param(name, type_="number", default=0, **extra):
    entry = {"name": name, "type": type_, "default": default}
    entry.update(extra)
    return entry


def _literal(value):
    return {"kind": "literal", "value": value}


def _param_ref(name):
    return {"kind": "param", "name": name}


def _state_ref(name):
    return {"kind": "state", "name": name}


def _projectile_model(**overrides):
    model = {
        "version": 1,
        "class_name": "GeneratedProjectile",
        "subject_kind": "pool",
        "params": [
            _param("speed_x", "angle", 0, min=-32, max=32, step=0.25),
            _param("speed_y", "number", 8, min=-32, max=32, step=0.25),
            _param("range", "number", 180, min=1, max=255, step=1),
            _param("hits", "pool", None),
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
    model.update(overrides)
    return model


class ValidModelTests(unittest.TestCase):
    def test_the_projectile_model_validates(self):
        validate_model(_projectile_model())  # must not raise

    def test_sprite_subject_kind_validates_too(self):
        model = _projectile_model(subject_kind="sprite")
        validate_model(model)

    def test_empty_actions_and_per_sprite_are_legal(self):
        validate_model({
            "version": 1, "class_name": "Empty", "subject_kind": "pool",
            "params": [], "state": [], "actions": [], "apply_to_all": [], "per_sprite": [],
        })


class InvalidModelTests(unittest.TestCase):
    def test_wrong_version_rejected(self):
        model = _projectile_model(version=2)
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_bad_class_name_rejected(self):
        for bad in ("not an identifier", "123start", "class", ""):
            with self.assertRaises(ModelError):
                validate_model(_projectile_model(class_name=bad))

    def test_bad_subject_kind_rejected(self):
        with self.assertRaises(ModelError):
            validate_model(_projectile_model(subject_kind="scene"))

    def test_unknown_action_class_rejected(self):
        model = _projectile_model()
        model["actions"][0]["action_class"] = "Spawn"  # not shipped yet
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_action_referencing_unknown_field_rejected(self):
        model = _projectile_model()
        model["actions"][0]["args"]["not_a_real_field"] = _literal(1)
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_collide_missing_required_targets_rejected(self):
        model = _projectile_model()
        model["actions"][1]["args"] = {}
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_duplicate_action_bind_rejected(self):
        model = _projectile_model()
        model["actions"].append(dict(model["actions"][0]))
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_apply_to_all_referencing_undeclared_action_rejected(self):
        model = _projectile_model()
        model["apply_to_all"].append("nonexistent")
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_param_ref_to_undeclared_param_rejected(self):
        model = _projectile_model()
        model["per_sprite"][0]["amount"] = _param_ref("not_declared")
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_state_ref_to_undeclared_state_rejected(self):
        model = _projectile_model()
        model["per_sprite"][1]["condition"]["left"] = _state_ref("not_declared")
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_if_action_referencing_undeclared_bind_rejected(self):
        model = _projectile_model()
        model["per_sprite"][1]["else"][0]["bind"] = "nonexistent"
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_state_name_colliding_with_a_reserved_framework_name_rejected(self):
        model = _projectile_model()
        model["state"] = ["dx"]  # reserved: the Move accumulator field
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_state_name_colliding_with_a_declared_param_rejected(self):
        model = _projectile_model()
        model["state"] = ["range"]  # already a declared parameter name
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_duplicate_param_name_rejected(self):
        model = _projectile_model()
        model["params"].append(dict(model["params"][0]))
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_bad_compare_op_rejected(self):
        model = _projectile_model()
        model["per_sprite"][1]["condition"]["op"] = "<>"
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_unknown_per_sprite_kind_rejected(self):
        model = _projectile_model()
        model["per_sprite"].append({"kind": "spawn_something"})
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_unknown_top_level_key_rejected(self):
        model = _projectile_model()
        model["unknown_extra_key"] = 1
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_error_message_names_the_offending_path(self):
        model = _projectile_model()
        model["per_sprite"][0]["amount"] = _param_ref("bogus")
        with self.assertRaises(ModelError) as ctx:
            validate_model(model)
        self.assertIn("model.per_sprite[0].amount", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
