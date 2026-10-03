"""Draws games/demos/tutorial_game/images/ship.png: the tutorial game's ship.

    python3 make_ship_art.py

Three 18x18 frames of an arrowhead ship, nose toward the centre of the disc:
frame 0 flies level, frame 1 leans into a turn to the left and frame 2 into a
turn to the right. The game picks the frame from the steering.

"Left" is the direction x counts down in. The renderer draws a sprite's image
mirrored in X (hardware/rotor/modules/povdisplay/gpu.c), so a ship that moves
to the left (x - 1) moves toward the right edge of its own image, and the left
turn is the frame whose nose points to the image's right.

The shapes are drawn with Pillow at 4x size, then reduced and thresholded, which
keeps the edges crisp. Needs Pillow.
"""
from math import cos, radians, sin
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 18
SCALE = 4                      # drawing resolution, per output pixel
CENTRE = (SIZE - 1) / 2
TURN = 24                      # degrees a banked frame is turned
FRAMES = (0, TURN, -TURN)      # level, left (nose to the image's right), right

HULL = (118, 128, 148)
EDGE = (214, 224, 240)
DARK = (70, 78, 96)
CANOPY = (90, 215, 245)
CANOPY_HOT = (210, 250, 255)
FLAME = (255, 140, 30)
FLAME_HOT = (255, 225, 120)

# Shapes with the nose up, around the origin, y growing downward as in an image.
HULL_SHAPE = ((0, -7.5), (5.5, 6.5), (0, 3.5), (-5.5, 6.5))
CORE_SHAPE = ((0, -6), (3.2, 5.6), (0, 3.2), (-3.2, 5.6))
CANOPY_SHAPE = tuple((1.5 * cos(radians(a)), -0.5 + 2.3 * sin(radians(a)))
                     for a in range(0, 360, 30))
CANOPY_GLINT = tuple((1.1 * cos(radians(a)), -1.4 + 1.1 * sin(radians(a)))
                     for a in range(0, 360, 45))
FLAME_SHAPE = ((-1.5, 3.6), (1.5, 3.6), (1.5, 6.4), (-1.5, 6.4))
FLAME_CORE = ((-1.5, 3.6), (1.5, 3.6), (1.5, 4.8), (-1.5, 4.8))


def mask(shape, angle):
    """A SIZE x SIZE bit mask of ``shape`` turned by ``angle`` degrees."""
    a = radians(angle)
    points = [((CENTRE + x * cos(a) - y * sin(a) + 0.5) * SCALE,
               (CENTRE + x * sin(a) + y * cos(a) + 0.5) * SCALE) for x, y in shape]
    big = Image.new("L", (SIZE * SCALE, SIZE * SCALE), 0)
    ImageDraw.Draw(big).polygon(points, fill=255)
    small = big.resize((SIZE, SIZE), Image.BOX)
    return {(x, y) for y in range(SIZE) for x in range(SIZE) if small.getpixel((x, y)) >= 128}


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
