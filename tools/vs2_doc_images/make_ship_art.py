"""Draws games/demos/tutorial_game/images/ship.png: the tutorial game's ship.

    python3 make_ship_art.py

Three 19x19 frames of an arrowhead ship, nose toward the centre of the disc:
frame 0 flies level, frame 1 leans into a turn to the left and frame 2 into a
turn to the right. The game picks the frame from the steering.

The width is odd on purpose: the level ship is exactly symmetric and ends in a
single-pixel point, which needs a centre column. At the bottom of the disc, where
the ship flies, a sprite looks just like its PNG, so the left-turn frame is the one
whose nose points to the image's left.

Each shape is a polygon, sampled four times per pixel in each direction and kept
where half or more of the pixel is covered, which keeps the edges crisp and the
level frame exactly symmetric. Needs Pillow, to write the PNG.
"""
from math import cos, radians, sin
from pathlib import Path

from PIL import Image

SIZE = 19
SCALE = 4                      # drawing resolution, per output pixel
CENTRE = (SIZE - 1) / 2
TURN = 24                      # degrees a banked frame is turned
FRAMES = (0, -TURN, TURN)      # level, left (nose to the image's left), right

HULL = (118, 128, 148)
EDGE = (214, 224, 240)
DARK = (70, 78, 96)
CANOPY = (90, 215, 245)
CANOPY_HOT = (210, 250, 255)
FLAME = (255, 140, 30)
FLAME_HOT = (255, 225, 120)

# Shapes with the nose up, around the origin, y growing downward as in an image.
HULL_SHAPE = ((0, -7.8), (6.0, 6.5), (0, 3.5), (-6.0, 6.5))
CORE_SHAPE = ((0, -6), (3.2, 5.6), (0, 3.2), (-3.2, 5.6))
CANOPY_SHAPE = tuple((1.5 * cos(radians(a)), -0.5 + 2.3 * sin(radians(a)))
                     for a in range(0, 360, 30))
CANOPY_GLINT = tuple((1.1 * cos(radians(a)), -1.4 + 1.1 * sin(radians(a)))
                     for a in range(0, 360, 45))
FLAME_SHAPE = ((-1.5, 3.6), (1.5, 3.6), (1.5, 6.4), (-1.5, 6.4))
FLAME_CORE = ((-1.5, 3.6), (1.5, 3.6), (1.5, 4.8), (-1.5, 4.8))


def inside(px, py, points):
    """Whether (px, py) is inside the polygon ``points`` (even-odd rule)."""
    hit = False
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def mask(shape, angle):
    """The pixels of a SIZE x SIZE image that ``shape``, turned by ``angle``
    degrees, covers by half or more.

    Coverage is counted on a SCALE x SCALE grid of sample points per pixel with
    an exact point-in-polygon test. ImageDraw.polygon would be shorter, but it
    also fills the outline on the right and bottom, and that makes a symmetric
    shape come out lopsided.
    """
    a = radians(angle)
    points = [(CENTRE + 0.5 + x * cos(a) - y * sin(a),
               CENTRE + 0.5 + x * sin(a) + y * cos(a)) for x, y in shape]
    covered = set()
    for y in range(SIZE):
        for x in range(SIZE):
            samples = sum(inside(x + (i + 0.5) / SCALE, y + (j + 0.5) / SCALE, points)
                          for i in range(SCALE) for j in range(SCALE))
            if samples * 2 >= SCALE * SCALE:
                covered.add((x, y))
    return covered


def frame(angle):
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    px = img.load()
    solid = mask(HULL_SHAPE, angle)
    core = mask(CORE_SHAPE, angle)
    canopy = mask(CANOPY_SHAPE, angle)
    glint = mask(CANOPY_GLINT, angle)
    flame = mask(FLAME_SHAPE, angle)
    flame_core = mask(FLAME_CORE, angle)
    for x, y in solid:
        edge = any((x + dx, y + dy) not in solid
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        if (x, y) in canopy:
            colour = CANOPY_HOT if (x, y) in glint else CANOPY
        elif (x, y) in flame:
            colour = FLAME_HOT if (x, y) in flame_core else FLAME
        elif edge:
            colour = EDGE
        else:
            colour = HULL if (x, y) in core else DARK
        px[x, y] = colour + (255,)
    return img


def main():
    strip = Image.new("RGBA", (SIZE * len(FRAMES), SIZE), (0, 0, 0, 0))
    for index, angle in enumerate(FRAMES):
        strip.paste(frame(angle), (index * SIZE, 0))
    out = Path(__file__).resolve().parents[2] / "games/demos/tutorial_game/images/ship.png"
    strip.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
