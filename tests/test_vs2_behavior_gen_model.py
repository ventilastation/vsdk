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


def _binary_op(op, left, right):
    return {"kind": "binary_op", "op": op, "left": left, "right": right}


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


def _state_machine_model(**overrides):
    """A small state-hat model exercising every Phase 2 node kind:
    ``hold``/``goto_state`` (state-body-only) plus ``set_state``/
    ``call_callback``/``spawn``/``play_sound`` (usable in either shape).
    Shaped like ``games/vs2_examples/vasura_states_demo``'s real model,
    trimmed to what this file's tests need."""
    model = {
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
                    "enter": [{"kind": "hold", "ticks": _literal(3), "then": "falling"}],
                    "step": [{"kind": "if_action", "bind": "hit",
                              "then": [{"kind": "goto_state", "name": "exploding"}],
                              "else": []}],
                },
                "falling": {
                    "step": [
                        {"kind": "accumulate", "state": "frames_left", "amount": _literal(1)},
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
                    "exit": [{"kind": "set_state", "state": "frames_left", "value": _literal(0)}],
                },
            },
        },
    }
    model.update(overrides)
    return model


def _damageable_model(**overrides):
    """The Damageable reference model -- see this task's report for the
    full design reasoning (hp counts up via ``damage_taken``, matching
    Transient/Blinking/Lifetime's own "elapsed compared to a limit" idiom,
    rather than counting a "remaining hp" down; invulnerability is a
    countdown state field reset on every fresh hit; "blink" is a plain
    hide-then-show rather than true alternating blink, since this
    schema's expression vocabulary has no modulo -- a game wanting real
    alternating blink composes the real vs2.behaviors.Blinking Behavior
    alongside this one instead)."""
    model = {
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
            # One top-level if/else, deliberately -- "currently
            # invulnerable" and "check for a fresh hit" are mutually
            # exclusive within a single tick. Splitting these into two
            # separate top-level nodes (tried first; see this task's
            # report) let a hit that *sets* invuln_left this same tick
            # immediately get re-decremented by a second, independent
            # node right after -- silently shortening the configured
            # window by one tick's worth of protection on every hit. One
            # if/else makes that impossible: whichever branch runs this
            # tick, the other cannot also run.
            {"kind": "if_else",
             "condition": {"kind": "compare", "op": ">",
                            "left": _state_ref("invuln_left"), "right": _literal(0)},
             "then": [
                 # Still invulnerable: tick the countdown down, and
                 # restore visibility (if "blink" hid the sprite) the
                 # tick it reaches zero.
                 {"kind": "accumulate", "state": "invuln_left", "amount": _literal(-1)},
                 {"kind": "if_else",
                  "condition": {"kind": "compare", "op": "<=",
                                 "left": _state_ref("invuln_left"), "right": _literal(0)},
                  "then": [
                      {"kind": "if_else",
                       "condition": {"kind": "compare", "op": "==",
                                      "left": _param_ref("blink"), "right": _literal(True)},
                       "then": [{"kind": "set_state", "state": "visible",
                                 "value": _literal(True)}],
                       "else": []},
                  ],
                  "else": []},
             ],
             "else": [
                 # Not invulnerable: check for a fresh hit.
                 {"kind": "if_action", "bind": "hit",
                  "then": [
                      {"kind": "accumulate", "state": "damage_taken", "amount": _literal(1)},
                      {"kind": "set_state", "state": "invuln_left",
                       "value": _param_ref("invulnerable_ticks")},
                      {"kind": "if_else",
                       "condition": {"kind": "compare", "op": "==",
                                      "left": _param_ref("blink"), "right": _literal(True)},
                       "then": [{"kind": "set_state", "state": "visible",
                                 "value": _literal(False)}],
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
    model.update(overrides)
    return model


class DamageableModelTests(unittest.TestCase):
    """Phase 2: Damageable, a plain Behavior (not a state machine) built
    entirely from Phase 1's node kinds plus this phase's four additions --
    proves the new nodes are genuinely usable outside a state hat, not
    only inside one."""

    def test_the_damageable_model_validates(self):
        validate_model(_damageable_model())  # must not raise


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


class StateHatModelTests(unittest.TestCase):
    """Phase 2: model.state_machine's schema."""

    def test_the_state_machine_model_validates(self):
        validate_model(_state_machine_model())  # must not raise

    def test_a_state_with_no_enter_or_exit_hook_is_legal(self):
        model = _state_machine_model()
        model["state_machine"]["bodies"]["falling"] = {"step": []}
        validate_model(model)

    def test_states_and_state_machine_together_reject_apply_to_all(self):
        model = _state_machine_model()
        model["apply_to_all"] = ["hit"]
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_states_and_state_machine_together_reject_per_sprite(self):
        model = _state_machine_model()
        model["per_sprite"] = [{"kind": "despawn"}]
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_empty_states_list_rejected(self):
        model = _state_machine_model()
        model["state_machine"]["states"] = []
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_initial_not_one_of_states_rejected(self):
        model = _state_machine_model()
        model["state_machine"]["initial"] = "nonexistent"
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_duplicate_state_name_rejected(self):
        model = _state_machine_model()
        model["state_machine"]["states"].append("orbiting")
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_state_name_colliding_with_declared_param_rejected(self):
        model = _state_machine_model()
        model["state_machine"]["states"][0] = "ground_y"  # already a param
        model["state_machine"]["bodies"]["ground_y"] = model["state_machine"]["bodies"].pop("orbiting")
        model["state_machine"]["initial"] = "ground_y"
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_state_name_colliding_with_reserved_statemachine_name_rejected(self):
        model = _state_machine_model()
        model["state_machine"]["states"][0] = "hold"  # StateMachine.hold()
        model["state_machine"]["bodies"]["hold"] = model["state_machine"]["bodies"].pop("orbiting")
        model["state_machine"]["initial"] = "hold"
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_missing_body_for_a_declared_state_rejected(self):
        model = _state_machine_model()
        del model["state_machine"]["bodies"]["falling"]
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_body_for_an_undeclared_state_rejected(self):
        model = _state_machine_model()
        model["state_machine"]["bodies"]["nonexistent"] = {"step": []}
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_body_missing_step_rejected(self):
        model = _state_machine_model()
        model["state_machine"]["bodies"]["falling"] = {"enter": []}
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_goto_state_to_undeclared_state_rejected(self):
        model = _state_machine_model()
        model["state_machine"]["bodies"]["falling"]["step"][1]["then"][0]["name"] = "nonexistent"
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_hold_then_undeclared_state_rejected(self):
        model = _state_machine_model()
        model["state_machine"]["bodies"]["orbiting"]["enter"][0]["then"] = "nonexistent"
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_goto_state_rejected_outside_a_state_body(self):
        """goto_state/hold only mean anything inside a state's own body --
        a plain Behavior's flat per_sprite list (no state_machine at all)
        must reject them, matching every other undeclared-kind rejection."""
        model = _projectile_model()
        model["per_sprite"].append({"kind": "goto_state", "name": "whatever"})
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_hold_rejected_outside_a_state_body(self):
        model = _projectile_model()
        model["per_sprite"].append(
            {"kind": "hold", "ticks": _literal(1), "then": "whatever"})
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_set_state_call_callback_spawn_play_sound_all_usable_in_plain_per_sprite(self):
        """The four Phase 2 node kinds that are *not* state-body-only work
        in a plain Behavior's flat per_sprite list too -- Damageable is
        built exactly this way (see tools/vs2_behavior_gen's Damageable
        model), with no state_machine at all."""
        model = _projectile_model(state=["shot_flown", "counter"])
        model["params"].append(_param("boom", "pool", None))
        model["params"].append(_param("bang", "sound", None))
        model["params"].append(_param("notify", "callback", None))
        model["per_sprite"] = [
            {"kind": "set_state", "state": "counter", "value": _literal(0)},
            {"kind": "call_callback", "name": "notify", "args": [_state_ref("counter")]},
            {"kind": "spawn", "pool": "boom", "x": _state_ref("x"), "y": _state_ref("y")},
            {"kind": "play_sound", "name": "bang"},
        ]
        validate_model(model)

    def test_call_callback_referencing_undeclared_param_rejected(self):
        model = _projectile_model()
        model["per_sprite"].append(
            {"kind": "call_callback", "name": "nonexistent", "args": []})
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_spawn_referencing_undeclared_pool_param_rejected(self):
        model = _projectile_model()
        model["per_sprite"].append(
            {"kind": "spawn", "pool": "nonexistent",
             "x": _literal(0), "y": _literal(0)})
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_play_sound_referencing_undeclared_param_rejected(self):
        model = _projectile_model()
        model["per_sprite"].append({"kind": "play_sound", "name": "nonexistent"})
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_sprite_x_and_y_usable_as_a_state_expression(self):
        """The built-in Sprite fields spawn's x/y arguments need -- see
        model.py's BUILTIN_SPRITE_FIELDS docstring -- work as a "state"
        expression even though neither is a declared per-sprite state
        field."""
        model = _projectile_model()
        model["per_sprite"][0]["amount"] = _state_ref("x")
        validate_model(model)

    def test_arbitrary_sprite_attribute_not_usable_as_a_state_expression(self):
        model = _projectile_model()
        model["per_sprite"][0]["amount"] = _state_ref("frame")
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_set_state_can_target_the_builtin_visible_field(self):
        model = _projectile_model()
        model["per_sprite"].append(
            {"kind": "set_state", "state": "visible", "value": {"kind": "literal", "value": False}})
        validate_model(model)

    def test_accumulate_can_also_target_a_builtin_sprite_field(self):
        """accumulate accepts the built-in x/y fields too, alongside a
        declared state field -- see model.py's own "accumulate" docstring
        comment for why (a state-hat body driving descent directly, e.g.
        this task's own vasura_states_demo "falling" state, is exactly as
        legitimate as Recycling's own direct sprite.x/y writes)."""
        model = _projectile_model()
        model["per_sprite"].append(
            {"kind": "accumulate", "state": "y", "amount": {"kind": "literal", "value": 1}})
        validate_model(model)

    def test_accumulate_still_rejects_a_genuinely_unknown_field(self):
        model = _projectile_model()
        model["per_sprite"].append(
            {"kind": "accumulate", "state": "frame", "amount": {"kind": "literal", "value": 1}})
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_bool_literal_is_now_a_legal_expression_value(self):
        model = _projectile_model()
        model["per_sprite"][0]["amount"] = {"kind": "literal", "value": True}
        validate_model(model)

    def test_binary_op_validates(self):
        model = _projectile_model()
        model["per_sprite"][0]["amount"] = _binary_op(
            "-", _param_ref("speed_y"), _literal(1))
        validate_model(model)

    def test_binary_op_min_max_validate(self):
        model = _projectile_model()
        model["per_sprite"][0]["amount"] = _binary_op(
            "max", _literal(0), _binary_op("-", _state_ref("shot_flown"), _literal(3)))
        validate_model(model)

    def test_binary_op_nests_inside_a_condition(self):
        model = _projectile_model()
        model["per_sprite"][1]["condition"]["right"] = _binary_op(
            "+", _param_ref("range"), _literal(10))
        validate_model(model)

    def test_binary_op_unknown_operator_rejected(self):
        model = _projectile_model()
        model["per_sprite"][0]["amount"] = _binary_op("^", _literal(1), _literal(2))
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_binary_op_missing_right_rejected(self):
        model = _projectile_model()
        model["per_sprite"][0]["amount"] = {
            "kind": "binary_op", "op": "+", "left": _literal(1)}
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_binary_op_rejects_a_bad_nested_operand(self):
        model = _projectile_model()
        model["per_sprite"][0]["amount"] = _binary_op(
            "+", _literal(1), _param_ref("not_a_declared_param"))
        with self.assertRaises(ModelError):
            validate_model(model)

    def test_enter_exit_hook_collision_between_states_rejected(self):
        """A state literally named enter_<other state> would generate the
        same method name as that other state's own enter_ hook --
        "orbiting" declares an "enter" hook (-> enter_orbiting), so a
        state named exactly that collides with it."""
        model = _state_machine_model()
        model["state_machine"]["states"].append("enter_orbiting")
        model["state_machine"]["bodies"]["enter_orbiting"] = {"step": []}
        with self.assertRaises(ModelError):
            validate_model(model)


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


# ---------------------------------------------------------------------------
# T17 Phase 3: the optional "block_id"
# ---------------------------------------------------------------------------

class BlockIdModelTests(unittest.TestCase):
    def test_accepts_block_id_on_action_decl_and_per_sprite_nodes(self):
        model = _projectile_model()
        model["actions"][0]["block_id"] = "BLK_MOVE"
        model["per_sprite"][0]["block_id"] = "BLK_ACC"
        model["per_sprite"][1]["block_id"] = "BLK_IF"
        model["per_sprite"][1]["else"][0]["block_id"] = "BLK_IFACTION"
        self.assertIsNone(validate_model(model))

    def test_accepts_block_id_on_every_state_body_node_kind(self):
        model = _state_machine_model()
        self.assertIsNone(validate_model(model))
        # Tag every node kind actually present with a block_id and confirm
        # none of them are rejected.
        for body in model["state_machine"]["bodies"].values():
            for hook in ("enter", "step", "exit"):
                for node in body.get(hook, []):
                    node["block_id"] = "BLK_%s" % (node["kind"],)
        self.assertIsNone(validate_model(model))

    def test_rejects_non_string_block_id(self):
        model = _projectile_model()
        model["per_sprite"][0]["block_id"] = 7
        with self.assertRaises(ModelError) as ctx:
            validate_model(model)
        self.assertIn("block_id", str(ctx.exception))

    def test_rejects_empty_string_block_id_on_action_decl(self):
        model = _projectile_model()
        model["actions"][0]["block_id"] = ""
        with self.assertRaises(ModelError) as ctx:
            validate_model(model)
        self.assertIn("block_id", str(ctx.exception))

    def test_omitting_block_id_still_validates(self):
        self.assertIsNone(validate_model(_projectile_model()))
        self.assertIsNone(validate_model(_state_machine_model()))


if __name__ == "__main__":
    unittest.main()
