import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

import vs2_hardware_report as report  # noqa: E402


def solid_frame(gb=0xFF, blue=0, green=0, red=0xFF):
    return bytes((gb, blue, green, red)) * (256 * 54)


class RunDirectoryTests(unittest.TestCase):
    def test_uses_timestamp_name_and_collision_suffix(self):
        now = datetime(2026, 7, 28, 14, 3, 4, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            first = report.create_run_directory(tmp, "Bench run", now=now)
            second = report.create_run_directory(tmp, "Bench run", now=now)
            self.assertEqual(first.name, "20260728-140304-Bench-run")
            self.assertEqual(second.name, "20260728-140304-Bench-run-02")
            self.assertTrue((first / "screenshots").is_dir())


class ScreenshotTests(unittest.TestCase):
    def test_writes_polar_and_parity_png_evidence(self):
        from PIL import Image

        captured = solid_frame()
        expected = bytearray(captured)
        expected[4:8] = bytes((0xFF, 0xFF, 0, 0))
        metrics = {"shift": 0}
        with tempfile.TemporaryDirectory() as tmp:
            frame_path = Path(tmp) / "frame.png"
            parity_path = Path(tmp) / "parity.png"
            report.save_frame_screenshot(captured, frame_path, size=96)
            report.save_parity_screenshot(
                captured, bytes(expected), metrics, parity_path, panel_size=64
            )
            with Image.open(frame_path) as image:
                self.assertEqual(image.size, (96, 96))
            with Image.open(parity_path) as image:
                width, height = image.size
            self.assertGreater(width, height)
            self.assertGreater(height, 64)


class HtmlReportTests(unittest.TestCase):
    def sample_results(self):
        return {
            "started_at": "2026-07-28T14:03:04-03:00",
            "finished_at": "2026-07-28T14:05:00-03:00",
            "status": "pass",
            "port": "/dev/cu.workbench",
            "rpms": [600],
            "repeats": 1,
            "max_skip_pct": 0.05,
            "config": {
                "duration": 5.0,
                "min_exact": 0.99,
                "min_active_exact": 0.99,
            },
            "git": {"branch": "impl/vs2-api-rework", "commit": "a" * 40, "dirty": True},
            "performance": [
                {
                    "ok": True,
                    "rpm": 600,
                    "repetition": 1,
                    "game": "vs2max",
                    "max_frame_render_us": 42000,
                    "frame_deadline_us": 100000,
                    "worst_slack_us": 100,
                    "skipped": 0,
                    "skip_pct": 0.0,
                    "heap_delta": 200,
                    "layers": 8,
                    "sprites": 100,
                    "tilemaps": 16,
                    "samples": 12000,
                    "frames": 50,
                    "screenshot": "screenshots/performance.png",
                    "failures": [],
                }
            ],
            "render_warmups": [],
            "rendering": [
                {
                    "rpm": 400,
                    "repetition": 1,
                    "shift": 0,
                    "exact_ratio": 0.997,
                    "active_exact_ratio": 1.0,
                    "different_pixels": 40,
                    "compared_pixels": 13568,
                    "screenshot": "screenshots/parity.png",
                    "failures": [],
                }
            ],
            "failures": [],
        }

    def test_writes_linked_html_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path, json_path = report.write_report(tmp, self.sample_results())
            document = html_path.read_text()
            data = json.loads(json_path.read_text())
            self.assertIn("Hardware acceptance report", document)
            self.assertIn("Ventilastation", document)
            self.assertNotIn("VentilaStation", document)
            self.assertIn("PASS", document)
            self.assertIn("screenshots/performance.png", document)
            self.assertIn("screenshots/parity.png", document)
            self.assertEqual(data["artifacts"]["html"], "report.html")


if __name__ == "__main__":
    unittest.main()
