import os
import struct
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

import povrender


def make_vs2_scene(layers, sprites, tilemaps=()):
    header_size = 16
    layer_size = 8
    sprite_size = 24
    tilemap_size = 32 if tilemaps else 0
    frames_bytes = sum(len(tilemap["frames"]) for tilemap in tilemaps)
    payload = bytearray(
        header_size
        + len(layers) * layer_size
        + len(sprites) * sprite_size
        + len(tilemaps) * 32
        + frames_bytes
    )
    payload[0:4] = b"VS2\0"
    payload[4] = 2 if tilemaps else 1
    payload[5] = len(layers)
    payload[6] = len(sprites)
    payload[7] = len(tilemaps)
    struct.pack_into("<HHHH", payload, 8, header_size, layer_size, sprite_size, tilemap_size)

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

    frames_offset = offset + len(tilemaps) * 32
    for tilemap in tilemaps:
        frames = tilemap["frames"]
        struct.pack_into(
            "<BBBBHHHHHHHHiiI",
            payload,
            offset,
            tilemap.get("layer", 255),
            tilemap["image"],
            tilemap.get("flags", 1),
            tilemap.get("mode", 1),
            tilemap["columns"],
            tilemap["rows"],
            tilemap["tile_width"],
            tilemap["tile_height"],
            *tilemap["viewport"],
            int(tilemap.get("x", 0) * 256),
            int(tilemap.get("y", 0) * 256),
            frames_offset,
        )
        offset += 32
        payload[frames_offset:frames_offset + len(frames)] = frames
        frames_offset += len(frames)
    return payload


def make_tile_strip():
    """4x4 tileset with 3 frames, stored column-mirrored like real strips.

    Frame 0: screen column 0 of the tile is palette index 1, the rest 2
    (asymmetric, catches mirroring bugs). Frame 1: solid 3. Frame 2: solid 4
    with the tile's screen pixel (0, 0) transparent.
    """
    frame0 = bytearray(16)
    for dx in range(4):
        for dy in range(4):
            frame0[(3 - dx) * 4 + dy] = 1 if dx == 0 else 2
    frame1 = bytearray([3] * 16)
    frame2 = bytearray([4] * 16)
    frame2[(3 - 0) * 4 + 0] = 255
    return bytes(bytearray([4, 4, 3, 0]) + frame0 + frame1 + frame2)


# 2x2 map: top row = frame 0 | frame 1, bottom row = frame 2 | empty cell
TILEMAP_FRAMES = bytes([0, 1, 2, 255])


def default_tilemap(**overrides):
    tilemap = {
        "image": 9,
        "frames": TILEMAP_FRAMES,
        "columns": 2,
        "rows": 2,
        "tile_width": 4,
        "tile_height": 4,
        "viewport": (0, 0, 8, 8),
        "mode": 2,
        "x": 10,
        "y": 40,
    }
    tilemap.update(overrides)
    return tilemap


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

        self.assertEqual(decoded["sprites"][0]["perspective"], 0)
        self.assertEqual(decoded["sprites"][1]["perspective"], 2)
        self.assertEqual(decoded["tilemaps"], [])

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

    def test_vs2_tilemap_renders_cells_unmirrored_with_empty_and_transparent(self):
        # HUD mode at y=40: dest rows 40..47 land on leds 13..6.
        povrender.all_strips[9] = make_tile_strip()
        povrender.set_vs2_scene(make_vs2_scene([], [], [default_tilemap()]))

        pixels_column_10 = povrender.render(10)
        # top-left tile is frame 0: screen column 0 shows index 1 -> color 10
        self.assertEqual([pixels_column_10[13 - n] for n in range(4)], [10, 10, 10, 10])
        # bottom-left tile is frame 2: pixel (0, 0) transparent, rest 40
        self.assertEqual([pixels_column_10[9 - n] for n in range(4)], [0, 40, 40, 40])

        pixels_column_11 = povrender.render(11)
        # tile screen column 1 of frame 0 shows index 2 -> 20 (mirroring check)
        self.assertEqual(pixels_column_11[13], 20)
        self.assertEqual(pixels_column_11[9], 40)

        pixels_column_14 = povrender.render(14)
        # second map column: top tile frame 1 -> 30, bottom cell 255 is empty
        self.assertEqual([pixels_column_14[13 - n] for n in range(4)], [30, 30, 30, 30])
        self.assertEqual([pixels_column_14[9 - n] for n in range(4)], [0, 0, 0, 0])

        pixels_column_18 = povrender.render(18)
        self.assertEqual(pixels_column_18, [0] * povrender.led_count)

    def test_vs2_tilemap_viewport_pans_horizontally(self):
        povrender.all_strips[9] = make_tile_strip()
        povrender.set_vs2_scene(make_vs2_scene([], [], [
            default_tilemap(viewport=(4, 0, 4, 8)),
        ]))

        # panning the viewport shows the second map column at the origin
        pixels_column_10 = povrender.render(10)
        self.assertEqual(pixels_column_10[13], 30)
        # and the window is only 4 pixels wide now
        pixels_column_14 = povrender.render(14)
        self.assertEqual(pixels_column_14, [0] * povrender.led_count)

    def test_vs2_tilemap_viewport_pans_vertically(self):
        povrender.all_strips[9] = make_tile_strip()
        povrender.set_vs2_scene(make_vs2_scene([], [], [
            default_tilemap(viewport=(0, 2, 8, 4)),
        ]))

        pixels_column_10 = povrender.render(10)
        # dest rows 40..41 show map rows 2..3 (frame 0), 42..43 show rows 4..5
        self.assertEqual(pixels_column_10[13], 10)
        self.assertEqual(pixels_column_10[12], 10)
        self.assertEqual(pixels_column_10[11], 0)   # frame 2 transparent pixel
        self.assertEqual(pixels_column_10[10], 40)
        self.assertEqual(pixels_column_10[9], 0)    # below the viewport window

    def test_vs2_tilemap_viewport_clamps_past_map_edge(self):
        povrender.all_strips[9] = make_tile_strip()
        povrender.set_vs2_scene(make_vs2_scene([], [], [
            default_tilemap(viewport=(6, 0, 8, 8)),
        ]))

        pixels_column_10 = povrender.render(10)
        self.assertEqual(pixels_column_10[13], 30)
        pixels_column_12 = povrender.render(12)
        self.assertEqual(pixels_column_12, [0] * povrender.led_count)

    def test_vs2_tilemap_wraps_around_column_zero(self):
        povrender.all_strips[9] = make_tile_strip()
        povrender.set_vs2_scene(make_vs2_scene([], [], [default_tilemap(x=254)]))

        pixels_column_254 = povrender.render(254)
        self.assertEqual(pixels_column_254[13], 10)
        pixels_column_0 = povrender.render(0)
        self.assertEqual(pixels_column_0[13], 20)

    def test_vs2_tilemap_draws_behind_sprites(self):
        povrender.all_strips[8] = bytes([2, 2, 1, 0, 1, 2, 3, 4])
        povrender.all_strips[9] = make_tile_strip()
        povrender.set_vs2_scene(make_vs2_scene([], [
            {"image": 8, "mode": 2, "flags": 1, "x": 10, "y": 40},
        ], [default_tilemap()]))

        pixels_column_10 = povrender.render(10)
        # the sprite pixel (data index 3 -> color 30) covers the tile's 10
        self.assertEqual(pixels_column_10[13], 30)
        # rows below the 2x2 sprite still show the tilemap
        self.assertEqual(pixels_column_10[11], 10)

    def test_vs2_tilemap_on_hidden_layer_is_dropped(self):
        povrender.all_strips[9] = make_tile_strip()
        povrender.set_vs2_scene(make_vs2_scene(
            [{"mode": 2, "visible": False}], [], [default_tilemap(layer=0)],
        ))

        pixels_column_10 = povrender.render(10)
        self.assertEqual(pixels_column_10, [0] * povrender.led_count)

    def test_vs2_tilemap_tunnel_projection_uses_deepspace(self):
        povrender.all_strips[9] = make_tile_strip()
        povrender.set_vs2_scene(make_vs2_scene([], [], [default_tilemap(mode=1)]))

        pixels_column_10 = povrender.render(10)
        self.assertEqual(pixels_column_10[povrender.deepspace[40]], 10)

    def test_vs2_fullscreen_tilemap_is_skipped(self):
        povrender.all_strips[9] = make_tile_strip()
        povrender.set_vs2_scene(make_vs2_scene([], [], [default_tilemap(mode=0)]))

        pixels_column_10 = povrender.render(10)
        self.assertEqual(pixels_column_10, [0] * povrender.led_count)

    def test_vs2_tilemap_with_mismatched_tile_dims_is_skipped(self):
        povrender.all_strips[9] = make_tile_strip()
        povrender.set_vs2_scene(make_vs2_scene([], [], [
            default_tilemap(tile_width=8, tile_height=8, viewport=(0, 0, 16, 16)),
        ]))

        pixels_column_10 = povrender.render(10)
        self.assertEqual(pixels_column_10, [0] * povrender.led_count)


if __name__ == "__main__":
    unittest.main()
