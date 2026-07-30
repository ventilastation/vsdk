import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

import vs2_hardware_test as hardware  # noqa: E402
import native_render  # noqa: E402


class PixelParityTests(unittest.TestCase):
    def frame(self):
        values = np.arange(
            hardware.FRAME_COLUMNS * hardware.FRAME_LEDS * hardware.APA102_BYTES,
            dtype=np.uint32,
        )
        return (values % 251).astype(np.uint8).tobytes()

    def test_finds_circular_column_offset(self):
        expected = self.frame()
        array = np.frombuffer(expected, dtype=np.uint8).reshape(
            hardware.FRAME_COLUMNS,
            hardware.FRAME_LEDS,
            hardware.APA102_BYTES,
        )
        captured = np.roll(array, 37, axis=0).tobytes()
        metrics = hardware.best_circular_match(captured, expected)
        self.assertEqual(metrics["shift"], 37)
        self.assertEqual(metrics["exact_ratio"], 1.0)
        self.assertEqual(metrics["active_exact_ratio"], 1.0)

    def test_ignores_only_shared_center_led(self):
        expected = self.frame()
        captured = bytearray(expected)
        for column in range(hardware.FRAME_COLUMNS):
            offset = column * hardware.FRAME_LEDS * hardware.APA102_BYTES
            captured[offset:offset + hardware.APA102_BYTES] = b"\xff\xff\xff\xff"
        metrics = hardware.best_circular_match(bytes(captured), expected)
        self.assertEqual(metrics["exact_ratio"], 1.0)

    def test_detects_non_center_pixel_regression(self):
        expected = self.frame()
        captured = bytearray(expected)
        captured[hardware.APA102_BYTES] ^= 0x01
        metrics = hardware.best_circular_match(bytes(captured), expected)
        self.assertGreater(metrics["different_pixels"], 0)
        self.assertLess(metrics["exact_ratio"], 1.0)


class PerformanceGateTests(unittest.TestCase):
    def good_row(self):
        return {
            "ok": True,
            "complete": 1,
            "layers": 8,
            "sprites": 100,
            "tilemaps": 16,
            "samples": 1000,
            "frames": 20,
            "skipped": 0,
            "overruns": 0,
            "frame_overruns": 0,
            "worst_slack_us": 300,
            "frame_deadline_us": 100000,
            "max_frame_render_us": 30000,
            "heap_delta": 0,
        }

    def test_accepts_complete_stable_run(self):
        row = self.good_row()
        expected = {"layers": 8, "sprites": 100, "tilemaps": 16}
        self.assertEqual(hardware.performance_failures(row, expected), [])

    def test_rejects_deadline_heap_skip_rate_and_budget_regressions(self):
        row = self.good_row()
        row.update(
            {
                "sprites": 99,
                "skipped": 2,
                "skip_pct": 0.2,
                "frame_overruns": 1,
                "max_frame_render_us": 110000,
                "heap_delta": -64,
            }
        )
        expected = {"layers": 8, "sprites": 100, "tilemaps": 16}
        failures = "\n".join(hardware.performance_failures(row, expected))
        self.assertIn("sprites=99", failures)
        self.assertIn("skipped", failures)
        self.assertIn("full-frame deadline", failures)
        self.assertIn("revolution budget", failures)
        self.assertIn("heap growth", failures)

    def test_accepts_measured_sub_threshold_column_jitter(self):
        row = self.good_row()
        row.update({"skipped": 3, "skip_pct": 0.0188})
        expected = {"layers": 8, "sprites": 100, "tilemaps": 16}
        self.assertEqual(hardware.performance_failures(row, expected), [])


class SceneReadinessTests(unittest.TestCase):
    class Reader:
        def __init__(self, batches):
            self.batches = list(batches)

        def read_for(self, _duration):
            return self.batches.pop(0) if self.batches else []

    def setUp(self):
        self.scene = {
            "label": "vs2max",
            "slug": "vs2_hardware",
            "layers": 8,
            "sprites": 100,
            "tilemaps": 16,
        }

    def test_retries_a_launch_that_fell_back_to_the_menu(self):
        reader = self.Reader([
            [],
            [("line", "povperf_state layers=0 sprites=0 tilemaps=0")],
            [],
            [("line", "povperf_state layers=8 sprites=100 tilemaps=16")],
        ])
        serial = mock.Mock()
        with mock.patch.object(hardware.profile, "wiggle"), \
                mock.patch.object(hardware.time, "sleep"):
            state = hardware.ensure_scene_ready(
                serial, reader, self.scene, settle=0, status_timeout=0
            )
        self.assertEqual(state["sprites"], "100")
        writes = b"".join(call.args[0] for call in serial.write.call_args_list)
        self.assertIn(b"launch vs2_hardware\n", writes)

    def test_rejects_a_scene_with_the_wrong_renderer_census(self):
        reader = self.Reader([
            [],
            [("line", "povperf_state layers=0 sprites=0 tilemaps=0")],
        ])
        with self.assertRaisesRegex(RuntimeError, "did not become ready"):
            hardware.ensure_scene_ready(
                mock.Mock(),
                reader,
                self.scene,
                settle=0,
                status_timeout=0,
                launch_attempts=1,
            )


class ReportPersistenceTests(unittest.TestCase):
    def test_auto_detection_failure_still_writes_timestamped_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                report_root=tmp,
                report_name="failure-case",
                port=None,
                rpms=[600, 700],
                repeats=3,
                max_skip_pct=0.05,
                baud=115200,
                settle=2.0,
                duration=5.0,
                render_rpm=400,
                capture_warmups=1,
                capture_repeats=3,
                capture_settle=2.0,
                capture_timeout=8.0,
                min_exact=0.99,
                min_active_exact=0.99,
                skip_performance=True,
                skip_render=True,
                json_out=None,
            )
            with mock.patch.object(
                hardware.profile,
                "find_workbench_port",
                side_effect=SystemExit("no workbench found"),
            ):
                self.assertEqual(hardware.run_hardware(args), 1)

            report_dirs = list(Path(tmp).iterdir())
            self.assertEqual(len(report_dirs), 1)
            payload = json.loads(
                (report_dirs[0] / "results.json").read_text()
            )
            self.assertEqual(payload["status"], "fail")
            self.assertIn("SystemExit: no workbench found", payload["failures"][0])
            self.assertTrue((report_dirs[0] / "report.html").is_file())
            self.assertTrue((report_dirs[0] / "screenshots").is_dir())


class NativeOracleLifetimeTests(unittest.TestCase):
    def test_retains_the_exact_image_bytes_borrowed_by_c(self):
        fake_lib = mock.Mock()
        fake_lib.emu_gpu_set_image_strip.return_value = True
        source = memoryview(bytearray(b"\x02\x03\x01\x00pixels"))
        with mock.patch.object(native_render, "available", True), \
                mock.patch.object(native_render, "_lib", fake_lib):
            native_render.set_image_strip(7, source)
            retained = native_render._image_strip_bytes[7]
            self.assertIsInstance(retained, bytes)
            self.assertEqual(retained, bytes(source))
            self.assertIs(fake_lib.emu_gpu_set_image_strip.call_args.args[1], retained)
            native_render.clear_image_strip(7)
            self.assertNotIn(7, native_render._image_strip_bytes)


if __name__ == "__main__":
    unittest.main()
