import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

from color_profile import ColorProfile, ColorProfileError, PAYLOAD_BYTES, Q15_ONE
import povrender


class ColorProfileTests(unittest.TestCase):
    def tearDown(self):
        povrender.set_apa102_profile_payload(ColorProfile.default().to_bytes())

    def test_default_profile_round_trips_exactly(self):
        profile = ColorProfile.default(generation=42)
        payload = profile.to_bytes()

        self.assertEqual(len(payload), PAYLOAD_BYTES)
        decoded = ColorProfile.from_bytes(payload, schema_version=1, generation=42)
        self.assertEqual(decoded.to_bytes(), payload)

    def test_profile_global_response_changes_preview_light(self):
        profile = ColorProfile.default()
        nominal = profile.decode_preview_rgb(0xFF, 0, 0, 255)[0]
        profile.global_response = tuple(Q15_ONE // 4 for _ in range(32))
        profile.global_response = (0,) + profile.global_response[1:]
        dimmed = profile.decode_preview_rgb(0xFF, 0, 0, 255)[0]

        self.assertGreater(dimmed, 0)
        self.assertLess(dimmed, nominal)

    def test_profile_matrix_changes_preview_chromaticity(self):
        profile = ColorProfile.default()
        profile.preview_matrix = (0, 0, 4096, 0, 4096, 0, 4096, 0, 0)
        preview = profile.decode_preview_rgb(0xFF, 0, 0, 255)

        self.assertEqual(preview, (0, 0, 255))

    def test_payload_rejects_command_header_mismatch(self):
        payload = ColorProfile.default(generation=5).to_bytes()
        with self.assertRaises(ColorProfileError):
            ColorProfile.from_bytes(payload, schema_version=1, generation=6)

    def test_pov_renderer_uses_installed_profile(self):
        profile = ColorProfile.default(generation=7)
        profile.global_response = tuple(Q15_ONE // 4 for _ in range(32))
        profile.global_response = (0,) + profile.global_response[1:]
        povrender.set_apa102_profile_payload(profile.to_bytes(), 1, 7)
        frame = bytearray(256 * 54 * 4)
        frame[0:4] = bytes((0xFF, 0, 0, 255))
        povrender.set_voom_frame_apa102(frame)

        red = povrender.render(0)[0] & 0xFF
        self.assertGreater(red, 0)
        self.assertLess(red, 255)


if __name__ == "__main__":
    unittest.main()
