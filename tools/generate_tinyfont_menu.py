#!/usr/bin/env python3
"""Pack white and red tiny-font ASCII glyphs into one 255-frame strip.

Frames 0..127 use ``tinyfont_white.png``.  Frames 128..254 use the matching
glyphs from ``tinyfont_red.png`` (source frames 0..126).  Printable ASCII
therefore has a white frame ``ord(char)`` and a red frame ``ord(char) | 0x80``
without exceeding the ROM format's unsigned-byte frame limit.
"""

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "system" / "shared" / "other" / "images"
WHITE = IMAGES / "tinyfont_white.png"
RED = IMAGES / "tinyfont_red.png"
OUTPUT = IMAGES / "tinyfont_menu.png"
GLYPH_WIDTH = 4
GLYPH_HEIGHT = 6
WHITE_FRAMES = 128
RED_FRAMES = 127


def main():
    white = Image.open(WHITE).convert("RGBA")
    red = Image.open(RED).convert("RGBA")
    expected = (GLYPH_WIDTH * 256, GLYPH_HEIGHT)
    if white.size != expected or red.size != expected:
        raise ValueError("tiny font source strips must be %s" % (expected,))

    packed = Image.new(
        "RGBA", (GLYPH_WIDTH * (WHITE_FRAMES + RED_FRAMES), GLYPH_HEIGHT)
    )
    packed.alpha_composite(white.crop((0, 0, GLYPH_WIDTH * WHITE_FRAMES, GLYPH_HEIGHT)))
    packed.alpha_composite(
        red.crop((0, 0, GLYPH_WIDTH * RED_FRAMES, GLYPH_HEIGHT)),
        (GLYPH_WIDTH * WHITE_FRAMES, 0),
    )
    packed.save(OUTPUT)


if __name__ == "__main__":
    main()
