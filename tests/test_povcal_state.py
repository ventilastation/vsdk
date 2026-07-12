import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

from color_profile import ColorProfile
from povcal_state import PovCalibrationState


class PovCalibrationStateTests(unittest.TestCase):
    def test_waiting_state_has_no_profile(self):
        state = PovCalibrationState()
        self.assertFalse(state.ready)
        self.assertIn("waiting", state.status_text())

    def test_acknowledged_profile_is_authoritative(self):
        state = PovCalibrationState()
        profile = ColorProfile.default(generation=9)
        state.reject("temporary error")
        state.apply(profile)

        self.assertTrue(state.ready)
        self.assertEqual(state.generation, 9)
        self.assertEqual(state.error, None)
        self.assertEqual(state.status_text(), "POV CAL: profile #9")


if __name__ == "__main__":
    unittest.main()
