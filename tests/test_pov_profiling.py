import sys
import unittest
from unittest import mock

sys.path.insert(0, "apps/micropython")

from ventilastation import pov_profiling


class FakeDisplay:
    def __init__(self):
        self.enabled = False
        self.calibrated = True
        self.reset_count = 0

    def set_performance_profiling(self, enabled):
        self.enabled = enabled

    def reset_performance_stats(self):
        self.reset_count += 1

    def set_color_pipeline_enabled(self, enabled):
        self.calibrated = enabled

    def get_performance_stats(self):
        return {
            "enabled": self.enabled,
            "calibrated": self.calibrated,
            "vs2": True,
            "layers": 2,
            "sprites": 19,
            "tilemaps": 1,
            "samples": 256,
            "project_samples": 512,
            "frames": 2,
            "deadline_us": 3906,
            "frame_deadline_us": 100000,
            "skipped_updates": 0,
            "deadline_misses": 0,
            "frame_deadline_misses": 0,
            "avg_total_us": 180,
            "max_total_us": 220,
            "avg_render_us": 130,
            "max_render_us": 170,
            "max_arm_render_us": 91,
            "avg_project_us": 130,
            "max_project_us": 170,
            "avg_frame_render_us": 33280,
            "max_frame_render_us": 34000,
            "avg_spi_wait_us": 30,
            "max_spi_wait_us": 40,
            "avg_copy_us": 6,
            "max_copy_us": 8,
            "worst_slack_us": 3686,
        }


class FakeGateScene:
    def __init__(self):
        self.mode = None
        self.started = []
        self.baselines = 0
        self.stopped = 0

    def gate_start(self, mode):
        self.mode = mode
        self.started.append(mode)

    def gate_stop(self):
        self.mode = None
        self.stopped += 1

    def gate_baseline(self):
        self.baselines += 1

    def gate_stats(self):
        return {
            "mode": self.mode or "stopped",
            "passes": 32,
            "sprites": 60,
            "samples": 100,
            "avg_us": 640,
            "max_us": 700,
            "heap_start": 1000,
            "heap_free": 1000,
            "heap_delta": 0,
        }


class PovProfilingTests(unittest.TestCase):
    def command(self, parts, display=None, scene=None):
        sent = []
        pov_profiling.handle_command(
            parts,
            lambda line: sent.append(line),
            display or FakeDisplay(),
            scene=scene,
        )
        return sent

    def test_start_resets_and_reports_vs2_timing(self):
        display = FakeDisplay()
        sent = self.command(["start"], display)
        self.assertTrue(display.enabled)
        self.assertEqual(display.reset_count, 1)
        self.assertIn(b"scene=vs2", sent[0])
        self.assertIn(b"complete=1", sent[0])
        self.assertIn(b"max_arm_render_us=91", sent[1])
        self.assertIn(b"frames=2", sent[1])
        self.assertIn(b"max_frame_render_us=34000", sent[1])

    def test_mode_switch_resets_without_persisting_profile(self):
        display = FakeDisplay()
        self.command(["mode", "legacy"], display)
        self.assertFalse(display.calibrated)
        self.assertEqual(display.reset_count, 1)

    def test_heap_baseline_and_stop_sample_use_the_same_allocation_point(self):
        display = FakeDisplay()
        sent = []
        with mock.patch.object(
            pov_profiling, "_heap_free", side_effect=[1000, 1000, 1000]
        ):
            pov_profiling.handle_command(["start"], sent.append, display)
            pov_profiling.handle_command(["stop"], sent.append, display)
        state_lines = [line for line in sent if line.startswith(b"povperf_state ")]
        self.assertEqual(len(state_lines), 2)
        # The start response is a warm-up and precedes the baseline.
        self.assertIn(b"heap_delta=", state_lines[0])
        self.assertIn(b"heap_delta=0", state_lines[1])

    def test_invalid_command_is_reported(self):
        sent = self.command(["mode", "fast"])
        self.assertEqual(sent, [b"povperf_error invalid_command"])

    def test_capture_prepares_an_opt_in_scene(self):
        scene = mock.Mock()
        sent = self.command(["capture"], scene=scene)
        scene.prepare_capture.assert_called_once_with()
        self.assertEqual(sent, [b"povperf_capture ready=1"])

    def test_capture_rejects_a_scene_without_fixture_hook(self):
        sent = self.command(["capture"], scene=object())
        self.assertEqual(sent, [b"povperf_error invalid_command"])

    def test_gate_controls_an_opt_in_scene(self):
        scene = FakeGateScene()
        sent = self.command(["gate", "start", "column"], scene=scene)
        self.assertEqual(scene.started, ["column"])
        self.assertIn(b"povperf_gate mode=column", sent[0])
        sent = self.command(["gate", "stop"], scene=scene)
        self.assertEqual(scene.stopped, 1)
        self.assertIn(b"povperf_gate mode=stopped", sent[0])
        self.command(["gate", "baseline"], scene=scene)
        self.assertEqual(scene.baselines, 1)

    def test_gate_rejects_missing_or_invalid_fixture(self):
        self.assertEqual(
            self.command(["gate", "status"], scene=object()),
            [b"povperf_error invalid_command"],
        )
        scene = FakeGateScene()
        self.assertEqual(
            self.command(["gate", "start"], scene=scene),
            [b"povperf_error invalid_command"],
        )


if __name__ == "__main__":
    unittest.main()
