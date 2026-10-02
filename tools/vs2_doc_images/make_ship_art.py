"""Draws games/demos/tutorial_game/images/ship.png: the tutorial game's ship.

    python3 make_ship_art.py

Three 18x18 frames of an arrowhead ship, nose toward the centre of the disc:
frame 0 flies level, frame 1 is turned toward the sprite's left and frame 2
toward its right. The game picks the frame from the steering, so the ship leans
into a turn. Needs Pillow.
"""
from math import cos, radians, sin
from pathlib import Path

from PIL import Image

SIZE = 18
CENTRE = (SIZE - 1) / 2
TURN = 24                      # degrees a banked frame is turned
FRAMES = (0, -TURN, TURN)      # level, toward the left, toward the right

HULL = (118, 128, 148)
EDGE = (214, 224, 240)
DARK = (70, 78, 96)
CANOPY = (90, 215, 245)
CANOPY_HOT = (210, 250, 255)
FLAME = (255, 140, 30)
FLAME_HOT = (255, 225, 120)

# The ship with its nose up, around the origin; y grows downward as in an image.
HULL_SHAPE = ((0, -7.5), (5.5, 6.5), (0, 3.5), (-5.5, 6.5))


def inside(polygon, x, y):
    """Even-odd point-in-polygon test."""
    result = False
    for i, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(i + 1) % len(polygon)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            result = not result
    return result


def to_local(px, py, angle):
    """Where image pixel (px, py) lies in the ship's own, unturned frame."""
    dx, dy = px - CENTRE, py - CENTRE
    a = radians(angle)
    return dx * cos(a) + dy * sin(a), -dx * sin(a) + dy * cos(a)


def frame(angle):
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    px = img.load()
    solid = set()
    for y in range(SIZE):
        for x in range(SIZE):
            hits = sum(
                inside(HULL_SHAPE, *to_local(x + sx, y + sy, angle))
                for sx in (0.17, 0.5, 0.83) for sy in (0.17, 0.5, 0.83))
            if hits >= 5:
                solid.add((x, y))
    for x, y in solid:
        lx, ly = to_local(x + 0.5, y + 0.5, angle)
        edge = any((x + dx, y + dy) not in solid
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        if (lx / 1.5) ** 2 + ((ly + 0.5) / 2.3) ** 2 <= 1:
            colour = CANOPY_HOT if ly < 0 else CANOPY
        elif abs(lx) < 1.6 and ly > 3.6:
            colour = FLAME_HOT if ly < 5 else FLAME
        elif edge:
            colour = EDGE
        else:
            colour = HULL if abs(lx) < 3.2 else DARK
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
