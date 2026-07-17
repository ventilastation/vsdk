"""Cross-language byte-layout checks for the desktop scene-shader packers."""

import base64
import json
import os
import shutil
import struct
import subprocess
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

import scene_shader


def make_vs2_fixture():
    """A mixed VS2 scene: layer modes, signed coords, flips and a tilemap."""
    header_size, layer_size, sprite_size, tilemap_size = 16, 8, 24, 32
    payload = bytearray(header_size + 2 * layer_size + 3 * sprite_size + tilemap_size + 4)
    payload[:4] = b"VS2\0"
    payload[4:8] = bytes((2, 2, 3, 1))
    struct.pack_into("<HHHH", payload, 8, header_size, layer_size, sprite_size, tilemap_size)
    offset = header_size
    # layer zero replaces record mode with HUD; layer one is hidden.
    payload[offset:offset + 3] = bytes((0, 2, 1))
    offset += layer_size
    payload[offset:offset + 3] = bytes((1, 1, 0))
    offset += layer_size
    payload[offset:offset + 5] = bytes((0, 7, 2, 0, 7))
    struct.pack_into("<ii", payload, offset + 10, -64, 1216)
    offset += sprite_size
    payload[offset:offset + 5] = bytes((1, 8, 0, 2, 1))  # hidden layer
    offset += sprite_size
    payload[offset:offset + 5] = bytes((255, 9, 1, 255, 1))
    struct.pack_into("<ii", payload, offset + 10, 255 * 256, 1 * 256)
    offset += sprite_size
    frames_offset = offset + tilemap_size
    struct.pack_into(
        "<BBBBHHHHHHHHiiI", payload, offset,
        0, 9, 1, 1, 2, 2, 4, 4, 1, 2, 6, 5, -128, 2048, frames_offset,
    )
    payload[frames_offset:frames_offset + 4] = bytes((0, 1, 255, 2))
    return bytes(payload)


def pack_for_json(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {key: pack_for_json(item) for key, item in value.items()}
    return value


class SceneShaderPackingTests(unittest.TestCase):
    def setUp(self):
        self.legacy = bytearray(b"\0\0\0\xff\xff" * 100)
        self.legacy[0:5] = bytes((3, 9, 7, 2, 0))
        self.legacy[15:20] = bytes((255, 4, 9, 1, 255))  # signed -1 -> HUD
        self.vs2 = make_vs2_fixture()
        self.assets = {
            3: bytes((255, 2, 1, 1)) + bytes(range(256)) * 2,
            9: bytes((4, 4, 2, 0)) + bytes((1, 2, 3, 255)) * 8,
        }
        self.palette = bytes((255, 3, 2, 1)) * 256 + bytes((255, 30, 20, 10)) * 256
        self.stars = ((2, 3), (255, 240), (300, -1))

    def test_python_packers_match_canonical_web_packers(self):
        if shutil.which("node") is None:
            self.skipTest("Node is required for the web/desktop packing parity test")
        payload = {
            "legacy": base64.b64encode(self.legacy).decode(),
            "vs2": base64.b64encode(self.vs2).decode(),
            "assets": [[slot, base64.b64encode(raw).decode()] for slot, raw in self.assets.items()],
            "palette": base64.b64encode(self.palette).decode(),
            "stars": self.stars,
        }
        node_script = r'''
const core = require("./web/scene-shader-core.js");
const input = JSON.parse(process.argv[1]);
const bytes = (encoded) => Uint8Array.from(Buffer.from(encoded, "base64"));
const assets = new Map(input.assets.map(([slot, encoded]) => {
  const raw = bytes(encoded);
  return [slot, { width: raw[0], height: raw[1], frames: raw[2], palette: raw[3], data: raw.subarray(4) }];
}));
const json = (packed) => Object.fromEntries(Object.entries(packed).map(([key, value]) => [
  key, ArrayBuffer.isView(value) ? Array.from(value) : value,
]));
const scene = (packed) => ({
  scene: Array.from(packed.scene),
  scene_width: packed.sceneWidth,
  scene_height: packed.sceneHeight,
  sprite_count: packed.spriteCount,
  tilemap_count: packed.tilemapCount,
  cells: Array.from(packed.cells),
  cells_width: packed.cellsWidth,
  cells_height: packed.cellsHeight,
});
const strips = (packed) => ({
  atlas: Array.from(packed.atlas), width: packed.width, height: packed.height,
  meta: Array.from(packed.meta), byte_length: packed.byteLength,
});
console.log(JSON.stringify({
  legacy: scene(core.packSceneLegacy(bytes(input.legacy))),
  vs2: scene(core.packSceneVs2Bytes(bytes(input.vs2))),
  strips: strips(core.packStrips(assets)),
  palette: json(core.packPalette(bytes(input.palette))),
  stars: json(core.packStars(input.stars.map(([x, y]) => ({x, y})))),
  deepspace: json(core.packDeepspace()),
}));
'''
        result = subprocess.run(
            ["node", "-e", node_script, json.dumps(payload)], cwd=ROOT,
            check=True, text=True, capture_output=True,
        )
        expected = json.loads(result.stdout)
        actual = {
            "legacy": pack_for_json(scene_shader.pack_scene_legacy(self.legacy)),
            "vs2": pack_for_json(scene_shader.pack_scene_vs2_bytes(self.vs2)),
            "strips": pack_for_json(scene_shader.pack_strips(self.assets.items())),
            "palette": pack_for_json(scene_shader.pack_palette(self.palette)),
            "stars": pack_for_json(scene_shader.pack_stars(self.stars)),
            "deepspace": pack_for_json(scene_shader.pack_deepspace()),
        }
        self.assertEqual(actual, expected)

    def test_desktop_loads_the_canonical_glsl_source(self):
        vertex = scene_shader.scene_vertex_source()
        fragment = scene_shader.scene_fragment_source()
        self.assertTrue(vertex.startswith("#version 330 core"))
        self.assertIn("layout(location = 0) in vec2 a_position", vertex)
        self.assertTrue(fragment.startswith("#version 330 core"))
        self.assertIn("uniform highp usampler2D u_scene", fragment)
        self.assertIn("u_led_axis", fragment)


if __name__ == "__main__":
    unittest.main()
