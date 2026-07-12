import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "emulator"))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))

from color_profile import ColorProfile
from ventilastation import color_calibration


class ColorCalibrationTests(unittest.TestCase):
    def setUp(self):
        color_calibration._loaded = False
        color_calibration._profile = None

    def test_micropython_default_matches_emulator_profile(self):
        payload = color_calibration.build_default(generation=12)
        profile = ColorProfile.from_bytes(payload, schema_version=1, generation=12)

        self.assertEqual(profile.to_bytes(), payload)

    def test_povcal_get_sends_canonical_profile_payload(self):
        sent = []

        def send(line, data=b""):
            sent.append((line, data))

        self.assertTrue(color_calibration.handle_command(["get"], send))
        self.assertEqual(len(sent), 1)
        line, payload = sent[0]
        self.assertTrue(line.startswith(b"povcal_state 1 0 "))
        self.assertEqual(ColorProfile.from_bytes(payload).generation, 0)

    def test_unknown_command_is_not_acknowledged(self):
        self.assertFalse(color_calibration.handle_command(["set", "master", "500"], lambda *args: None))


if __name__ == "__main__":
    unittest.main()
