"""Draws games/demos/tutorial_game/images/trench.png: the tutorial game's tileset.

    python3 make_trench_tiles.py

Eight 16x16 tiles of dark hull plating for a derelict space station's trench.
The plating is near-black so a tilemap that covers the whole tunnel still reads
as a dark background; the colour is in a few lit structures (windows, vents,
conduits, hazard stripes, status lights). Needs Pillow.

Tile numbers, in strip order: PLATE, SEAM, PIPE, WINDOWS, VENT, HAZARD, LIGHTS,
CONDUIT. They are named in the game's code.
"""
from pathlib import Path

from PIL import Image

T = 16
BASE = (13, 16, 24)
EDGE = (22, 27, 40)
RIVET = (40, 48, 68)
SCUFF = (30, 36, 52)
STEEL = (38, 46, 64)
STEEL_HI = (70, 82, 110)
STEEL_LO = (24, 29, 42)
AMBER = (255, 176, 32)
AMBER_DIM = (130, 84, 14)
CYAN = (30, 215, 235)
CYAN_DIM = (10, 72, 84)
ORANGE = (255, 112, 20)
ORANGE_DIM = (96, 36, 10)
RED = (235, 50, 50)
GREEN = (50, 225, 115)
BLUE = (70, 130, 255)
YELLOW = (205, 160, 20)
SOOT = (12, 12, 14)


def tile():
    """A plate: base colour with seams on the right and bottom edges, so
    neighbouring tiles join into panels."""
    img = Image.new("RGB", (T, T), BASE)
    px = img.load()
    for i in range(T):
        px[T - 1, i] = EDGE
        px[i, T - 1] = EDGE
    return img, px


def rivets(px):
    for x, y in ((3, 3), (12, 3), (3, 12), (12, 12)):
        px[x, y] = RIVET


def plate():
    img, px = tile()
    rivets(px)
    return img


def seam():
    img, px = tile()
    for y in range(T):
        px[8, y] = EDGE
    for x, y in ((3, 4), (4, 4), (11, 10), (12, 10), (5, 12)):
        px[x, y] = SCUFF
    return img


def pipe():
    img, px = tile()
    for y in range(5, 11):
        for x in range(T - 1):
            px[x, y] = STEEL
    for x in range(T - 1):
        px[x, 5] = STEEL_HI
        px[x, 6] = STEEL_HI if x % 2 else STEEL
        px[x, 10] = STEEL_LO
    for x in (2, 3, 12, 13):                      # brackets
        for y in range(3, 13):
            px[x, y] = RIVET if y not in range(5, 11) else STEEL_LO
    return img


def windows():
    img, px = tile()
    for x0, colour, dim in ((2, AMBER, AMBER_DIM), (7, AMBER, AMBER_DIM), (12, CYAN, CYAN_DIM)):
        for y in range(5, 10):
            for x in range(x0, x0 + 2 + (x0 != 12)):
                if x < T - 1:
                    px[x, y] = colour if y < 8 else dim
    return img


def vent():
    img, px = tile()
    for y in range(3, 13):
        for x in range(3, 13):
            px[x, y] = STEEL_LO
    for x in range(3, 13):
        px[x, 3] = px[x, 12] = STEEL
    for y in (5, 7, 9, 11):
        for x in range(4, 12):
            px[x, y] = ORANGE
            px[x, y + 1] = ORANGE_DIM if y < 11 else STEEL_LO
    return img


def hazard():
    img, px = tile()
    for y in range(4, 12):
        for x in range(T - 1):
            px[x, y] = YELLOW if ((x + y) // 3) % 2 == 0 else SOOT
    for x in range(T - 1):
        px[x, 3] = px[x, 12] = STEEL_LO
    return img


def lights():
    img, px = tile()
    for y in range(4, 12):
        for x in range(2, 14):
            px[x, y] = STEEL_LO
    for x, colour in ((4, RED), (6, GREEN), (8, BLUE), (10, AMBER), (12, GREEN)):
        px[x, 6] = colour
        px[x, 9] = tuple(c // 3 for c in colour)
    return img


def conduit():
    img, px = tile()
    for x in range(T - 1):
        px[x, 6] = px[x, 9] = CYAN_DIM
        px[x, 7] = px[x, 8] = CYAN
    for y in range(5, 11):
        px[7, y] = px[8, y] = STEEL_HI              # junction
    px[7, 7] = px[8, 8] = (200, 245, 250)
    return img


TILES = (plate, seam, pipe, windows, vent, hazard, lights, conduit)


def main():
    strip = Image.new("RGB", (T * len(TILES), T))
    for i, draw in enumerate(TILES):
        strip.paste(draw(), (i * T, 0))
    out = Path(__file__).resolve().parents[2] / "games/demos/tutorial_game/images/trench.png"
    strip.save(out)
    print("wrote", out)


main()
