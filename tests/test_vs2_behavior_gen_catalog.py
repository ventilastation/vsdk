"""Tests for tools/vs2_behavior_gen/catalog.py -- the offline Action/
Behavior catalog the block editor's palette is generated from.

Pure CPython. Imports the real ``vs2.actions``/``vs2.behaviors`` modules
(see ``catalog.py``'s own docstring for why that is safe with no
``configure_runtime()``/hardware setup). Run: ``python3
tests/test_vs2_behavior_gen_catalog.py``.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.vs2_behavior_gen import catalog


class ActionCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = catalog.build_catalog()

    def test_exactly_the_phase_one_action_classes(self):
        names = [entry["name"] for entry in self.catalog["actions"]]
        self.assertEqual(names, ["Move", "MoveTo", "Animate", "Collide"])

    def test_move_params_are_fully_introspected(self):
        move = next(e for e in self.catalog["actions"] if e["name"] == "Move")
        param_names = {p["name"] for p in move["params"]}
        self.assertEqual(param_names, {"speed_x", "speed_y", "accel_x", "accel_y"})
        self.assertEqual(move["extra_fields"], [])
        speed_y = next(p for p in move["params"] if p["name"] == "speed_y")
        self.assertEqual(speed_y["type"], "number")
        self.assertEqual(speed_y["default"], 0)
        self.assertEqual(speed_y["min"], -32)
        self.assertEqual(speed_y["max"], 32)

    def test_collide_has_no_introspected_params_but_real_extra_fields(self):
        """The real spec-vs-shipped-catalog mismatch this module's docstring
        documents: Collide's targets/radius/space are plain constructor
        keywords, not declared vs2.params.Parameter attributes, so
        introspect() alone sees nothing."""
        collide = next(e for e in self.catalog["actions"] if e["name"] == "Collide")
        self.assertEqual(collide["params"], [])
        extra_names = {f["name"] for f in collide["extra_fields"]}
        self.assertEqual(extra_names, {"targets", "radius", "space"})
        targets = next(f for f in collide["extra_fields"] if f["name"] == "targets")
        self.assertTrue(targets["required"])
        space = next(f for f in collide["extra_fields"] if f["name"] == "space")
        self.assertEqual(space["default"], "world")
        self.assertEqual(space["options"], ["world", "screen"])

    def test_animate_field_is_an_extra_field_not_a_declared_parameter(self):
        animate = next(e for e in self.catalog["actions"] if e["name"] == "Animate")
        param_names = {p["name"] for p in animate["params"]}
        self.assertNotIn("field", param_names)
        extra_names = {f["name"] for f in animate["extra_fields"]}
        self.assertIn("field", extra_names)

    def test_every_action_has_a_doc_summary(self):
        for entry in self.catalog["actions"]:
            self.assertTrue(entry["doc"], entry["name"])


class BehaviorCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = catalog.build_catalog()
        self.by_name = {e["name"]: e for e in self.catalog["behaviors"]}

    def test_exactly_the_phase_two_behavior_classes_no_shufflebag(self):
        """StateMachine joined the catalog in Phase 2 -- see catalog.py's
        own docstring for why it is listed even though (unlike every other
        entry here) a block program's generated class really does
        subclass it directly."""
        expected = {
            "Projectile", "Transient", "Lifetime", "DespawnBeyond", "Recycling",
            "Blinking", "Pinned", "Shaking", "Animated", "Moving", "Patrolling",
            "PathFollowing", "Pilotable", "Aiming", "Chasing", "Orbiting", "Laned",
            "StateMachine",
        }
        self.assertEqual(set(self.by_name), expected)
        self.assertNotIn("ShuffleBag", self.by_name)
        self.assertNotIn("Damageable", self.by_name)  # not a real shipped Behavior

    def test_state_machine_has_no_introspected_params_or_state_but_real_extra_notes(self):
        """The real gap this module's EXTRA_BEHAVIOR_NOTES patches:
        StateMachine's base class declares no vs2.params.Parameter and
        primes its three fsm_* fields by hand rather than via state = (...)
        -- see catalog.py's own docstring for the full reasoning."""
        state_machine = self.by_name["StateMachine"]
        self.assertEqual(state_machine["params"], [])
        self.assertEqual(state_machine["state"], [])
        self.assertEqual(state_machine["subject_kinds"], ["pool", "sprite"])
        self.assertEqual(state_machine["extra"], {
            "structural_attrs": ["states", "initial"],
            "reserved_state": ["fsm_state", "fsm_hold", "fsm_then"],
        })

    def test_every_other_behavior_has_an_empty_extra_dict(self):
        for entry in self.catalog["behaviors"]:
            if entry["name"] == "StateMachine":
                continue
            self.assertEqual(entry["extra"], {}, entry["name"])

    def test_projectile_is_pool_only(self):
        """Projectile.step() exists; it defines no step_one/step_scene --
        see apps/micropython/vs2/behaviors.py. This is the exact
        subject-kind constraint the dispatch logic in vs2/__init__.py's
        _behavior_kind_mismatch enforces at attach time."""
        self.assertEqual(self.by_name["Projectile"]["subject_kinds"], ["pool"])
        self.assertEqual(self.by_name["Projectile"]["state"], ["shot_flown"])

    def test_moving_supports_both_pool_and_sprite(self):
        self.assertEqual(self.by_name["Moving"]["subject_kinds"], ["pool", "sprite"])

    def test_every_behavior_param_list_is_name_sorted(self):
        for entry in self.catalog["behaviors"]:
            names = [p["name"] for p in entry["params"]]
            self.assertEqual(names, sorted(names), entry["name"])

    def test_no_behavior_declares_scene_subject_kind_in_phase_one_catalog(self):
        """Spawner/FiringAt (scene-subject Behaviors) are not shipped in
        this catalog list at all yet -- see the T17 dispatch card's fixed
        list -- so nothing here should report "scene"."""
        for entry in self.catalog["behaviors"]:
            self.assertNotIn("scene", entry["subject_kinds"], entry["name"])


class WriteCatalogTests(unittest.TestCase):
    def test_write_catalog_produces_valid_json_matching_build_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vs2-behavior-catalog.json"
            written = catalog.write_catalog(path)
            on_disk = json.loads(path.read_text())
            self.assertEqual(written, on_disk)
            self.assertTrue(path.read_text().endswith("\n"))

    def test_committed_web_catalog_matches_a_fresh_build(self):
        """web/vs2-behavior-catalog.json is committed (mirroring
        web/runtime-manifest.json's own established pattern -- see
        generate_catalog.py's docstring for why); this is the drift guard
        that would catch someone editing vs2/behaviors.py or actions.py
        without re-running the generator."""
        committed_path = Path(ROOT) / "web" / "vs2-behavior-catalog.json"
        self.assertTrue(committed_path.exists(), "run generate_catalog.py first")
        committed = json.loads(committed_path.read_text())
        fresh = catalog.build_catalog()
        self.assertEqual(committed, fresh)


if __name__ == "__main__":
    unittest.main()
