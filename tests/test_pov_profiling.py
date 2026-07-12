import sys
import unittest

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
            "deadline_us": 3906,
            "skipped_updates": 0,
            "deadline_misses": 0,
            "avg_total_us": 180,
            "max_total_us": 220,
            "avg_render_us": 130,
            "max_render_us": 170,
            "max_arm_render_us": 91,
            "avg_spi_wait_us": 30,
            "max_spi_wait_us": 40,
            "avg_copy_us": 6,
            "max_copy_us": 8,
            "worst_slack_us": 3686,
        }


class PovProfilingTests(unittest.TestCase):
    def command(self, parts, display=None):
        sent = []
        pov_profiling.handle_command(parts, lambda line: sent.append(line), display or FakeDisplay())
        return sent

    def test_start_resets_and_reports_vs2_timing(self):
        display = FakeDisplay()
        sent = self.command(["start"], display)
        self.assertTrue(display.enabled)
        self.assertEqual(display.reset_count, 1)
        self.assertIn(b"scene=vs2", sent[0])
        self.assertIn(b"complete=1", sent[0])
        self.assertIn(b"max_arm_render_us=91", sent[1])

    def test_mode_switch_resets_without_persisting_profile(self):
        display = FakeDisplay()
        self.command(["mode", "legacy"], display)
        self.assertFalse(display.calibrated)
        self.assertEqual(display.reset_count, 1)

    def test_invalid_command_is_reported(self):
        sent = self.command(["mode", "fast"])
        self.assertEqual(sent, [b"povperf_error invalid_command"])


if __name__ == "__main__":
    unittest.main()
