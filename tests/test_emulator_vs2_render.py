import os
import struct
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

import povrender


def make_vs2_scene(layers, sprites):
    header_size = 16
    layer_size = 8
    sprite_size = 24
    payload = bytearray(header_size + len(layers) * layer_size + len(sprites) * sprite_size)
    payload[0:4] = b"VS2\0"
    payload[4] = 1
    payload[5] = len(layers)
    payload[6] = len(sprites)
    struct.pack_into("<HHH", payload, 8, header_size, layer_size, sprite_size)

    offset = header_size
    for index, layer in enumerate(layers):
        payload[offset] = index
        payload[offset + 1] = layer.get("mode", 1)
        payload[offset + 2] = 0 if layer.get("visible") is False else 1
        offset += layer_size

    for sprite in sprites:
        payload[offset] = sprite.get("layer", 255)
        payload[offset + 1] = sprite["image"]
        payload[offset + 2] = sprite.get("frame", 0)
        payload[offset + 3] = sprite.get("mode", 1)
        payload[offset + 4] = sprite.get("flags", 1)
        struct.pack_into(
            "<ii",
            payload,
            offset + 10,
            int(sprite.get("x", 0) * 256),
            int(sprite.get("y", 0) * 256),
        )
        offset += sprite_size
    return payload


class EmulatorVs2RenderTests(unittest.TestCase):
    def setUp(self):
        povrender.clear_voom_frame()
        povrender.clear_vs2_scene()
        povrender.starfield = []
        povrender.all_strips.clear()
        povrender.upalette = [0] * 256
        povrender.upalette[1] = 10
        povrender.upalette[2] = 20
        povrender.upalette[3] = 30
        povrender.upalette[4] = 40

    def tearDown(self):
        povrender.clear_voom_frame()
        povrender.clear_vs2_scene()

    def test_vs2_hud_flip_x_and_flip_y(self):
        povrender.all_strips[8] = bytes([2, 2, 1, 0, 1, 2, 3, 4])
        povrender.set_vs2_scene(make_vs2_scene([], [
            {"image": 8, "mode": 2, "flags": 1 | 2 | 4, "x": 20, "y": 51},
        ]))

        pixels_column_20 = povrender.render(20)
        pixels_column_21 = povrender.render(21)

        self.assertEqual(pixels_column_20[2], 20)
        self.assertEqual(pixels_column_20[1], 10)
        self.assertEqual(pixels_column_21[2], 40)

    def test_vs2_unlayered_modes_survive_decode(self):
        decoded = povrender.decode_vs2_scene(make_vs2_scene([], [
            {"image": 3, "mode": 0, "flags": 1, "x": 30, "y": 255},
            {"image": 7, "mode": 2, "flags": 1, "x": 42, "y": 0},
        ]))

        self.assertEqual(decoded[0]["perspective"], 0)
        self.assertEqual(decoded[1]["perspective"], 2)

    def test_vs2_signed_fractional_x_wraps_while_y_clips(self):
        povrender.all_strips[8] = bytes([2, 2, 1, 0, 1, 2, 3, 4])
        povrender.set_vs2_scene(make_vs2_scene([], [
            {"image": 8, "mode": 2, "flags": 1, "x": -0.25, "y": -0.25},
        ]))

        pixels_column_0 = povrender.render(0)
        pixels_column_1 = povrender.render(1)
        pixels_column_255 = povrender.render(255)

        self.assertEqual(pixels_column_0[53], 20)
        self.assertEqual(pixels_column_1[53], 0)
        self.assertEqual(pixels_column_255[53], 40)


if __name__ == "__main__":
    unittest.main()
