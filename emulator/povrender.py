"""Polar POV frame renderer + shared display state for the desktop emulator.

Holds the sprite table, image strips, palettes and starfield that comms.py
fills from the wire protocol, and renders one 54-pixel LED column at a time
(the same model as the spinning hardware).
"""

import random
import math
from struct import pack, unpack, unpack_from

from deepspace import deepspace, PIXELS
from apa102 import decode_preview_rgb

ROWS = 256
COLUMNS = 256
TRANSPARENT_INDEX = 0xFF
STARS = COLUMNS // 2
led_count = PIXELS

starfield = [(random.randrange(COLUMNS), random.randrange(ROWS)) for n in range(STARS)]
spritedata = bytearray( b"\0\0\0\xff\xff" * 100)
vs2_scene_sprites = None
vs2_scene_tilemaps = None
all_strips = {}
qpalette = []
upalette = []

# Full-frame display path: set by comms.py when a "frame_rgb" command arrives
# (the workbench's LED-bus capture, or a full-frame renderer like the
# Ventilagon port). 256 columns × led_count × 3 bytes (R, G, B per LED).
_voom_frame_rgb = None
_voom_frame_apa102 = None

def set_voom_frame_rgb(data):
    global _voom_frame_rgb, _voom_frame_apa102
    _voom_frame_rgb = bytes(data)
    _voom_frame_apa102 = None

def set_voom_frame_apa102(data):
    """Install a raw, spatially reassembled APA102 capture frame.

    The workbench has already placed the two physical arms into display
    coordinates, but each LED remains exactly [GB, B, G, R].  Decode it only
    when rendering, so a future calibration-profile change can reinterpret
    the same captured data correctly.
    """
    expected = COLUMNS * led_count * 4
    if len(data) != expected:
        raise ValueError("frame_apa102 has %d bytes, expected %d" % (len(data), expected))
    global _voom_frame_rgb, _voom_frame_apa102
    _voom_frame_apa102 = bytes(data)
    _voom_frame_rgb = None

def clear_voom_frame():
    global _voom_frame_rgb, _voom_frame_apa102
    _voom_frame_rgb = None
    _voom_frame_apa102 = None

def clear_vs2_scene():
    global vs2_scene_sprites, vs2_scene_tilemaps
    vs2_scene_sprites = None
    vs2_scene_tilemaps = None

def set_vs2_scene(data):
    global vs2_scene_sprites, vs2_scene_tilemaps
    scene = decode_vs2_scene(data)
    if scene is None:
        vs2_scene_sprites = None
        vs2_scene_tilemaps = None
    else:
        vs2_scene_sprites = scene["sprites"]
        vs2_scene_tilemaps = scene["tilemaps"]

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
    global palette, upalette
    palette = change_colors(paldata)
    upalette = unpack_palette(palette)

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

def render_tilemap(pixels, column, tilemap):
    # FULLSCREEN tilemaps are unsupported; only TUNNEL (1) and HUD (2) render.
    perspective = tilemap["perspective"]
    if perspective == 0:
        return
    strip = all_strips.get(tilemap["image"])
    if not strip:
        return
    w, h, total_frames, pal = unpack("BBBB", strip[0:4])
    if w == 255: w = 256 # special case for the planet backdrops
    tile_w = tilemap["tile_width"]
    tile_h = tilemap["tile_height"]
    if w != tile_w or h != tile_h:
        return
    total_frames = total_frames or 1
    pal_base = 256 * pal
    pixeldata = memoryview(strip)[4:]

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


def render(column):
    if _voom_frame_apa102 is not None:
        # Raw hardware capture: column N = led_count × [GB, B, G, R].
        # decode_preview_rgb applies the nominal APA102 light model and
        # monitor sRGB encoding. The calibrated profile-aware decoder will
        # replace its default response curves without changing this transport.
        offset = column * led_count * 4
        pixels = []
        for i in range(led_count):
            base = offset + i * 4
            gb, b, g, r = _voom_frame_apa102[base:base + 4]
            preview_r, preview_g, preview_b = decode_preview_rgb(gb, b, g, r)
            pixels.append(0xFF000000 | (preview_b << 16) | (preview_g << 8) | preview_r)
        return pixels

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

    scene_sprites = vs2_scene_sprites
    use_vs2_renderer = scene_sprites is not None
    if use_vs2_renderer and vs2_scene_tilemaps:
        # first slice: all tilemaps draw behind all sprites
        for tilemap in sorted(vs2_scene_tilemaps, key=lambda t: t["slot"], reverse=True):
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
        w, h, total_frames, pal = unpack("BBBB", strip[0:4])
        pal_base = 256 * pal
        if w == 255: w = 256 # special case for the planet backdrops
        pixeldata = memoryview(strip)[4:]

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
