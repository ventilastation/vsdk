import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

from base_control import BaseControlState, DIAL_MINIMUM, gamma_correct


class BaseControlTests(unittest.TestCase):
    def test_valid_commands_are_canonical_and_update_state(self):
        state = BaseControlState()
        self.assertEqual(state.apply([b"leds", b"1", b"2", b"3"]), "base leds 1 2 3\n")
        self.assertEqual(state.rgb, (1, 2, 3))
        self.assertEqual(state.led_rgb, tuple(gamma_correct(value) for value in (1, 2, 3)))
        self.assertEqual(state.apply([b"servo", b"255"]), "base servo 255\n")
        self.assertEqual(state.servo_position, 255)
        self.assertEqual(state.apply([b"buttons", b"3", b"20"]), "base buttons 3 100\n")
        self.assertTrue(state.button_lit(1, 0))
        self.assertFalse(state.button_lit(1, 60))

    def test_invalid_commands_do_not_change_state(self):
        state = BaseControlState()
        self.assertIsNone(state.apply([b"servo", b"256"]))
        self.assertIsNone(state.apply([b"leds", b"-1", b"0", b"0"]))
        self.assertIsNone(state.apply([b"buttons", b"4", b"0"]))
        self.assertEqual((state.rgb, state.servo_position, state.button_mask), ((0, 0, 0), 0, 0))

    def test_gamma_curve_is_dark_at_midpoint_and_exact_at_endpoints(self):
        self.assertEqual(gamma_correct(0), 0)
        self.assertEqual(gamma_correct(255), 255)
        self.assertEqual(gamma_correct(128), 56)

    def test_dial_floor_keeps_black_commands_visible(self):
        state = BaseControlState()
        self.assertEqual(state.dial_rgb, (DIAL_MINIMUM,) * 3)
        state.apply([b"leds", b"255", b"0", b"0"])
        self.assertEqual(state.dial_rgb, (255, DIAL_MINIMUM, DIAL_MINIMUM))


if __name__ == "__main__":
    unittest.main()
