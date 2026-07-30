#!/usr/bin/env python3
"""Generate the shared tile strip used by the VS2 hardware acceptance scene."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "system" / "shared" / "other" / "images" / "vs2_environment.png"
FRAME_WIDTH = 32
FRAME_HEIGHT = 16
FRAME_COUNT = 16
TRANSPARENT = (255, 0, 255, 0)


def draw_ground(draw, frame):
    if frame < 2:
        base = (18, 88 + frame * 12, 152 + frame * 16, 255)
        draw.rectangle((0, 0, 31, 15), fill=base)
        for y in range(3 + frame * 2, 16, 6):
            draw.arc((1, y - 4, 13, y + 4), 0, 180, fill=(72, 154, 210, 255))
            draw.arc((14, y - 4, 29, y + 4), 0, 180, fill=(72, 154, 210, 255))
    elif frame < 4:
        draw.rectangle((0, 0, 31, 15), fill=(184, 142, 58, 255))
        for x in range((frame * 5) % 9, 32, 9):
            draw.line((x, 0, x - 6, 15), fill=(224, 188, 104, 255))
        draw.polygon(
            [(0, 0), (7, 0), (12, 8), (8, 15), (0, 15)],
            fill=(24, 104, 164, 255),
        )
    elif frame < 6:
        draw.rectangle((0, 0, 31, 15), fill=(46, 126, 60, 255))
        for x in range((frame * 4) % 8, 32, 8):
            draw.polygon(
                [(x, 15), (x + 3, 3), (x + 6, 15)],
                fill=(24, 82, 44, 255),
            )
    else:
        draw.rectangle((0, 0, 31, 15), fill=(82, 88, 94, 255))
        draw.rectangle((2, 2, 29, 13), outline=(166, 176, 184, 255))
        draw.line((4, 8, 27, 8), fill=(238, 48, 52, 255), width=2)
        if frame == 7:
            draw.rectangle((13, 3, 18, 12), fill=(238, 48, 52, 255))


def draw_object(draw, frame):
    kind = frame - 8
    if kind == 0:
        draw.polygon(
            [(5, 14), (8, 6), (15, 2), (23, 7), (27, 14)],
            fill=(64, 70, 78, 255),
            outline=(162, 172, 180, 255),
        )
    elif kind == 1:
        draw.polygon(
            [(9, 14), (13, 3), (17, 0), (22, 13)],
            fill=(44, 188, 202, 255),
            outline=(190, 246, 244, 255),
        )
        draw.polygon(
            [(18, 14), (22, 6), (25, 4), (28, 14)],
            fill=(42, 116, 198, 255),
        )
    elif kind == 2:
        draw.rectangle((13, 3, 18, 14), fill=(178, 186, 188, 255))
        draw.polygon(
            [(8, 5), (23, 5), (20, 10), (11, 10)],
            fill=(238, 48, 52, 255),
        )
        draw.rectangle((10, 11, 21, 14), fill=(60, 66, 72, 255))
    else:
        draw.ellipse((5, 1, 26, 14), fill=(54, 62, 70, 255), outline=(184, 194, 198, 255))
        draw.ellipse((10, 4, 21, 12), outline=(244, 78, 62, 255), width=2)
        draw.line((16, 2, 16, 14), fill=(244, 78, 62, 255))


def draw_cloud(draw, frame):
    variant = frame - 12
    shade = (
        (224, 234, 238, 220),
        (194, 212, 222, 210),
        (238, 226, 196, 215),
        (170, 190, 206, 205),
    )[variant]
    dx = (variant & 1) * 3
    dy = (variant >> 1) * 2
    draw.ellipse((2 + dx, 7 - dy, 16 + dx, 14 - dy), fill=shade)
    draw.ellipse((8 + dx, 3 - dy, 23 + dx, 14 - dy), fill=shade)
    draw.ellipse((16 + dx, 6 - dy, 29 + dx, 14 - dy), fill=shade)
    draw.rectangle((7 + dx, 9 - dy, 25 + dx, 14 - dy), fill=shade)


def generate():
    strip = Image.new(
        "RGBA",
        (FRAME_WIDTH * FRAME_COUNT, FRAME_HEIGHT),
        TRANSPARENT,
    )
    for frame in range(FRAME_COUNT):
        tile = Image.new("RGBA", (FRAME_WIDTH, FRAME_HEIGHT), TRANSPARENT)
        draw = ImageDraw.Draw(tile)
        if frame < 8:
            draw_ground(draw, frame)
        elif frame < 12:
            draw_object(draw, frame)
        else:
            draw_cloud(draw, frame)
        strip.alpha_composite(tile, (frame * FRAME_WIDTH, 0))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    strip.save(OUTPUT, optimize=True)


if __name__ == "__main__":
    generate()
