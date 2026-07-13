import unittest
from unittest import mock


import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

from povperf_controls import start_capture, stop_capture


class PovPerformanceControlTests(unittest.TestCase):
    def test_start_legacy_selects_encoder_then_starts_a_fresh_capture(self):
        send_command = mock.Mock()
        start_capture("legacy", send_command)

        self.assertEqual(send_command.call_args_list, [
            mock.call("povperf mode legacy"),
            mock.call("povperf start"),
        ])

    def test_start_calibrated_selects_encoder_then_starts_a_fresh_capture(self):
        send_command = mock.Mock()
        start_capture("calibrated", send_command)

        self.assertEqual(send_command.call_args_list, [
            mock.call("povperf mode calibrated"),
            mock.call("povperf start"),
        ])

    def test_stop_requests_the_board_final_report(self):
        send_command = mock.Mock()
        stop_capture(send_command)

        send_command.assert_called_once_with("povperf stop")

    def test_unknown_encoder_is_not_sent(self):
        send_command = mock.Mock()
        with self.assertRaises(ValueError):
            start_capture("invalid", send_command)

        send_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
