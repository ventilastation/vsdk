import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

from color_profile import (
    ColorProfile, ColorProfileError, PAYLOAD_BYTES, Q15_ONE, VERSION,
)
import povrender


class ColorProfileTests(unittest.TestCase):
    def tearDown(self):
        povrender.set_apa102_profile_payload(ColorProfile.default().to_bytes())

    def test_default_profile_round_trips_exactly(self):
        profile = ColorProfile.default(generation=42)
        payload = profile.to_bytes()

        self.assertEqual(len(payload), PAYLOAD_BYTES)
        decoded = ColorProfile.from_bytes(payload, schema_version=VERSION, generation=42)
        self.assertEqual(decoded.to_bytes(), payload)

    def test_profile_global_response_changes_preview_light(self):
        profile = ColorProfile.default()
        nominal = profile.decode_preview_rgb(0xFF, 0, 0, 255)[0]
        profile.global_response = tuple(Q15_ONE // 4 for _ in range(32))
        profile.global_response = (0,) + profile.global_response[1:]
        dimmed = profile.decode_preview_rgb(0xFF, 0, 0, 255)[0]

        self.assertGreater(dimmed, 0)
        self.assertLess(dimmed, nominal)

    def test_dark_white_leaves_the_ceiling_alone(self):
        # The ordinary white balance already holds where no global-brightness
        # modulation is in play, so trimming a channel there would double-
        # correct tones that already look right.
        profile = ColorProfile.default()
        nominal = profile.decode_preview_rgb(0xE0 | profile.gb_ceiling, 200, 200, 200)
        profile.dark_white = (1000, 960, 1000)

        self.assertEqual(
            profile.decode_preview_rgb(0xE0 | profile.gb_ceiling, 200, 200, 200),
            nominal,
        )

    def test_dark_white_retints_globally_modulated_levels(self):
        profile = ColorProfile.default()
        level = 0xE0 | 4  # well below the ceiling, so the trim is at full weight
        nominal = profile.decode_preview_rgb(level, 200, 200, 200)
        profile.dark_white = (1000, 960, 1000)
        trimmed = profile.decode_preview_rgb(level, 200, 200, 200)

        # The decoder models the light a fixed drive produces, so declaring
        # green dimmer per PWM count means more light for the same count. The
        # encoder inverts this, which is what neutralizes the rendered grey.
        self.assertGreater(trimmed[1], nominal[1])
        self.assertEqual((trimmed[0], trimmed[2]), (nominal[0], nominal[2]))

    def test_dark_white_survives_a_round_trip(self):
        profile = ColorProfile.default()
        profile.dark_white = (1010, 955, 1000)
        decoded = ColorProfile.from_bytes(profile.to_bytes())

        self.assertEqual(decoded.dark_white, (1010, 955, 1000))

    def test_dark_white_outside_its_range_is_rejected(self):
        profile = ColorProfile.default()
        profile.dark_white = (1000, 0, 1000)
        with self.assertRaises(ColorProfileError):
            profile.to_bytes()

    def test_profile_matrix_changes_preview_chromaticity(self):
        profile = ColorProfile.default()
        profile.preview_matrix = (0, 0, 4096, 0, 4096, 0, 4096, 0, 0)
        preview = profile.decode_preview_rgb(0xFF, 0, 0, 255)

        self.assertEqual(preview, (0, 0, 255))

    def test_payload_rejects_command_header_mismatch(self):
        payload = ColorProfile.default(generation=5).to_bytes()
        with self.assertRaises(ColorProfileError):
            ColorProfile.from_bytes(payload, schema_version=VERSION, generation=6)

    def test_pov_renderer_uses_installed_profile(self):
        profile = ColorProfile.default(generation=7)
        profile.global_response = tuple(Q15_ONE // 4 for _ in range(32))
        profile.global_response = (0,) + profile.global_response[1:]
        povrender.set_apa102_profile_payload(profile.to_bytes(), VERSION, 7)
        frame = bytearray(256 * 54 * 4)
        frame[0:4] = bytes((0xFF, 0, 0, 255))
        povrender.set_voom_frame_apa102(frame)

        red = povrender.render(0)[0] & 0xFF
        self.assertGreater(red, 0)
        self.assertLess(red, 255)


if __name__ == "__main__":
    unittest.main()
