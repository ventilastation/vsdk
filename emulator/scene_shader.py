"""Packed scene data and an OpenGL 3.3 full-frame POV compositor.

The shader itself is deliberately loaded from ``web/scene-shader-core.js``.
That file is the canonical description shared by the browser and the desktop
emulator; keeping one GLSL source avoids small perspective or palette-swizzle
differences between the two previews.  The Python packers below mirror its
typed-array layouts and are covered by ``tests/test_scene_shader_pack.py``.

This module has no pyglet dependency until :class:`DesktopSceneCompositor` is
constructed, so the packing code remains usable in headless unit tests.
"""

from __future__ import annotations

import ctypes
import re
from pathlib import Path
from struct import unpack_from

import numpy as np

from deepspace import deepspace

COLUMNS = 256
PIXELS = 54
ROWS = 256
STARS = COLUMNS // 2
ATLAS_WIDTH = 2048
SCENE_TEXELS_PER_ENTITY = 4
SCENE_LANES_PER_ENTITY = SCENE_TEXELS_PER_ENTITY * 4
TRANSPARENT_INDEX = 0xFF
MODE_PLANET = 0
MODE_TUNNEL = 1
MODE_HUD = 2


def _empty_scene():
    return {"sprites": [], "tilemaps": [], "cells": []}


def canonical_mode(mode):
    """Match the legacy CPU renderer's interpretation of perspective."""
    if mode == MODE_PLANET:
        return MODE_PLANET
    if mode == MODE_TUNNEL:
        return MODE_TUNNEL
    return MODE_HUD


def _as_u32(value):
    return int(value) & 0xFFFFFFFF


def _push_sprite(packer, *, x, y, strip, frame, mode, flip_x=False, flip_y=False):
    lanes = np.zeros(SCENE_LANES_PER_ENTITY, dtype=np.uint32)
    lanes[0] = _as_u32(x)
    lanes[1] = _as_u32(y)
    lanes[2] = int(strip) & 0xFF
    lanes[3] = int(frame) & 0xFF
    lanes[4] = canonical_mode(mode)
    lanes[5] = (1 if flip_x else 0) | (2 if flip_y else 0)
    packer["sprites"].append(lanes)


def _push_tilemap(packer, *, x, y, strip, mode, columns, rows, tile_width,
                  tile_height, viewport, frames):
    offset = sum(len(cells) for cells in packer["cells"])
    raw_cells = bytes(frames)
    packer["cells"].append(raw_cells)
    lanes = np.zeros(SCENE_LANES_PER_ENTITY, dtype=np.uint32)
    lanes[0] = _as_u32(x)
    lanes[1] = _as_u32(y)
    lanes[2] = int(strip) & 0xFF
    lanes[3] = canonical_mode(mode)
    lanes[4:8] = (columns, rows, tile_width, tile_height)
    lanes[8:12] = viewport
    lanes[12] = offset
    packer["tilemaps"].append(lanes)


def _finish_scene(packer):
    entity_count = len(packer["sprites"]) + len(packer["tilemaps"])
    scene = np.zeros((max(entity_count, 1), SCENE_LANES_PER_ENTITY), dtype=np.uint32)
    for row, lanes in enumerate(packer["sprites"] + packer["tilemaps"]):
        scene[row] = lanes

    cell_length = sum(len(cells) for cells in packer["cells"])
    cells_height = max(1, (cell_length + ATLAS_WIDTH - 1) // ATLAS_WIDTH)
    cells = np.zeros(ATLAS_WIDTH * cells_height, dtype=np.uint8)
    cursor = 0
    for chunk in packer["cells"]:
        cells[cursor:cursor + len(chunk)] = np.frombuffer(chunk, dtype=np.uint8)
        cursor += len(chunk)
    return {
        "scene": scene.reshape(-1),
        "scene_width": SCENE_TEXELS_PER_ENTITY,
        "scene_height": max(entity_count, 1),
        "sprite_count": len(packer["sprites"]),
        "tilemap_count": len(packer["tilemaps"]),
        "cells": cells,
        "cells_width": ATLAS_WIDTH,
        "cells_height": cells_height,
    }


def pack_scene_legacy(sprite_table_bytes):
    """Pack the 100 x 5-byte legacy ``sprites`` payload for the shader."""
    packer = _empty_scene()
    data = bytes(sprite_table_bytes or b"")
    for slot in range(len(data) // 5):
        base = slot * 5
        frame = data[base + 3]
        if frame == 0xFF:
            continue
        raw_mode = data[base + 4]
        mode = raw_mode - 256 if raw_mode & 0x80 else raw_mode
        _push_sprite(
            packer, x=data[base], y=data[base + 1], strip=data[base + 2],
            frame=frame, mode=mode,
        )
    return _finish_scene(packer)


def pack_scene_vs2_bytes(scene_bytes):
    """Decode raw VS2 directly into the fixed GPU records, allocation-light."""
    packer = _empty_scene()
    data = bytes(scene_bytes or b"")
    if len(data) < 16 or data[:4] != b"VS2\0" or data[4] not in (1, 2):
        return _finish_scene(packer)

    version, layer_count, sprite_count = data[4:7]
    tilemap_count = data[7] if version >= 2 else 0
    header_size, layer_size, sprite_size, tilemap_size = unpack_from("<HHHH", data, 8)
    if (header_size < 16 or layer_size < 3 or sprite_size < 18 or
            (version >= 2 and tilemap_size < 32) or header_size > len(data)):
        return _finish_scene(packer)

    layers = {}
    offset = header_size
    for _ in range(layer_count):
        if offset + layer_size > len(data):
            return _finish_scene(packer)
        layers[data[offset]] = (data[offset + 1], bool(data[offset + 2] & 1))
        offset += layer_size

    for _slot in range(sprite_count):
        if offset + sprite_size > len(data):
            return _finish_scene(packer)
        record = offset
        offset += sprite_size
        flags = data[record + 4]
        layer = layers.get(data[record])
        if not flags & 1 or (layer is not None and not layer[1]):
            continue
        x_fixed = unpack_from("<i", data, record + 10)[0]
        y_fixed = unpack_from("<i", data, record + 14)[0]
        _push_sprite(
            packer,
            x=x_fixed // 256,
            y=y_fixed // 256,
            strip=data[record + 1],
            frame=data[record + 2],
            mode=layer[0] if layer is not None else data[record + 3],
            flip_x=bool(flags & 2),
            flip_y=bool(flags & 4),
        )

    for _slot in range(tilemap_count):
        if offset + tilemap_size > len(data):
            return _finish_scene(packer)
        record = offset
        offset += tilemap_size
        flags = data[record + 2]
        layer = layers.get(data[record])
        if not flags & 1 or (layer is not None and not layer[1]):
            continue
        columns, rows = unpack_from("<HH", data, record + 4)
        cells_length = columns * rows
        frames_offset = unpack_from("<I", data, record + 28)[0]
        if frames_offset + cells_length > len(data):
            continue
        mode = layer[0] if layer is not None else data[record + 3]
        if canonical_mode(mode) == MODE_PLANET:
            continue
        _push_tilemap(
            packer,
            x=unpack_from("<i", data, record + 20)[0] // 256,
            y=unpack_from("<i", data, record + 24)[0] // 256,
            strip=data[record + 1], mode=mode,
            columns=columns, rows=rows,
            tile_width=unpack_from("<H", data, record + 8)[0],
            tile_height=unpack_from("<H", data, record + 10)[0],
            viewport=unpack_from("<HHHH", data, record + 12),
            frames=data[frames_offset:frames_offset + cells_length],
        )
    return _finish_scene(packer)


def pack_strips(raw_assets):
    """Pack ``{slot: ImageStrip wire blob}`` data into a byte atlas + metadata."""
    meta = np.zeros(256 * 4, dtype=np.uint32)
    chunks = []
    offset = 0
    assets = dict(raw_assets)
    for slot in range(256):
        raw = assets.get(slot)
        if raw is None:
            continue
        raw = bytes(raw)
        if len(raw) < 4:
            continue
        width, height, frames, palette = raw[:4]
        pixels = raw[4:]
        if not pixels or not height:
            continue
        width = 256 if width == 255 else width
        base = slot * 4
        meta[base:base + 4] = (width, height, max(frames, 1) & 0xFF | (palette << 8), offset)
        chunks.append(pixels)
        offset += len(pixels)
    height = max(1, (offset + ATLAS_WIDTH - 1) // ATLAS_WIDTH)
    atlas = np.zeros(ATLAS_WIDTH * height, dtype=np.uint8)
    cursor = 0
    for chunk in chunks:
        atlas[cursor:cursor + len(chunk)] = np.frombuffer(chunk, dtype=np.uint8)
        cursor += len(chunk)
    return {
        "atlas": atlas, "width": ATLAS_WIDTH, "height": height,
        "meta": meta, "byte_length": offset,
    }


def pack_palette(palette_bytes):
    data = bytes(palette_bytes or b"")
    rows = max(1, len(data) // 1024)
    packed = np.zeros(256 * 4 * rows, dtype=np.uint8)
    if data:
        packed[:min(len(data), len(packed))] = np.frombuffer(data[:len(packed)], dtype=np.uint8)
    return {"data": packed, "width": 256, "height": rows}


def pack_stars(positions):
    """Pack the fixed 128-star texture shared with the browser compositor."""
    packed = np.zeros(STARS, dtype=np.uint32)
    count = min(len(positions), STARS)
    for index, (x, y) in enumerate(positions[:count]):
        packed[index] = (int(x) & 0xFF) | ((int(y) & 0xFF) << 8)
    return {"data": packed, "width": STARS, "height": 1, "count": count}


def pack_deepspace():
    packed = np.zeros(256 * 2, dtype=np.uint32)
    packed[:ROWS] = deepspace
    lo = [255] * PIXELS
    hi = [0] * PIXELS
    for y, led in enumerate(deepspace):
        if led < PIXELS:
            lo[led] = min(lo[led], y)
            hi[led] = max(hi[led], y)
    for led in range(PIXELS):
        packed[256 + led] = lo[led] | (hi[led] << 8)
    return {"data": packed, "width": 256, "height": 2}


def _shared_shader_source(name):
    """Extract a template literal from the canonical browser shader module."""
    core = Path(__file__).resolve().parents[1] / "web" / "scene-shader-core.js"
    source = core.read_text(encoding="utf-8")
    match = re.search(r"const %s = `(?P<body>.*?)`;" % re.escape(name), source, re.DOTALL)
    if match is None:
        raise RuntimeError("could not find %s in %s" % (name, core))
    return match.group("body").replace("${ATLAS_WIDTH}", str(ATLAS_WIDTH))


def scene_vertex_source():
    return "#version 330 core\n" + _shared_shader_source("SCENE_VERTEX_SOURCE_BODY")


def scene_fragment_source():
    return "#version 330 core\n" + _shared_shader_source("SCENE_FRAGMENT_SOURCE_BODY")


class DesktopSceneCompositor:
    """OpenGL 3.3 scene pass that writes directly into the LED colour texture."""

    def __init__(self):
        # Delayed imports keep pure packing tests independent of windowing.
        from pyglet.gl import (
            GL_CLAMP_TO_EDGE, GL_COLOR_ATTACHMENT0,
            GL_FRAMEBUFFER, GL_FRAMEBUFFER_COMPLETE, GL_NEAREST, GL_R8UI,
            GL_R32UI, GL_RED_INTEGER, GL_RGBA, GL_RGBA32UI, GL_RGBA_INTEGER,
            GL_TEXTURE0, GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER,
            GL_TEXTURE_MIN_FILTER, GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T,
            GL_TRIANGLES, GL_UNSIGNED_BYTE, GL_UNSIGNED_INT, GL_VIEWPORT, GLint, GLuint,
            glActiveTexture, glBindFramebuffer, glBindTexture,
            glCheckFramebufferStatus, glDisable, glGetIntegerv,
            glFramebufferTexture2D, glGenFramebuffers, glGenTextures,
            glTexImage2D, glTexParameteri, glViewport,
        )
        from pyglet.graphics.shader import Shader, ShaderProgram

        self.gl = {
            name: value for name, value in locals().items()
            if name.startswith("GL_") or name.startswith("gl") or name in ("GLint", "GLuint")
        }
        self.program = ShaderProgram(
            Shader(scene_vertex_source(), "vertex"),
            Shader(scene_fragment_source(), "fragment"),
        )
        # Give pyglet a normal vertex list; the canonical shader pins this
        # attribute to location zero, and its public name is still a_position.
        self.vertex_list = self.program.vertex_list(
            3, self.gl["GL_TRIANGLES"],
            a_position=("f", (-1.0, -1.0, 3.0, -1.0, -1.0, 3.0)),
        )
        self.textures = {name: self._new_texture() for name in (
            "strips", "strip_meta", "palette", "scene", "cells", "stars", "deepspace",
        )}
        self.framebuffer = self.gl["GLuint"]()
        self.gl["glGenFramebuffers"](1, ctypes.byref(self.framebuffer))
        self._assets_key = None
        self._palette_key = None
        self._deepspace_uploaded = False

    def _new_texture(self):
        texture = self.gl["GLuint"]()
        self.gl["glGenTextures"](1, ctypes.byref(texture))
        self.gl["glBindTexture"](self.gl["GL_TEXTURE_2D"], texture)
        for parameter in (self.gl["GL_TEXTURE_MIN_FILTER"], self.gl["GL_TEXTURE_MAG_FILTER"]):
            self.gl["glTexParameteri"](self.gl["GL_TEXTURE_2D"], parameter, self.gl["GL_NEAREST"])
        for parameter in (self.gl["GL_TEXTURE_WRAP_S"], self.gl["GL_TEXTURE_WRAP_T"]):
            self.gl["glTexParameteri"](self.gl["GL_TEXTURE_2D"], parameter, self.gl["GL_CLAMP_TO_EDGE"])
        return texture

    @staticmethod
    def _pointer(data):
        return np.ascontiguousarray(data).ctypes.data_as(ctypes.c_void_p)

    def _upload(self, name, data, width, height, internal_format, pixel_format, pixel_type):
        gl = self.gl
        gl["glBindTexture"](gl["GL_TEXTURE_2D"], self.textures[name])
        gl["glTexImage2D"](
            gl["GL_TEXTURE_2D"], 0, internal_format, width, height, 0,
            pixel_format, pixel_type, self._pointer(data),
        )

    def _set_uniforms(self):
        self.program.use()
        for unit, name in enumerate((
            "u_strips", "u_strip_meta", "u_palette", "u_scene", "u_cells", "u_stars", "u_deepspace",
        )):
            self.program[name] = unit
            self.gl["glActiveTexture"](self.gl["GL_TEXTURE0"] + unit)
            self.gl["glBindTexture"](self.gl["GL_TEXTURE_2D"], self.textures[name[2:]])
        self.program["u_column_offset"] = 0
        self.program["u_led_axis"] = 1

    def render(self, scene_input, led_texture):
        """Render one raw scene snapshot into ``led_texture``. Returns true."""
        gl = self.gl
        assets_key = scene_input["assets_revision"]
        if assets_key != self._assets_key:
            strips = pack_strips(scene_input["assets"])
            self._upload("strips", strips["atlas"], strips["width"], strips["height"],
                         gl["GL_R8UI"], gl["GL_RED_INTEGER"], gl["GL_UNSIGNED_BYTE"])
            self._upload("strip_meta", strips["meta"], 256, 1,
                         gl["GL_RGBA32UI"], gl["GL_RGBA_INTEGER"], gl["GL_UNSIGNED_INT"])
            self._assets_key = assets_key

        palette_key = scene_input["palette_revision"]
        if palette_key != self._palette_key:
            palette = pack_palette(scene_input["palette"])
            self._upload("palette", palette["data"], palette["width"], palette["height"],
                         gl["GL_RGBA"], gl["GL_RGBA"], gl["GL_UNSIGNED_BYTE"])
            self._palette_key = palette_key

        if not self._deepspace_uploaded:
            deepspace_data = pack_deepspace()
            self._upload("deepspace", deepspace_data["data"], 256, 2,
                         gl["GL_R32UI"], gl["GL_RED_INTEGER"], gl["GL_UNSIGNED_INT"])
            self._deepspace_uploaded = True

        scene = (pack_scene_vs2_bytes(scene_input["scene"])
                 if scene_input["kind"] == "vs2"
                 else pack_scene_legacy(scene_input["scene"]))
        stars = pack_stars(scene_input["stars"])
        self._upload("scene", scene["scene"], scene["scene_width"], scene["scene_height"],
                     gl["GL_RGBA32UI"], gl["GL_RGBA_INTEGER"], gl["GL_UNSIGNED_INT"])
        self._upload("cells", scene["cells"], scene["cells_width"], scene["cells_height"],
                     gl["GL_R8UI"], gl["GL_RED_INTEGER"], gl["GL_UNSIGNED_BYTE"])
        self._upload("stars", stars["data"], stars["width"], 1,
                     gl["GL_R32UI"], gl["GL_RED_INTEGER"], gl["GL_UNSIGNED_INT"])

        previous_viewport = (gl["GLint"] * 4)()
        gl["glGetIntegerv"](gl["GL_VIEWPORT"], previous_viewport)
        gl["glBindFramebuffer"](gl["GL_FRAMEBUFFER"], self.framebuffer)
        gl["glFramebufferTexture2D"](
            gl["GL_FRAMEBUFFER"], gl["GL_COLOR_ATTACHMENT0"], gl["GL_TEXTURE_2D"], led_texture.id, 0,
        )
        if gl["glCheckFramebufferStatus"](gl["GL_FRAMEBUFFER"]) != gl["GL_FRAMEBUFFER_COMPLETE"]:
            gl["glBindFramebuffer"](gl["GL_FRAMEBUFFER"], 0)
            raise RuntimeError("scene compositor framebuffer is incomplete")
        gl["glViewport"](0, 0, COLUMNS, PIXELS)
        gl["glDisable"](0x0BE2)  # GL_BLEND; do not let ring-display blend state leak in.
        self._set_uniforms()
        self.program["u_sprite_count"] = scene["sprite_count"]
        self.program["u_tilemap_count"] = scene["tilemap_count"]
        self.program["u_star_count"] = stars["count"]
        self.vertex_list.draw(gl["GL_TRIANGLES"])
        self.program.stop()
        gl["glBindFramebuffer"](gl["GL_FRAMEBUFFER"], 0)
        # Preserve the actual drawable viewport rather than assuming logical
        # window dimensions; this matters on Retina/HiDPI desktop displays.
        gl["glViewport"](*previous_viewport)
        return True

    def read_pixels(self):
        """Read back the rendered LED texture as column-major RGBA bytes."""
        from pyglet.gl import GL_FRAMEBUFFER, GL_RGBA, GL_TEXTURE_2D, GL_UNSIGNED_BYTE, glBindFramebuffer, glReadPixels

        pixels = np.zeros((PIXELS, COLUMNS, 4), dtype=np.uint8)
        glBindFramebuffer(GL_FRAMEBUFFER, self.framebuffer)
        glReadPixels(0, 0, COLUMNS, PIXELS, GL_RGBA, GL_UNSIGNED_BYTE, self._pointer(pixels))
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        return np.ascontiguousarray(pixels.transpose(1, 0, 2).reshape(-1, 4))
