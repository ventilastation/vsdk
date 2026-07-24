"""Polar POV frame renderer + shared display state for the desktop emulator.

Holds the sprite table, image strips, palettes and starfield that comms.py
fills from the wire protocol, and renders one 54-pixel LED column at a time
(the same model as the spinning hardware).
"""

import random
import math
import threading
from struct import pack, unpack, unpack_from

from deepspace import deepspace, PIXELS
from apa102 import decode_frame
from color_profile import ColorProfile, DEFAULT_PROFILE
import native_render

ROWS = 256
COLUMNS = 256
TRANSPARENT_INDEX = 0xFF
STARS = COLUMNS // 2
led_count = PIXELS

starfield = [(random.randrange(COLUMNS), random.randrange(ROWS)) for n in range(STARS)]
spritedata = bytearray( b"\0\0\0\xff\xff" * 100)

# The native compositor normally consumes decoded Python structures.  The
# full-frame scene shader instead needs the original wire bytes, plus a stable
# snapshot of assets and palette.  Updates arrive from comms.py's receiver
# thread, so publish those references under a small lock rather than letting a
# texture upload observe a half-replaced dictionary.
_scene_shader_lock = threading.RLock()
_scene_assets_revision = 0
_scene_palette_revision = 0
_vs2_scene_bytes = None
_palette_wire_bytes = b""

def set_spritedata(data):
    """Install the pre-VS2 fixed 100-sprite-slot table, keeping the Python
    renderer's spritedata and the native renderer's sprites[] in sync."""
    with _scene_shader_lock:
        spritedata[:] = data
    native_render.set_legacy_sprites(data)
# Decoded VS2 scenes are immutable after publication.  The communications
# thread swaps this one reference only after it has decoded the full payload,
# and a display draw captures it once for all 256 columns.
_vs2_scene = None
_CURRENT_VS2_SCENE = object()
all_strips = {}
qpalette = []
upalette = []

# Full-frame display path: set by comms.py when a "frame_rgb" command arrives
# (the workbench's LED-bus capture, or a full-frame renderer like the
# Ventilagon port). 256 columns × led_count × 3 bytes (R, G, B per LED).
_voom_frame_rgb = None
_voom_frame_apa102_raw = None
_voom_frame_apa102_pixels = None
_apa102_profile = DEFAULT_PROFILE

def set_voom_frame_rgb(data):
    global _voom_frame_rgb, _voom_frame_apa102_raw, _voom_frame_apa102_pixels
    _voom_frame_rgb = bytes(data)
    _voom_frame_apa102_raw = None
    _voom_frame_apa102_pixels = None

def _decode_apa102_frame():
    """Recompute the cached preview pixels for the current raw capture.

    decode_frame() is vectorized but still costs real time; running it once
    here per captured frame (or per calibration update) instead of once per
    rendered pixel per redraw is what keeps the desktop preview off the CPU's
    critical path.
    """
    global _voom_frame_apa102_pixels
    if _voom_frame_apa102_raw is None:
        _voom_frame_apa102_pixels = None
    else:
        _voom_frame_apa102_pixels = decode_frame(_voom_frame_apa102_raw, _apa102_profile).tolist()

def set_voom_frame_apa102(data):
    """Install a raw, spatially reassembled APA102 capture frame.

    The workbench has already placed the two physical arms into display
    coordinates, but each LED remains exactly [GB, B, G, R]. Decoded once here
    into preview pixels; set_apa102_profile_payload() re-decodes this same raw
    frame if a new calibration profile arrives before the next capture does.
    """
    expected = COLUMNS * led_count * 4
    if len(data) != expected:
        raise ValueError("frame_apa102 has %d bytes, expected %d" % (len(data), expected))
    global _voom_frame_rgb, _voom_frame_apa102_raw
    _voom_frame_apa102_raw = bytes(data)
    _voom_frame_rgb = None
    _decode_apa102_frame()

def apply_voom_frame_apa102_chunk(start_column, chunk_bytes):
    """Write one column-range chunk into the persistent raw APA102 buffer.

    Used by the workbench's UDP telemetry transport (comms.py's
    WorkbenchTelemetryConn), which streams a frame as many small per-chunk
    datagrams rather than one atomic payload -- UDP was chosen specifically
    so a lost datagram leaves a few columns stale instead of stalling or
    corrupting the whole frame (see docs/internals/workbench.md). Does not
    decode; call decode_voom_frame_apa102() afterward, at a rate decoupled
    from how often chunks arrive (decode_frame() reprocesses the *entire*
    buffer every time, so running it once per small chunk would multiply
    the vectorized decode cost far beyond what a smooth preview needs).
    """
    global _voom_frame_apa102_raw, _voom_frame_rgb
    if not isinstance(_voom_frame_apa102_raw, bytearray):
        _voom_frame_apa102_raw = bytearray(COLUMNS * led_count * 4)
    _voom_frame_rgb = None
    offset = start_column * led_count * 4
    _voom_frame_apa102_raw[offset:offset + len(chunk_bytes)] = chunk_bytes

def decode_voom_frame_apa102():
    """Public trigger for callers that update the raw buffer incrementally
    (apply_voom_frame_apa102_chunk) and need to explicitly request a decode
    pass on their own schedule, decoupled from chunk arrival."""
    _decode_apa102_frame()

def set_apa102_profile_payload(payload, schema_version=None, generation=None):
    """Install the board's acknowledged calibration profile for raw preview."""
    profile = ColorProfile.from_bytes(payload, schema_version, generation)
    global _apa102_profile
    _apa102_profile = profile
    _decode_apa102_frame()
    return profile

def get_apa102_profile():
    return _apa102_profile

def clear_voom_frame():
    global _voom_frame_rgb, _voom_frame_apa102_raw, _voom_frame_apa102_pixels
    _voom_frame_rgb = None
    _voom_frame_apa102_raw = None
    _voom_frame_apa102_pixels = None

def clear_vs2_scene():
    global _vs2_scene, _vs2_scene_bytes
    with _scene_shader_lock:
        _vs2_scene = None
        _vs2_scene_bytes = None
    native_render.clear_scene()

def set_vs2_scene(data):
    global _vs2_scene, _vs2_scene_bytes
    scene = decode_vs2_scene(data)
    with _scene_shader_lock:
        _vs2_scene = scene
        _vs2_scene_bytes = bytes(data) if scene is not None else None
    native_render.decode_scene(data)


def snapshot_vs2_scene():
    """Return the complete VS2 scene currently published by comms.

    Call this once per visible frame, then pass the result to ``render`` for
    every column.  A scene update from the receiver thread must not splice two
    scene revisions into the same circular display frame.
    """
    with _scene_shader_lock:
        return _vs2_scene


def snapshot_scene_shader_input():
    """Return the raw state for one GPU scene pass, or ``None`` for captures.

    ``frame_rgb`` and ``frame_apa102`` are already final LED pixels rather
    than sprite/VS2 scenes, so they deliberately remain on the existing CPU
    upload path.  The returned tuple/dicts only contain immutable byte
    strings, allowing the Pyglet draw thread to upload it after releasing the
    receiver lock.
    """
    with _scene_shader_lock:
        if _voom_frame_apa102_pixels is not None or _voom_frame_rgb is not None:
            return None
        return {
            "kind": "vs2" if _vs2_scene_bytes is not None else "legacy",
            "scene": _vs2_scene_bytes if _vs2_scene_bytes is not None else bytes(spritedata),
            "assets": tuple(all_strips.items()),
            "palette": _palette_wire_bytes,
            "stars": tuple(starfield),
            "assets_revision": _scene_assets_revision,
            "palette_revision": _scene_palette_revision,
        }

def decode_vs2_scene(data):
    if len(data) < 16 or data[0:4] != b"VS2\0":
        return None
    version, layer_count, sprite_count, tilemap_count, header_size, layer_size, sprite_size, tilemap_size = unpack_from(
        "<BBBBHHHH",
        data,
        4,
    )
    if version not in (1, 2):
        return None
    if version < 2:
        tilemap_count = 0
        tilemap_size = 0

    layers = []
    offset = header_size
    for _ in range(layer_count):
        if offset + layer_size > len(data):
            return None
        layer_id, mode, flags = unpack_from("<BBB", data, offset)
        layers.append({
            "id": layer_id,
            "mode": mode,
            "visible": bool(flags & 0x01),
        })
        offset += layer_size

    decoded = []
    for slot in range(sprite_count):
        if offset + sprite_size > len(data):
            return None
        layer_id, image, frame, mode, flags, _reserved0, _reserved1, _reserved2, x_fixed, y_fixed = unpack_from(
            "<BBBBBBhhii",
            data,
            offset,
        )
        layer = layers[layer_id] if layer_id < len(layers) else None
        offset += sprite_size
        if not flags & 0x01:
            continue
        if layer is not None and not layer["visible"]:
            continue
        if layer is not None:
            mode = layer["mode"]
        decoded.append({
            "slot": slot,
            "x": x_fixed / 256.0,
            "y": y_fixed / 256.0,
            "image": image,
            "frame": frame,
            "perspective": mode,
            "flip_x": bool(flags & 0x02),
            "flip_y": bool(flags & 0x04),
        })

    tilemaps = []
    for slot in range(tilemap_count):
        if offset + tilemap_size > len(data):
            return None
        (
            layer_id, image, flags, mode,
            map_columns, map_rows, tile_width, tile_height,
            viewport_x, viewport_y, viewport_w, viewport_h,
            x_fixed, y_fixed, frames_offset,
        ) = unpack_from("<BBBBHHHHHHHHiiI", data, offset)
        layer = layers[layer_id] if layer_id < len(layers) else None
        offset += tilemap_size
        cells = map_columns * map_rows
        if frames_offset + cells > len(data):
            return None
        if not flags & 0x01:
            continue
        if layer is not None and not layer["visible"]:
            continue
        if layer is not None:
            mode = layer["mode"]
        tilemaps.append({
            "slot": slot,
            "x": x_fixed / 256.0,
            "y": y_fixed / 256.0,
            "image": image,
            "frames": bytes(data[frames_offset:frames_offset + cells]),
            "columns": map_columns,
            "rows": map_rows,
            "tile_width": tile_width,
            "tile_height": tile_height,
            "viewport": (viewport_x, viewport_y, viewport_w, viewport_h),
            "perspective": mode,
        })
    return {"sprites": decoded, "tilemaps": tilemaps}

def change_colors(colors):
    # byteswap all longs
    fmt_unpack = "<" + "L" * (len(colors)//4)
    fmt_pack = ">" + "L" * (len(colors)//4)
    b = unpack(fmt_unpack, colors)
    return pack(fmt_pack, *b)

def pack_colors(colors):
    fmt_pack = "<" + "L" * len(colors)
    return pack(fmt_pack, *colors)

def unpack_palette(pal):
    fmt_unpack = "<" + "L" * (len(pal)//4)
    return unpack(fmt_unpack, pal)

def repeated(n, iterable):
    """Yield each item from `iterable` `n` times."""
    for item in iterable:
        for _ in range(n):
            yield item

def set_palettes(paldata):
    global palette, upalette, _palette_wire_bytes, _scene_palette_revision
    palette = change_colors(paldata)
    upalette = unpack_palette(palette)
    with _scene_shader_lock:
        _palette_wire_bytes = bytes(paldata)
        _scene_palette_revision += 1
    native_render.set_palette(paldata)

def set_image_strip(slot, data):
    """Install one decoded image strip, keeping the Python renderer's
    all_strips and the native renderer's image_stripes[] in sync. ImageStrip's
    C layout (frame_width, frame_height, total_frames, palette, then raw
    pixel data) is byte-identical to this wire blob, so the native side is a
    zero-copy pointer cast -- see emu_gpu_set_image_strip()."""
    global _scene_assets_revision
    with _scene_shader_lock:
        all_strips[slot] = bytes(data)
        _scene_assets_revision += 1
    native_render.set_image_strip(slot, data)

def get_visible_column(sprite_x, sprite_width, render_column):
    sprite_column = sprite_width - 1 - ((render_column - sprite_x + COLUMNS) % COLUMNS)
    if 0 <= sprite_column < sprite_width:
        return sprite_column
    else:
        return -1

def get_source_column(sprite_x, sprite_width, render_column, flip_x=False):
    sprite_column = get_visible_column(sprite_x, sprite_width, render_column)
    if sprite_column == -1:
        return -1
    if flip_x:
        return sprite_width - 1 - sprite_column
    return sprite_column

def _floor_coord(value):
    return int(math.floor(value))

def _clamp(value, minimum, maximum):
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value

def set_pixel(pixels, led, color):
    if 0 <= led < led_count:
        pixels[led] = color

# Every strip's 4-byte header (w, h, total_frames, pal_base) is immutable for
# as long as the strip's bytes object lives -- comms.py always installs a new
# bytes object on reload, so caching by identity needs no manual invalidation.
# Without this, render()/render_tilemap() re-ran struct.unpack on the same
# static header for every column (256x/frame) for every visible sprite/tile.
_strip_header_cache = {}

def _strip_header(strip):
    cached = _strip_header_cache.get(id(strip))
    if cached is not None and cached[0] is strip:
        return cached[1:]
    w, h, total_frames, pal = unpack("BBBB", strip[0:4])
    if w == 255: w = 256 # special case for the planet backdrops
    header = (w, h, total_frames, 256 * pal, memoryview(strip)[4:])
    _strip_header_cache[id(strip)] = (strip,) + header
    return header

def render_tilemap(pixels, column, tilemap):
    # FULLSCREEN tilemaps are unsupported; only TUNNEL (1) and HUD (2) render.
    perspective = tilemap["perspective"]
    if perspective == 0:
        return
    strip = all_strips.get(tilemap["image"])
    if not strip:
        return
    w, h, total_frames, pal_base, pixeldata = _strip_header(strip)
    tile_w = tilemap["tile_width"]
    tile_h = tilemap["tile_height"]
    if w != tile_w or h != tile_h:
        return
    total_frames = total_frames or 1

    map_columns = tilemap["columns"]
    map_w = map_columns * tile_w
    map_h = tilemap["rows"] * tile_h
    viewport_x, viewport_y, viewport_w, viewport_h = tilemap["viewport"]
    if viewport_x >= map_w or viewport_y >= map_h:
        return
    viewport_w = min(viewport_w, map_w - viewport_x)
    viewport_h = min(viewport_h, map_h - viewport_y)

    x0 = _floor_coord(tilemap["x"])
    delta = (column - x0) % COLUMNS
    if delta >= viewport_w:
        return
    sx = viewport_x + delta
    tile_col = sx // tile_w
    # strip data columns are stored mirrored, same as sprites
    source_column = tile_w - 1 - (sx % tile_w)

    frames = tilemap["frames"]
    y0 = _floor_coord(tilemap["y"])
    for dest_y in range(max(y0, 0), min(y0 + viewport_h, ROWS)):
        sy = viewport_y + (dest_y - y0)
        frame = frames[(sy // tile_h) * map_columns + tile_col]
        if frame == 255:
            continue
        frame %= total_frames
        index = pixeldata[source_column * tile_h + frame * tile_w * tile_h + (sy % tile_h)]
        if index != TRANSPARENT_INDEX:
            color = upalette[index + pal_base]
            if perspective == 1:
                led = deepspace[dest_y]
            else:
                led = led_count - 1 - dest_y
            set_pixel(pixels, led, color)


def step_starfield():
    for (n, (x, y)) in enumerate(starfield):
        y -= 1
        if y < 0:
            y = ROWS - 1
            x = random.randrange(COLUMNS)
        starfield[n] = (x, y)
    native_render.step_starfield()


def render(column, vs2_scene=_CURRENT_VS2_SCENE):
    if vs2_scene is _CURRENT_VS2_SCENE:
        vs2_scene = _vs2_scene
    if _voom_frame_apa102_pixels is not None:
        # Raw hardware capture: column N = led_count × [GB, B, G, R], already
        # decoded into preview pixels by _decode_apa102_frame() when the frame
        # (or the calibration profile) was installed.
        offset = column * led_count
        return _voom_frame_apa102_pixels[offset:offset + led_count]

    if _voom_frame_rgb is not None:
        # RGB voom frame: column N = led_count × (R, G, B) triples
        # Reconstruct as ABGR uint32 to match the palette entry format used by upalette.
        offset = column * led_count * 3
        pixels = []
        for i in range(led_count):
            base = offset + i * 3
            r, g, b = _voom_frame_rgb[base], _voom_frame_rgb[base + 1], _voom_frame_rgb[base + 2]
            pixels.append(0xFF000000 | (b << 16) | (g << 8) | r)
        return pixels

    pixels = [0x00000000] * led_count

    for (x,y) in starfield:
        if x == column:
            try:
                px = deepspace[y]
                if px < PIXELS:
                    pixels[px] = 0xff404040
            except Exception as e:
                print(e, len(pixels), y, px)
                print(y, deepspace)

    scene_sprites = vs2_scene["sprites"] if vs2_scene is not None else None
    use_vs2_renderer = vs2_scene is not None
    if use_vs2_renderer and vs2_scene["tilemaps"]:
        # first slice: all tilemaps draw behind all sprites
        for tilemap in sorted(vs2_scene["tilemaps"], key=lambda t: t["slot"], reverse=True):
            render_tilemap(pixels, column, tilemap)
    if scene_sprites is None:
        # sprite 0 is drawn on top of all the others
        scene_sprites = []
        for n in range(99, -1, -1):
            x, y, image, frame, perspective = unpack("BBBBb", spritedata[n*5:n*5+5])
            if frame == 255:
                continue
            scene_sprites.append({
                "slot": n,
                "x": x,
                "y": y,
                "image": image,
                "frame": frame,
                "perspective": perspective,
                "flip_x": False,
                "flip_y": False,
            })
    else:
        scene_sprites = sorted(scene_sprites, key=lambda sprite: sprite["slot"], reverse=True)

    for sprite in scene_sprites:
        x = _floor_coord(sprite["x"]) if use_vs2_renderer else int(sprite["x"])
        y = _floor_coord(sprite["y"]) if use_vs2_renderer else int(sprite["y"])
        image = sprite["image"]
        frame = sprite["frame"]
        perspective = sprite["perspective"]
        flip_x = sprite.get("flip_x", False)
        flip_y = sprite.get("flip_y", False)

        strip = all_strips.get(image)
        if not strip:
            continue
        w, h, total_frames, pal_base, pixeldata = _strip_header(strip)

        frame %= total_frames

        visible_column = get_source_column(x, w, column, flip_x)
        if visible_column != -1:
            base = visible_column * h + (frame * w * h)
            if perspective:
                y_start = max(y, 0)
                y_end = min(y + h, ROWS)

                for dest_y in range(y_start, y_end):
                    source_row = dest_y - y
                    if flip_y:
                        source_row = h - 1 - source_row
                    index = pixeldata[base + source_row]
                    if index != TRANSPARENT_INDEX:
                        color = upalette[index + pal_base]
                        if perspective == 1:
                            led = deepspace[dest_y]
                        else:
                            led = led_count - 1 - dest_y
                        set_pixel(pixels, led, color)
            else:
                zleds = deepspace[_clamp(255 - y, 0, ROWS - 1)]

                for led in range(zleds):
                    source_row = led * led_count // zleds
                    if source_row >= h:
                        break
                    if not flip_y:
                        source_row = h - 1 - source_row
                    index = pixeldata[base + source_row]
                    if index != TRANSPARENT_INDEX:
                        color = upalette[index + pal_base]
                        set_pixel(pixels, led, color)

    return pixels


def render_frame(vs2_scene):
    """Render all 256 columns at once. Returns a numpy uint32 array
    (COLUMNS*led_count) of packed pixels in render()'s 0xAABBGGRR layout.

    Raw hardware-capture display (_voom_frame_apa102_pixels/_voom_frame_rgb)
    still goes through render() per column -- the native renderer only
    replaces the VS2-scene path and the pre-VS2 fixed 100-sprite-slot path
    (render()/render_tilemap()'s two branches in Python), which is what
    real games and the menu actually spend their render time in.
    """
    if _voom_frame_apa102_pixels is None and _voom_frame_rgb is None:
        native_pixels = (
            native_render.render_frame() if vs2_scene is not None
            else native_render.render_legacy_frame()
        )
        if native_pixels is not None:
            return native_pixels

    # Imported lazily, not at module level: this module is on comms.py's
    # always-imported path, and the headless Raspberry Pi base -- which
    # never renders a frame -- doesn't have numpy installed.
    import numpy as np
    all_pixels = []
    for column in range(COLUMNS):
        all_pixels.extend(render(column, vs2_scene))
    return np.array(all_pixels, dtype=np.uint32)
