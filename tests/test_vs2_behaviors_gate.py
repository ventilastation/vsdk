import sys
import unittest


sys.path.insert(0, "tools")

import vs2_behaviors_gate as gate


class GateFieldTests(unittest.TestCase):
    def test_keeps_a_profile_line_after_a_forwarded_preamble(self):
        events = [
            ("line", "launcher noisepovperf_gate mode=column avg_us=123"),
        ]
        self.assertEqual(
            gate._field(events, "povperf_gate "),
            {"mode": "column", "avg_us": "123"},
        )

    def test_allows_bounded_uart_report_overhead(self):
        rows = [
            {"mode": "inline", "avg_us": 100, "samples": 101, "heap_delta": -80,
             "overruns": 0, "frame_overruns": 0, "worst_slack_us": 1},
            {"mode": "column", "avg_us": 105, "samples": 101, "heap_delta": -80,
             "overruns": 0, "frame_overruns": 0, "worst_slack_us": 1},
            {"mode": "per_sprite", "avg_us": 110, "samples": 101, "heap_delta": -80,
             "overruns": 0, "frame_overruns": 0, "worst_slack_us": 1},
            {"mode": "hybrid", "avg_us": 115, "samples": 101, "heap_delta": -80,
             "overruns": 0, "frame_overruns": 0, "worst_slack_us": 1},
        ]
        self.assertEqual(gate._failures(rows), [])


if __name__ == "__main__":
    unittest.main()
