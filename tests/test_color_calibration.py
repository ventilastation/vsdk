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
        sent = []
        self.assertTrue(color_calibration.handle_command(
            ["set", "not_a_setting", "500"], lambda *args: sent.append(args)))
        self.assertTrue(sent[0][0].startswith(b"povcal_error"))

    def test_set_applies_profile_then_returns_the_new_generation(self):
        sent = []

        class Display:
            def __init__(self):
                self.applied = []

            def set_color_profile(self, payload):
                self.applied.append(payload)

        display = Display()
        self.assertTrue(color_calibration.handle_command(
            ["set", "master", "700"],
            lambda *args: sent.append(args),
            display,
        ))
        self.assertEqual(len(display.applied), 1)
        profile = ColorProfile.from_bytes(sent[0][1])
        self.assertEqual(profile.master_milli, 700)
        self.assertEqual(profile.generation, 1)

    def test_commit_writes_the_active_profile(self):
        saved = []
        original_write = color_calibration._write_nvs
        color_calibration._write_nvs = lambda payload: saved.append(payload) or True
        try:
            sent = []
            self.assertTrue(color_calibration.handle_command(
                ["commit"], lambda *args: sent.append(args)))
        finally:
            color_calibration._write_nvs = original_write
        self.assertEqual(saved, [color_calibration.active_profile()])
        self.assertTrue(sent[0][0].startswith(b"povcal_state"))

    def test_test_pattern_is_ram_only(self):
        sent = []

        class Display:
            def __init__(self):
                self.pattern = None

            def set_color_test_pattern(self, pattern, level):
                self.pattern = (pattern, level)

        display = Display()
        profile_before = color_calibration.active_profile()
        self.assertTrue(color_calibration.handle_command(
            ["test", "radial", "200"], lambda *args: sent.append(args), display))
        self.assertEqual(display.pattern, (6, 200))
        self.assertEqual(color_calibration.active_profile(), profile_before)
        self.assertTrue(sent[0][0].startswith(b"povcal_state"))


if __name__ == "__main__":
    unittest.main()
