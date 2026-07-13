import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

from apa102 import decode_preview_rgb
import povrender


class Apa102PreviewTests(unittest.TestCase):
    def tearDown(self):
        povrender.clear_voom_frame()

    def test_full_global_brightness_preserves_full_primary(self):
        self.assertEqual(decode_preview_rgb(0xFF, 0, 0, 255), (255, 0, 0))
        self.assertEqual(decode_preview_rgb(0xFF, 0, 255, 0), (0, 255, 0))
        self.assertEqual(decode_preview_rgb(0xFF, 255, 0, 0), (0, 0, 255))

    def test_global_brightness_contributes_to_preview_light(self):
        full = decode_preview_rgb(0xFF, 0, 0, 255)[0]
        dim = decode_preview_rgb(0xE1, 0, 0, 255)[0]
        self.assertGreater(dim, 0)
        self.assertLess(dim, full)

    def test_invalid_or_zero_global_brightness_is_black(self):
        self.assertEqual(decode_preview_rgb(0x00, 255, 255, 255), (0, 0, 0))
        self.assertEqual(decode_preview_rgb(0xE0, 255, 255, 255), (0, 0, 0))

    def test_raw_apa102_frame_is_rendered_without_losing_global_brightness(self):
        frame = bytearray(256 * 54 * 4)
        column = 7
        led = 3
        offset = (column * 54 + led) * 4
        frame[offset:offset + 4] = bytes((0xFF, 0, 0, 255))

        povrender.set_voom_frame_apa102(frame)

        self.assertEqual(povrender.render(column)[led], 0xFF0000FF)
        self.assertEqual(povrender.render(column)[led + 1], 0xFF000000)

    def test_raw_frame_length_is_validated(self):
        with self.assertRaises(ValueError):
            povrender.set_voom_frame_apa102(b"short")


if __name__ == "__main__":
    unittest.main()
