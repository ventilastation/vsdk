"""Recovery status ring: a single frozen image strip, no ROM/vfs dependency.

Recovery must be able to show something on the LED ring before the vfs
filesystem has any content at all (a fresh board's first boot only has
`factory` + NVS). Sprites normally load their pixel data from a ROM file on
vfs (`Scene.stripes_rom` -> `director.load_rom()`); this module instead
builds one small ImageStrip directly as Python objects, held alive for the
process lifetime by this module's own globals, and wires it in with the
native `vshw_sprites.set_imagestrip()` / `vshw_povdisplay.set_palettes()`
calls directly -- the same two primitives `director._parse_rom_memory()`
uses per strip, just skipping the "parse it out of a ROM file" step. This
module has no dependency on the `ventilastation` package or `vs2`, since it
must keep working even when vfs has neither (see vsdk_recovery.py).

Each recovery lifecycle phase gets a solid-color frame on a full-circle,
fixed-width band. There's no animation loop: recovery sets `sprite.frame`
once per phase transition, and the hardware GPU task keeps spinning
whatever was last set independently of Python (see vsdk_recovery.py).
"""

# 256 columns (the on-disk/in-memory attribute byte can't hold 256, so the
# strip format reserves 255 as "actually 256" -- see gpu.c's `if (width ==
# 255) width++`).
_WIDTH_BYTE = 255
WIDTH = 256
HEIGHT = 12
PALETTE_GROUP = 0

FRAME_BOOT = 0          # dim blue: recovery is starting up
FRAME_WIFI = 1          # blue: connecting to WiFi
FRAME_DOWNLOADING = 2   # green: fetching an update over HTTP
FRAME_CHECKING = 3      # yellow: scanning or validating SHA256 checksums
FRAME_WRITING = 4       # red: erasing or writing a flash partition
FRAME_ERROR = 5         # amber: a step failed, about to retry
FRAME_SUCCESS = 6       # bright green: update verified, about to reboot
TOTAL_FRAMES = 7

# Palette entries, (255, blue, green, red) per entry -- matches the BGRA-ish
# layout `director._parse_rom_memory()`/the ROM tooling already use.
_COLOR_BY_FRAME = {
    FRAME_BOOT: (60, 0, 0),
    FRAME_WIFI: (200, 60, 0),
    FRAME_DOWNLOADING: (0, 160, 0),
    FRAME_CHECKING: (0, 200, 200),
    FRAME_WRITING: (0, 0, 200),
    FRAME_ERROR: (0, 140, 200),
    FRAME_SUCCESS: (40, 220, 40),
}


def _build_palette():
    palette = bytearray(256 * 4)
    for frame, (b, g, r) in _COLOR_BY_FRAME.items():
        offset = frame * 4
        palette[offset:offset + 4] = bytes([255, b, g, r])
    return bytes(palette)


def _build_strip():
    header = bytes([_WIDTH_BYTE, HEIGHT, TOTAL_FRAMES, PALETTE_GROUP])
    data = bytearray(WIDTH * HEIGHT * TOTAL_FRAMES)
    frame_size = WIDTH * HEIGHT
    for frame in range(TOTAL_FRAMES):
        # Same palette index in every column/row of a frame: a solid,
        # full-circle color band. Frame N's color lives at palette index N.
        start = frame * frame_size
        for i in range(frame_size):
            data[start + i] = frame
    return header + bytes(data)


PALETTE = _build_palette()
STRIP = _build_strip()


def install(display, sprites, strip_number=0):
    """Wire this strip/palette into the native display/sprites modules
    (vshw_povdisplay / vshw_sprites on hardware) and return the strip number.
    """
    display.set_palettes(PALETTE)
    sprites.set_imagestrip(strip_number, STRIP)
    return strip_number
