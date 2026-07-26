"""OTA progress display: concentric single-LED "rings" on the POV display.

The display renders identically at every rotation column (persistence of
vision paints a full circle), so a value can only be conveyed through which
*row* (radius) lights up, not through per-column shapes -- there is no font
or glyph renderer in this codebase, and this module doesn't add one. Instead
each kind of information gets its own ring, at its own single-LED radius,
in its own color, all shown simultaneously:

  - WiFi connecting: only the outermost LED, blue.
  - Partition writes (tier 2/3, counted in 4096-byte blocks across every
    partition that needs writing): a 50%-gray ring whose radius closes in
    from the outermost LED (0%) to the innermost (99%) as blocks are
    written, plus a 10%-yellow ring that bounces in and out by one LED
    every time a block is actually written -- a "yes, it's alive" pulse
    distinct from the calm progress ring.
  - LFS file sync (tier 1, counted in bytes across every file that needs
    downloading): the same idea in white (progress) and green (activity).

Where two rings land on the same LED, white always wins; see _Z_ORDER.

Renders through vshw_vs2 (render_vs2(), the same path every game uses) with
the background starfield explicitly turned off for the duration -- gpu.c's
render()/render_vs2() both draw it unconditionally otherwise, which is what
made an earlier attempt at this feature look like it was doing nothing at
all: the progress indicator was rendering correctly underneath, but the
ever-present, visually busy starfield buried it. vshw_vs2 is a native
module with no dependency on the vfs-resident vs2.py package (the layer/
sprite/tilemap primitives it exposes are exactly what vs2.py itself builds
on) -- see vs2_native.c -- so using it here doesn't compromise this module's
own vfs-independence requirement, below.

Frozen at the top level (not nested under ventilastation/) so it works from
vsdk_recovery.py with vfs completely empty, same as updater.py/boot.py/
vsdk_uart_log.py -- see vsdk_recovery.py's docstring for why a frozen
submodule nested under a vfs-resident package isn't reliably reachable.
"""

try:
    import vshw_povdisplay as _display
    import vshw_sprites as _sprites  # only for set_imagestrip() -- image_stripes[] is shared with vshw_vs2
    import vshw_vs2 as _vs2
    _NATIVE = True
except ImportError:
    _NATIVE = False

_VS2_FLAG_VISIBLE = 0x01

PIXELS = 54  # must match gpu.h's PIXELS -- the physical LED count per arm.

_WIDTH_BYTE = 255  # "actually 256" -- see gpu.c's `if (width == 255) width++`.
WIDTH = 256
TRANSPARENT = 0xFF
_LIT = 1

# perspective=2 in render()'s HUD mode maps strip row y directly onto LED
# (PIXELS-1-y) with sprite_y=0 -- row 0 is the outermost LED, row PIXELS-1
# the innermost (confirmed against povdisplay.c's init_buffers(): framebuffer
# index 0 is the hub-shared center LED, so PIXELS-1 is the tip).
_PERSPECTIVE_HUD = 2

# One ring per kind of information, each its own strip slot + palette group
# (palette is a per-strip property, not per-sprite -- see sprites.c). Colors
# are (blue, green, red) bytes, packed as [255, b, g, r] per palette entry --
# see _build_palette()'s wire format below.
_WIFI = "wifi"
_PARTITION_PROGRESS = "partition_progress"
_PARTITION_ACTIVITY = "partition_activity"
_FILE_PROGRESS = "file_progress"
_FILE_ACTIVITY = "file_activity"

_RING_COLOR = {
    _WIFI: (200, 60, 0),                # blue
    _PARTITION_PROGRESS: (128, 128, 128),  # 50% gray
    _PARTITION_ACTIVITY: (0, 90, 90),      # dim (~10%) yellow
    _FILE_PROGRESS: (255, 255, 255),       # white
    _FILE_ACTIVITY: (0, 200, 0),           # green
}

# Stacking order, most-visible first: when two rings land on the same LED,
# the one drawn *last* wins (render()'s sprite loop runs high id -> low id,
# and lower ids draw on top -- see gpu.c). Sprites are created in this same
# order below, so the first-created (_FILE_PROGRESS, i.e. white) gets the
# lowest sprite id and therefore always wins, per the user's requirement;
# the rest is this module's own judgment call, not separately specified.
_Z_ORDER = (_FILE_PROGRESS, _FILE_ACTIVITY, _PARTITION_ACTIVITY, _PARTITION_PROGRESS, _WIFI)

_STRIP_SLOT = {name: 20 + i for i, name in enumerate(_Z_ORDER)}  # arbitrary, just needs to not collide with another module's strip slot
_PALETTE_GROUP = {name: i for i, name in enumerate(_Z_ORDER)}

_DISPLAY_NVS_KEYS = (
    "hall_gpio", "irdiode_gpio", "led_spi_host",
    "led_clk", "led_mosi", "led_cs", "led_freq",
)

_started = False
_sprite = {}  # name -> Sprite instance
_row = {}     # name -> currently-shown row, or None if disabled


def _read_display_args():
    import esp32
    nvs = esp32.NVS("vs_board")
    return tuple(nvs.get_i32(key) for key in _DISPLAY_NVS_KEYS)


def _build_palette():
    palette = bytearray(256 * 4 * len(_Z_ORDER))
    for name in _Z_ORDER:
        b, g, r = _RING_COLOR[name]
        offset = _PALETTE_GROUP[name] * 256 * 4 + _LIT * 4
        palette[offset:offset + 4] = bytes([255, b, g, r])
    return bytes(palette)


def _build_ring_strip(name, row):
    """One WIDTH x PIXELS x 1-frame strip with `row` lit across every
    column (a full-circle ring at that radius) and everything else
    transparent, or fully blank if row is None."""
    header = bytes([_WIDTH_BYTE, PIXELS, 1, _PALETTE_GROUP[name]])
    body = bytearray(b"\xff" * (WIDTH * PIXELS))
    if row is not None:
        for col in range(WIDTH):
            body[col * PIXELS + row] = _LIT
    return header + bytes(body)


def ensure_started():
    """Idempotent: init the POV display and create the (initially disabled)
    ring sprites. Returns False without doing anything if the native
    display modules aren't linked in (desktop/emulator) or the board's
    wiring isn't provisioned yet -- best-effort, like vsdk_recovery.py's
    old _make_sprite()."""
    global _started
    if _started:
        return True
    if not _NATIVE:
        return False
    try:
        display_args = _read_display_args()
    except Exception:
        return False
    try:
        _display.init(PIXELS, *display_args)
        _display.set_gamma_mode(1)
        _display.set_starfield_enabled(False)
        _display.set_palettes(_build_palette())
        _vs2.set_active(True)
        for name in _Z_ORDER:
            sprite = _vs2.Sprite()
            sprite.set_strip(_STRIP_SLOT[name])
            sprite.set_perspective(_PERSPECTIVE_HUD)
            sprite.set_x(0)
            sprite.set_y(0)
            sprite.disable()
            _sprite[name] = sprite
            _row[name] = None
    except Exception as error:
        print("vsdk_ota_rings: display unavailable, continuing without it:", error)
        return False
    _started = True
    return True


def _set_ring(name, row):
    """row=None disables the ring; otherwise clamps into [0, PIXELS) and
    (re)builds+registers that ring's one-frame strip -- set_imagestrip()
    only stores a pointer (see sprites.c), so this is a cheap atomic swap,
    not a copy into shared, concurrently-rendered memory."""
    if not _started:
        return
    if row is not None:
        row = 0 if row < 0 else (PIXELS - 1 if row >= PIXELS else row)
    if _row.get(name) == row:
        return
    _row[name] = row
    sprite = _sprite[name]
    if row is None:
        sprite.disable()
        return
    _sprites.set_imagestrip(_STRIP_SLOT[name], _build_ring_strip(name, row))
    sprite.set_frame(0)
    sprite.set_flags(_VS2_FLAG_VISIBLE)


def _row_for_fraction(done, total):
    """0% -> row 0 (outermost), 99%+ -> row PIXELS-1 (innermost)."""
    if total <= 0:
        return 0
    fraction = done / total
    if fraction < 0:
        fraction = 0.0
    elif fraction > 1:
        fraction = 1.0
    return int(fraction * (PIXELS - 1))


def show_wifi_connecting():
    if ensure_started():
        _set_ring(_WIFI, 0)


def hide_wifi():
    _set_ring(_WIFI, None)


def set_file_progress(done_bytes, total_bytes):
    if ensure_started():
        _set_ring(_FILE_PROGRESS, _row_for_fraction(done_bytes, total_bytes))


_activity_pos = {_PARTITION_ACTIVITY: 0, _FILE_ACTIVITY: 0}
_activity_dir = {_PARTITION_ACTIVITY: 1, _FILE_ACTIVITY: 1}


def _pulse_activity(name):
    if not ensure_started():
        return
    pos = _activity_pos[name] + _activity_dir[name]
    if pos >= PIXELS - 1:
        pos = PIXELS - 1
        _activity_dir[name] = -1
    elif pos <= 0:
        pos = 0
        _activity_dir[name] = 1
    _activity_pos[name] = pos
    _set_ring(name, pos)


def pulse_file_activity():
    _pulse_activity(_FILE_ACTIVITY)


def set_partition_progress(done_blocks, total_blocks):
    if ensure_started():
        _set_ring(_PARTITION_PROGRESS, _row_for_fraction(done_blocks, total_blocks))


def pulse_partition_activity():
    _pulse_activity(_PARTITION_ACTIVITY)


def clear():
    """Hide every ring and restore the starfield for whatever runs next
    (a game, the menu, or another vs2 scene) -- deliberately doesn't touch
    vs2_render_active or the sprite registrations themselves (no
    vshw_vs2.reset_scene()), so this module's own sprites stay valid and
    reusable if another OTA/recovery attempt calls into it again in the
    same boot."""
    for name in _Z_ORDER:
        _set_ring(name, None)
    if _started:
        try:
            _display.set_starfield_enabled(True)
        except Exception:
            pass
