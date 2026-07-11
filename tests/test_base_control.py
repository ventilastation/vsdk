import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

from base_control import BaseControlState


class BaseControlTests(unittest.TestCase):
    def test_valid_commands_are_canonical_and_update_state(self):
        state = BaseControlState()
        self.assertEqual(state.apply([b"leds", b"1", b"2", b"3"]), "base leds 1 2 3\n")
        self.assertEqual(state.rgb, (1, 2, 3))
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


if __name__ == "__main__":
    unittest.main()
