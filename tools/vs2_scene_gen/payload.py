"""A pure-Python reader for ``vs2.export_scene_payload()`` bytes.

Used only by :mod:`recover`, to turn what a real ``build()`` produced back
into plain Python data structures comparable against a scene model. This
is intentionally **version-pinned** to ``PAYLOAD_VERSION == 3`` (the value
in ``apps/micropython/vs2/__init__.py`` as of this task) rather than
generic across versions -- :func:`parse_scene_payload` raises loudly on a
version mismatch instead of silently misreading a layout that has since
changed. The record layout mirrors ``export_scene_payload()``'s own
``struct.pack_into`` calls exactly; see that function's comments for what
each field means (this module does not re-derive them).

**Draw-order index, not attribute names.** A payload has no idea a sprite
is called ``self.enemies`` -- it only has ``(kind, index-into-that-kind's-
own-list)`` per drawable, in draw order. :mod:`recover`'s job is to
compare *counts, positions and images* against the model's own draw-order
sequence, not names -- exactly the boundary the proposal draws between
"the editor recovers the true scene ... by reading
``vs2.export_scene_payload()``" (structure only) and a name-aware tool
like ``vs2beh`` (which instead walks live Python objects -- see
``ventilastation/behavior_control.py``).
"""

import struct

MAGIC = b"VS2\0"
SUPPORTED_VERSION = 3

DRAW_SPRITE = 0
DRAW_TILEMAP = 1

_HEADER_FMT = "<4sBBBBHHHH"
_LAYER_FMT = "<BBBBBBBB"
_SPRITE_FMT = "<BBBBBBhhii"  # first 18 bytes of each (possibly wider) record
_TILEMAP_FMT = "<BBBBHHHHHHHHiiI"  # exactly 32 bytes, no trailing padding


class PayloadError(ValueError):
    """The payload is malformed, truncated, or not
    ``SUPPORTED_VERSION``."""


def _fixed_8_8_to_float(raw):
    return raw / 256.0


def parse_scene_payload(payload):
    """Parse ``export_scene_payload()``'s bytes into a plain dict::

        {"version": 3,
         "layers": [{"index", "projection", "visible", "camera_x",
                      "camera_y", "curve_index"}, ...],
         "sprites": [{"layer_index", "strip", "frame", "visible",
                       "flip_x", "flip_y", "x", "y"}, ...],
         "tilemaps": [{"layer_index", "strip", "visible", "flip_x",
                        "flip_y", "columns", "rows", "tile_width",
                        "tile_height", "view_x", "view_y", "view_width",
                        "view_height", "x", "y", "cells": bytes}, ...],
         "drawables": [{"kind": "sprite"|"tilemap", "index"}, ...]}

    ``drawables`` is in draw order -- the same order :mod:`generator`
    emits the model's layers/drawables in -- and is what
    :func:`recover.compare_payload_to_model` walks alongside the model.

    Raises:
        PayloadError: On a bad magic number, an unsupported version, or a
            payload too short for the counts its own header declares.
    """
    payload = bytes(payload)
    header_size = struct.calcsize(_HEADER_FMT)
    if len(payload) < header_size:
        raise PayloadError("payload shorter than the header (%d bytes)" % (header_size,))
    (magic, version, layer_count, sprite_count, tilemap_count,
     declared_header_size, layer_size, sprite_size, tilemap_size) = struct.unpack_from(
        _HEADER_FMT, payload, 0)
    if magic != MAGIC:
        raise PayloadError("bad magic %r; not a vs2 scene payload" % (magic,))
    if version != SUPPORTED_VERSION:
        raise PayloadError(
            "payload version %d != this parser's supported version %d "
            "(vs2/__init__.py's wire format has changed; update payload.py)"
            % (version, SUPPORTED_VERSION))

    offset = declared_header_size
    layers = []
    for index in range(layer_count):
        (layer_index, projection, flags, camera_x, camera_y, curve_index,
         _reserved0, _reserved1) = struct.unpack_from(_LAYER_FMT, payload, offset)
        layers.append({
            "index": layer_index, "projection": projection,
            "visible": bool(flags & 0x01), "camera_x": camera_x,
            "camera_y": camera_y, "curve_index": curve_index,
        })
        offset += layer_size

    sprites = []
    for index in range(sprite_count):
        (layer_index, strip, frame, projection, flags, _reserved0,
         _reserved1, _reserved2, x_fixed, y_fixed) = struct.unpack_from(
            _SPRITE_FMT, payload, offset)
        sprites.append({
            "layer_index": layer_index, "strip": strip, "frame": frame,
            "projection": projection, "visible": bool(flags & 0x01),
            "flip_x": bool(flags & 0x02), "flip_y": bool(flags & 0x04),
            "x": _fixed_8_8_to_float(x_fixed), "y": _fixed_8_8_to_float(y_fixed),
        })
        offset += sprite_size

    tilemaps = []
    cells_by_index = []
    for index in range(tilemap_count):
        (layer_index, strip, flags, projection, columns, rows, tile_width,
         tile_height, view_x, view_y, view_width, view_height, x_fixed,
         y_fixed, cells_offset) = struct.unpack_from(_TILEMAP_FMT, payload, offset)
        tilemaps.append({
            "layer_index": layer_index, "strip": strip,
            "visible": bool(flags & 0x01), "flip_x": bool(flags & 0x02),
            "flip_y": bool(flags & 0x04), "columns": columns, "rows": rows,
            "tile_width": tile_width, "tile_height": tile_height,
            "view_x": view_x, "view_y": view_y, "view_width": view_width,
            "view_height": view_height,
            "x": _fixed_8_8_to_float(x_fixed), "y": _fixed_8_8_to_float(y_fixed),
        })
        cells_by_index.append((cells_offset, columns * rows))
        offset += tilemap_size

    for tilemap, (cells_offset, count) in zip(tilemaps, cells_by_index):
        tilemap["cells"] = bytes(payload[cells_offset:cells_offset + count])

    draw_ref_offset = 0
    if cells_by_index:
        draw_ref_offset = max(o + n for o, n in cells_by_index)
    else:
        draw_ref_offset = offset

    drawables = []
    draw_ref_size = 2
    remaining = len(payload) - draw_ref_offset
    count = remaining // draw_ref_size
    for index in range(count):
        kind, kind_index = struct.unpack_from(
            "<BB", payload, draw_ref_offset + index * draw_ref_size)
        drawables.append({
            "kind": "sprite" if kind == DRAW_SPRITE else "tilemap",
            "index": kind_index,
        })

    return {
        "version": version, "layers": layers, "sprites": sprites,
        "tilemaps": tilemaps, "drawables": drawables,
    }
