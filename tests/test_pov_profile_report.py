import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pov_profile_report as report  # noqa: E402


class FakeSerial:
    """Feeds canned bytes to WireReader like a real board would, in chunks,
    so the "payload not fully arrived yet" wait path gets exercised too."""

    def __init__(self, chunks):
        self._chunks = list(chunks)

    def read(self, _n):
        if self._chunks:
            return self._chunks.pop(0)
        return b""


class ParseKvLineTests(unittest.TestCase):
    def test_extracts_fields(self):
        fields = report.parse_kv_line(
            "povperf_timing samples=100 deadline_us=390 skipped=2", "povperf_timing ")
        self.assertEqual(fields, {"samples": "100", "deadline_us": "390", "skipped": "2"})

    def test_wrong_prefix_returns_none(self):
        self.assertIsNone(report.parse_kv_line("povperf_state foo=1", "povperf_timing "))


class ToIntTests(unittest.TestCase):
    def test_present_key(self):
        self.assertEqual(report.to_int({"samples": "42"}, "samples"), 42)

    def test_missing_key_uses_default(self):
        self.assertEqual(report.to_int({}, "samples", 7), 7)

    def test_non_numeric_uses_default(self):
        self.assertEqual(report.to_int({"samples": "nan"}, "samples", 0), 0)


class BuildReportRowTests(unittest.TestCase):
    def test_failed_run_when_no_response(self):
        row = report.build_report_row(600, "prboom", "native.voom", None, None)
        self.assertFalse(row["ok"])

    def test_computes_overrun_and_skip_percent(self):
        state = {"encoder": "calibrated"}
        timing = {"samples": "100", "overruns": "5", "skipped": "5", "deadline_us": "390"}
        row = report.build_report_row(600, "prboom", "native.voom", state, timing)
        self.assertTrue(row["ok"])
        self.assertAlmostEqual(row["overrun_pct"], 5.0)
        # 5 skipped out of (100 samples + 5 skipped) columns actually swept.
        self.assertAlmostEqual(row["skip_pct"], 100.0 * 5 / 105)

    def test_normalizes_micropython_field_names(self):
        # MicroPython's profiler calls these avg_render_us/avg_spi_wait_us;
        # retro-go's calls them avg_project_us/avg_spi_us. Both must land in
        # the same normalized fields.
        timing = {
            "samples": "10", "overruns": "0", "skipped": "0", "deadline_us": "390",
            "avg_render_us": "150", "avg_spi_wait_us": "20",
        }
        row = report.build_report_row(600, "vixious", "alecu.vixeous", {"encoder": "calibrated"}, timing)
        self.assertEqual(row["avg_render_us"], 150)
        self.assertEqual(row["avg_spi_us"], 20)

    def test_normalizes_retro_go_field_names(self):
        timing = {
            "samples": "10", "overruns": "0", "skipped": "0", "deadline_us": "390",
            "avg_project_us": "160", "avg_spi_us": "5",
        }
        row = report.build_report_row(600, "prboom", "native.voom", {"encoder": "calibrated"}, timing)
        self.assertEqual(row["avg_render_us"], 160)
        self.assertEqual(row["avg_spi_us"], 5)


class WireReaderTests(unittest.TestCase):
    def test_plain_lines_pass_through(self):
        ser = FakeSerial([b"povperf_timing samples=5\n", b"", b""])
        reader = report.WireReader(ser)
        events = reader.read_for(0.05)
        self.assertIn(("line", "povperf_timing samples=5"), events)

    def test_unwraps_info_frame(self):
        payload = "director: launch failed: alecu.vixeous"
        data = payload.encode("utf-8")
        ser = FakeSerial([("info %d\n" % len(data)).encode("ascii") + data, b""])
        reader = report.WireReader(ser)
        events = reader.read_for(0.05)
        self.assertIn(("info", payload), events)

    def test_info_frame_split_across_reads(self):
        payload = b"hello world"
        header = b"info %d\n" % len(payload)
        # Split the payload itself mid-frame to exercise the "wait for the
        # rest of the payload" path in read_for().
        ser = FakeSerial([header + payload[:4], payload[4:], b""])
        reader = report.WireReader(ser)
        events = reader.read_for(0.5)
        self.assertIn(("info", "hello world"), events)

    def test_ignores_workbench_log_noise_between_lines(self):
        ser = FakeSerial([
            b"I (123) led_capture: bursts/s: good=2560\n"
            b"povperf_state enabled=1 encoder=calibrated scene=voom complete=0\n",
            b"",
        ])
        reader = report.WireReader(ser)
        events = reader.read_for(0.05)
        lines = [text for kind, text in events if kind == "line"]
        self.assertIn("povperf_state enabled=1 encoder=calibrated scene=voom complete=0", lines)


if __name__ == "__main__":
    unittest.main()
