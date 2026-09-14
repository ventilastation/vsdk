"""Tests for tools/vs2_scene_gen/recover.py.

Two groups:

- ``ComparePayloadToModelTests`` -- pure logic, hand-built payload dicts
  (the same shape :func:`payload.parse_scene_payload` returns), no
  subprocess, always runs.
- ``RealMicropythonRoundTripTests`` -- builds a tiny synthetic game under
  ``games/`` and actually shells out to the real ``micropython`` unix
  binary via :func:`recover.capture_scene_payload`. Skipped, gracefully,
  if that binary is not on ``PATH`` -- same ``shutil.which`` pattern
  ``tests/run_tests.py``'s ``run_scripts`` uses, since dev/CI environments
  vary on whether it's installed.

Pure CPython otherwise: this package never runs on-device. Run:
``python3 tests/test_vs2_scene_gen_recover.py``.
"""

import copy
import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.vs2_scene_gen import generator, recover

MICROPYTHON_AVAILABLE = shutil.which("micropython") is not None


def _small_model():
    return {
        "version": 1,
        "class_name": "RoundtripScene",
        "layers": [
            {
                "attr": "world",
                "drawables": [
                    {"kind": "sprite", "attr": "dot", "image": "dot.png", "x": 10, "y": 5, "frame": 0},
                    {"kind": "sprite_pool", "attr": "pool", "image": "dot.png", "count": 3, "frame": 1},
                    {
                        "kind": "tilemap",
                        "attr": "grid",
                        "image": "box.png",
                        "columns": 2,
                        "rows": 2,
                        "x": 20,
                        "y": 1,
                    },
                ],
            }
        ],
    }


def _matching_payload():
    """A hand-built ``parsed_payload`` that agrees exactly with
    :func:`_small_model`, in the same shape
    :func:`payload.parse_scene_payload` returns."""
    return {
        "version": 3,
        "layers": [{"index": 0, "projection": 1, "visible": True, "camera_x": 0,
                     "camera_y": 0, "curve_index": 0}],
        "sprites": [
            {"layer_index": 0, "strip": 0, "frame": 0, "projection": 1, "visible": True,
             "flip_x": False, "flip_y": False, "x": 10.0, "y": 5.0},
            {"layer_index": 0, "strip": 0, "frame": 1, "projection": 1, "visible": False,
             "flip_x": False, "flip_y": False, "x": 0.0, "y": 0.0},
            {"layer_index": 0, "strip": 0, "frame": 1, "projection": 1, "visible": False,
             "flip_x": False, "flip_y": False, "x": 0.0, "y": 0.0},
            {"layer_index": 0, "strip": 0, "frame": 1, "projection": 1, "visible": False,
             "flip_x": False, "flip_y": False, "x": 0.0, "y": 0.0},
        ],
        "tilemaps": [
            {"layer_index": 0, "strip": 1, "visible": True, "flip_x": False, "flip_y": False,
             "columns": 2, "rows": 2, "tile_width": 4, "tile_height": 4, "view_x": 0,
             "view_y": 0, "view_width": 8, "view_height": 8, "x": 20.0, "y": 1.0,
             "cells": b"\xff\xff\xff\xff"},
        ],
        "drawables": [
            {"kind": "sprite", "index": 0},
            {"kind": "sprite", "index": 1},
            {"kind": "sprite", "index": 2},
            {"kind": "sprite", "index": 3},
            {"kind": "tilemap", "index": 0},
        ],
    }


class ComparePayloadToModelTests(unittest.TestCase):
    def test_matching_model_and_payload_report_no_mismatches(self):
        mismatches = recover.compare_payload_to_model(_small_model(), _matching_payload())
        self.assertEqual(mismatches, [])

    def test_drawable_count_mismatch_is_reported(self):
        model = _small_model()
        del model["layers"][0]["drawables"][1]  # drop the sprite_pool: model now expects 2
        mismatches = recover.compare_payload_to_model(model, _matching_payload())
        self.assertTrue(mismatches, "expected at least one mismatch")
        self.assertTrue(any("drawable count" in m for m in mismatches), mismatches)

    def test_layer_count_mismatch_is_reported(self):
        model = _small_model()
        payload = _matching_payload()
        payload["layers"] = payload["layers"] + copy.deepcopy(payload["layers"])
        mismatches = recover.compare_payload_to_model(model, payload)
        self.assertTrue(any("layer count" in m for m in mismatches), mismatches)

    def test_mismatched_image_identity_is_reported(self):
        # Force the tilemap's strip to collide with the (different-named)
        # sprite image's strip -- an internal inconsistency that must be
        # caught even though this function never sees image names on the
        # payload side.
        payload = _matching_payload()
        payload["tilemaps"][0]["strip"] = payload["sprites"][0]["strip"]
        mismatches = recover.compare_payload_to_model(_small_model(), payload)
        self.assertTrue(any("resolved to strip" in m for m in mismatches), mismatches)

    def test_same_image_used_twice_with_different_strips_is_reported(self):
        payload = _matching_payload()
        payload["sprites"][1]["strip"] = 5  # pool slot suddenly uses a different strip
        mismatches = recover.compare_payload_to_model(_small_model(), payload)
        self.assertTrue(any("elsewhere in the same scene" in m for m in mismatches), mismatches)

    def test_position_mismatch_is_reported(self):
        payload = _matching_payload()
        payload["sprites"][0]["x"] = 99.0
        mismatches = recover.compare_payload_to_model(_small_model(), payload)
        self.assertTrue(any("model x=10" in m for m in mismatches), mismatches)

    def test_frame_mismatch_is_reported(self):
        payload = _matching_payload()
        payload["sprites"][0]["frame"] = 7
        mismatches = recover.compare_payload_to_model(_small_model(), payload)
        self.assertTrue(any("model frame 0" in m for m in mismatches), mismatches)

    def test_sprite_vs_tilemap_kind_mismatch_is_reported(self):
        payload = _matching_payload()
        payload["drawables"][4] = {"kind": "sprite", "index": 0}
        mismatches = recover.compare_payload_to_model(_small_model(), payload)
        self.assertTrue(any("expected a tilemap" in m for m in mismatches), mismatches)

    def test_sprite_pool_slot_visible_true_is_reported(self):
        payload = _matching_payload()
        payload["sprites"][1]["visible"] = True
        mismatches = recover.compare_payload_to_model(_small_model(), payload)
        self.assertTrue(any("should start hidden" in m for m in mismatches), mismatches)

    def test_rejects_a_malformed_model_rather_than_a_bad_comparison(self):
        from tools.vs2_scene_gen.model import ModelError
        with self.assertRaises(ModelError):
            recover.compare_payload_to_model({"version": 999}, _matching_payload())


class CapturePayloadGuardTests(unittest.TestCase):
    def test_raises_recover_error_when_micropython_is_not_on_path(self):
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(recover.RecoverError):
                recover.capture_scene_payload("does.not.matter", ROOT)


@unittest.skipUnless(MICROPYTHON_AVAILABLE, "micropython (unix port) not on PATH")
class RealMicropythonRoundTripTests(unittest.TestCase):
    SLUG = "_vs2_scene_gen_fixtures.roundtrip"

    def setUp(self):
        parts = self.SLUG.split(".")
        self.game_dir = Path(ROOT) / "games" / parts[0] / parts[1]
        self.addCleanup(shutil.rmtree, Path(ROOT) / "games" / parts[0], ignore_errors=True)
        code_dir = self.game_dir / "code"
        code_dir.mkdir(parents=True)

        (self.game_dir / "meta.json").write_text(
            '{"api": "vs2", "api_revision": 2, "title": "Roundtrip fixture"}'
        )

        model = _small_model()
        scene_path = code_dir / "roundtrip_scene.py"
        result = generator.write_scene_file(model, scene_path)
        self.assertEqual(result.status, "created")

        (code_dir / "roundtrip.py").write_text(
            "from .roundtrip_scene import RoundtripScene\n"
            "\n"
            "\n"
            "def main():\n"
            "    from ventilastation.director import director, stripes\n"
            "\n"
            "    stripes.clear()\n"
            "    stripes['dot.png'] = 0\n"
            "    stripes['box.png'] = 1\n"
            "    director.image_metadata[0] = {'width': 4, 'height': 4, 'frames': 2,\n"
            "                                   'palette': 0, 'glyphs': None}\n"
            "    director.image_metadata[1] = {'width': 4, 'height': 4, 'frames': 1,\n"
            "                                   'palette': 0, 'glyphs': None}\n"
            "    # No real ROM for this synthetic fixture -- assets are seeded above.\n"
            "    director.load_rom = lambda *a, **k: None\n"
            "\n"
            "    return RoundtripScene()\n"
        )
        self.model = model

    def test_real_build_matches_the_model_it_was_generated_from(self):
        parsed = recover.capture_scene_payload(self.SLUG, ROOT)
        mismatches = recover.compare_payload_to_model(self.model, parsed)
        self.assertEqual(mismatches, [], "real MicroPython build disagreed with the model")

    def test_bad_slug_raises_recover_error(self):
        with self.assertRaises(recover.RecoverError):
            recover.capture_scene_payload("no.such.slug.at.all", ROOT)


if __name__ == "__main__":
    unittest.main()
