"""Draws art/clouds.png: a mostly transparent FULLSCREEN layer with a few
pixel-art cloud banks, so the layers example can put "clouds" over the world.

    python3 make_clouds.py

Needs Pillow. The picture is square; the ROM builder maps it onto the disc, so
distance from the middle of the picture becomes distance from the centre of the
display and angle around it becomes X.
"""
from math import cos, pi, sin

from PIL import Image, ImageDraw

SIZE = 256
LIGHT = (232, 240, 252, 255)
SHADE = (150, 170, 200, 255)

# (angle in degrees, distance from the middle as a fraction, puff radii in px)
BANKS = [
    (20, 0.72, (14, 10, 12)),
    (95, 0.55, (12, 9, 10)),
    (160, 0.78, (16, 11, 13)),
    (230, 0.60, (13, 10, 11)),
    (300, 0.74, (15, 11, 12)),
]


def bank(draw, cx, cy, radii):
    offsets = [(-14, 3), (0, -4), (15, 3), (-4, 8), (8, 9)]
    for (dx, dy), r in zip(offsets, radii * 2):
        box = (cx + dx - r, cy + dy - r // 2, cx + dx + r, cy + dy + r // 2)
        draw.ellipse(box, fill=SHADE)
    for (dx, dy), r in zip(offsets, radii * 2):
        box = (cx + dx - r, cy + dy - r // 2 - 3, cx + dx + r, cy + dy + r // 2 - 3)
        draw.ellipse(box, fill=LIGHT)


def main():
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    middle = SIZE / 2
    for angle, dist, radii in BANKS:
        a = angle * pi / 180
        bank(draw, int(middle + dist * middle * cos(a)),
             int(middle + dist * middle * sin(a)), radii)
    image.save(__file__.replace("make_clouds.py", "art/clouds.png"))


main()
