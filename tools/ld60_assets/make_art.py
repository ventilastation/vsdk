"""Draws the images of the five LD60 "Circular Arcade" games in games/ld60/.

    python3 tools/ld60_assets/make_art.py

Every game gets ``images/tiles.png`` (an autotiled wall set plus a few extra
tiles), ``images/sprites.png`` (8x8 frames), ``menu.png`` and a copy of the
tutorial's ``steel8x8.png`` font. Needs Pillow.

Art is drawn the way a player sees it: upright, right-facing, head toward the
top of the picture. A game whose player flies at the top of the disc (x = 128)
stores its pictures turned through 180 degrees, because the renderer draws the
top of a strip toward the centre of the disc; that is what ``TOP`` means below.
Rim Runner's player stands at the bottom of the disc, where a strip looks just
like its PNG, so it stores the pictures as drawn.
"""
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
GAMES = ROOT / "games" / "ld60"
FONT = ROOT / "games" / "demos" / "tutorial_game" / "images" / "steel8x8.png"

TILE = 8
CLEAR = (0, 0, 0, 0)

PALETTE = {
    ".": CLEAR,
    "w": (235, 240, 255, 255),
    "c": (40, 220, 235, 255),
    "C": (20, 120, 150, 255),
    "y": (255, 220, 60, 255),
    "o": (255, 140, 30, 255),
    "r": (235, 50, 50, 255),
    "R": (140, 30, 40, 255),
    "g": (70, 220, 90, 255),
    "G": (30, 120, 60, 255),
    "b": (70, 110, 255, 255),
    "B": (30, 50, 150, 255),
    "m": (230, 70, 220, 255),
    "p": (150, 80, 220, 255),
    "k": (150, 160, 185, 255),
    "d": (60, 66, 84, 255),
    "n": (170, 110, 60, 255),
    "N": (100, 60, 30, 255),
}


def sprite(rows):
    """An 8x8 RGBA image from eight strings of eight palette letters."""
    assert len(rows) == TILE and all(len(row) == TILE for row in rows), rows
    image = Image.new("RGBA", (TILE, TILE), CLEAR)
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            image.putpixel((x, y), PALETTE[char])
    return image


def strip(frames, top):
    """A filmstrip of equally sized frames; turned 180 degrees if ``top``."""
    out = Image.new("RGBA", (TILE * len(frames), TILE), CLEAR)
    for index, frame in enumerate(frames):
        if top:
            frame = frame.rotate(180)
        out.paste(frame, (index * TILE, 0))
    return out


def wall_tiles(top, fill, speck, edge, glow=None):
    """Sixteen wall tiles, one per combination of open neighbours.

    Frame bit 0 is an open cell on the +x side, bit 1 on the -x side, bit 2 on
    the +y (toward the centre) side and bit 3 on the -y (toward the rim) side.
    Where a side is open the tile gets a bright edge line facing it. The lines
    are drawn upright and turned with the rest of the strip.
    """
    # Which edge of the upright picture each map direction is. Seen from the top
    # of the disc +x is to the right and +y is down; seen from the bottom both
    # are reversed.
    if top:
        sides = ((7, None), (0, None), (None, 7), (None, 0))
    else:
        sides = ((0, None), (7, None), (None, 0), (None, 7))
    frames = []
    for mask in range(16):
        image = Image.new("RGBA", (TILE, TILE), fill + (255,))
        draw = ImageDraw.Draw(image)
        for y in range(TILE):
            for x in range(TILE):
                if (x * 3 + y * 5) % 7 == 0:
                    image.putpixel((x, y), speck + (255,))
        for bit, (col, row) in enumerate(sides):
            if not mask & (1 << bit):
                continue
            if glow:
                shade = glow + (255,)
                if col is not None:
                    inner = 1 if col == 0 else 6
                    draw.line((inner, 0, inner, 7), fill=shade)
                else:
                    inner = 1 if row == 0 else 6
                    draw.line((0, inner, 7, inner), fill=shade)
            if col is not None:
                draw.line((col, 0, col, 7), fill=edge + (255,))
            else:
                draw.line((0, row, 7, row), fill=edge + (255,))
        frames.append(image)
    return frames


def blank():
    return Image.new("RGBA", (TILE, TILE), CLEAR)


# --- Spiral Tunnel ---------------------------------------------------------

TUNNEL_SPRITES = [
    sprite([  # 0 ship
        "........",
        "..d.....",
        ".ddkc...",
        "dkwwwcc.",
        "dkwwwcc.",
        ".ddkc...",
        "..d.....",
        "........",
    ]),
    sprite([  # 1 ufo
        "........",
        "...cc...",
        "..cwwc..",
        ".mmmmmm.",
        "mwmwmwmw",
        ".kkkkkk.",
        "..y..y..",
        "........",
    ]),
    sprite([  # 2 ufo
        "........",
        "...cc...",
        "..cwwc..",
        ".mmmmmm.",
        "mmwmwmwm",
        ".kkkkkk.",
        "...yy...",
        "........",
    ]),
    sprite([  # 3 ufo
        "........",
        "...cc...",
        "..cwwc..",
        ".mmmmmm.",
        "wmmwmwmm",
        ".kkkkkk.",
        ".y....y.",
        "........",
    ]),
    sprite([  # 4 bomb
        "........",
        "........",
        "...oo...",
        "..oyyo..",
        "..oyyo..",
        "...oo...",
        "........",
        "........",
    ]),
]

# Explosion frames, shared by every game.
BOOM = [
    sprite([
        "........",
        "........",
        "........",
        "...yy...",
        "...yy...",
        "........",
        "........",
        "........",
    ]),
    sprite([
        "........",
        "..o..o..",
        "...yy...",
        ".oywwyo.",
        ".oywwyo.",
        "...yy...",
        "..o..o..",
        "........",
    ]),
    sprite([
        ".r....r.",
        "..o..o..",
        "r..yy..r",
        "..y..y..",
        "..y..y..",
        "r..yy..r",
        "..o..o..",
        ".r....r.",
    ]),
]


def make_spiral_tunnel():
    top = True
    out = GAMES / "spiral_tunnel" / "images"
    walls = wall_tiles(top, (8, 14, 34), (14, 24, 56), (40, 200, 235), (16, 80, 110))
    strip(walls, top).save(out / "tiles.png")
    strip(TUNNEL_SPRITES + BOOM, top).save(out / "sprites.png")


# --- Dodge 'Em ---------------------------------------------------------------

DODGEM_SPRITES = [
    sprite([  # 0 player car
        "........",
        "........",
        ".ccccc..",
        "cwcccwc.",
        "ccccccc.",
        ".k...k..",
        "........",
        "........",
    ]),
    sprite([  # 1 player car, wheels turning
        "........",
        "........",
        ".ccccc..",
        "cwcccwc.",
        "ccccccc.",
        "..k.k...",
        "........",
        "........",
    ]),
    sprite([  # 2 enemy car
        "........",
        "........",
        "..rrrrr.",
        ".crrrcr.",
        ".rrrrrrr",
        "..k...k.",
        "........",
        "........",
    ]),
    sprite([  # 3 enemy car, wheels turning
        "........",
        "........",
        "..rrrrr.",
        ".crrrcr.",
        ".rrrrrrr",
        "...k.k..",
        "........",
        "........",
    ]),
] + BOOM

PILL = sprite([
    "........",
    "........",
    "........",
    "...yy...",
    "...yy...",
    "........",
    "........",
    "........",
])


def make_dodge_em():
    top = True
    out = GAMES / "dodge_em" / "images"
    # Solid walls with a bright edge line, so wall and track are easy to tell apart.
    walls = wall_tiles(top, (96, 30, 110), (96, 30, 110), (255, 130, 255))
    strip(walls + [PILL], top).save(out / "tiles.png")
    strip(DODGEM_SPRITES, top).save(out / "sprites.png")


# --- Catch the Robots -----------------------------------------------------

ROBOT_SPRITES = [
    sprite([  # 0 player
        "...yy...",
        "..yyyy..",
        "..wcwc..",
        "...cc...",
        "..cccc..",
        ".c.cc.c.",
        "...cc...",
        "..c..c..",
    ]),
    sprite([  # 1 player, mid-stride
        "...yy...",
        "..yyyy..",
        "..wcwc..",
        "...cc...",
        "..cccc..",
        "c..cc..c",
        "...cc...",
        "...cc...",
    ]),
    sprite([  # 2 robot
        "...g....",
        "..kkkk..",
        ".kgkkgk.",
        ".kkkkkk.",
        "..kddk..",
        ".kkkkkk.",
        "..k..k..",
        ".kk..kk.",
    ]),
    sprite([  # 3 robot, mid-stride
        "....g...",
        "..kkkk..",
        ".kgkkgk.",
        ".kkkkkk.",
        "..kddk..",
        ".kkkkkk.",
        "..k..k..",
        "..kk.kk.",
    ]),
] + BOOM


def make_catch_the_robots():
    top = True
    out = GAMES / "catch_the_robots" / "images"
    # Solid, fairly bright walls (no speckle) against black passages, so it is
    # obvious which is which.
    walls = wall_tiles(top, (24, 110, 48), (24, 110, 48), (150, 255, 170))
    strip(walls, top).save(out / "tiles.png")
    strip(ROBOT_SPRITES, top).save(out / "sprites.png")


# --- Rim Runner ---------------------------------------------------------------

EGG = sprite([
    "........",
    "........",
    "...ww...",
    "..wwww..",
    "..wywy..",
    "..wwww..",
    "...ww...",
    "........",
])

RIM_SPRITES = [
    sprite([  # 0 runner
        "..yyy...",
        "..ywy...",
        "..yyy...",
        ".bbbbb..",
        "b.bbb.b.",
        "..bbb...",
        "..b.b...",
        ".bb.bb..",
    ]),
    sprite([  # 1 runner, mid-stride
        "..yyy...",
        "..ywy...",
        "..yyy...",
        ".bbbbb..",
        "b.bbb.b.",
        "..bbb...",
        "...b....",
        "...bb...",
    ]),
    sprite([  # 2 runner, jumping
        "b.yyy.b.",
        "b.ywy.b.",
        "bbyyybb.",
        ".bbbbb..",
        "..bbb...",
        "..b.b...",
        ".b...b..",
        "........",
    ]),
    sprite([  # 3 bird, wings up
        "p......p",
        "pp....pp",
        ".pp..pp.",
        "..pppp..",
        "...pwo..",
        "...pp...",
        "........",
        "........",
    ]),
    sprite([  # 4 bird, wings down
        "........",
        "........",
        "..pppp..",
        "pppwopp.",
        "pp.pp.pp",
        "p..pp..p",
        "........",
        "........",
    ]),
] + BOOM


def make_rim_runner():
    top = False
    out = GAMES / "rim_runner" / "images"
    walls = wall_tiles(top, (30, 18, 10), (44, 28, 16), (230, 150, 50), (110, 60, 20))
    strip(walls + [EGG], top).save(out / "tiles.png")
    strip(RIM_SPRITES, top).save(out / "sprites.png")


# --- Defender -------------------------------------------------------------------

DEFENDER_SPRITES = [
    sprite([  # 0 ship
        "........",
        "kk......",
        ".kkkk...",
        "ykwwwcc.",
        ".kkkk...",
        "kk......",
        "........",
        "........",
    ]),
    sprite([  # 1 ship, thrusting
        "........",
        "kk......",
        ".kkkk...",
        "yowwwcc.",
        ".kkkk...",
        "kk......",
        "........",
        "........",
    ]),
    sprite([  # 2 enemy
        "........",
        "..mmmm..",
        ".mmmmmm.",
        "mmwmmwmm",
        "mmmmmmmm",
        ".m.mm.m.",
        "m..mm..m",
        "........",
    ]),
    sprite([  # 3 enemy, tentacles in
        "........",
        "..mmmm..",
        ".mmmmmm.",
        "mmwmmwmm",
        "mmmmmmmm",
        "..mmmm..",
        ".m.mm.m.",
        "........",
    ]),
    sprite([  # 4 player bullet
        "........",
        "........",
        "........",
        ".yyyyyw.",
        "........",
        "........",
        "........",
        "........",
    ]),
    sprite([  # 5 enemy bullet
        "........",
        "........",
        "...rr...",
        "..rwwr..",
        "..rwwr..",
        "...rr...",
        "........",
        "........",
    ]),
] + BOOM


def make_defender():
    top = True
    out = GAMES / "defender" / "images"
    walls = wall_tiles(top, (30, 14, 12), (44, 22, 18), (230, 90, 60), (110, 40, 30))
    strip(walls, top).save(out / "tiles.png")
    strip(DEFENDER_SPRITES, top).save(out / "sprites.png")


# --- Menu icons (64 x 30) ------------------------------------------------------

def icon(name, draw_scene):
    image = Image.new("RGB", (64, 30), (0, 0, 0))
    draw_scene(ImageDraw.Draw(image))
    image.save(GAMES / name / "menu.png")


def icon_spiral_tunnel(d):
    for i, radius in enumerate(range(26, 4, -3)):
        shade = (20 + i * 10, 90 + i * 12, 130 + i * 10)
        d.ellipse((32 - radius * 1.2, 15 - radius * 0.55 + i, 32 + radius * 1.2,
                   15 + radius * 0.55 + i), outline=shade)
    d.polygon(((6, 24), (16, 21), (6, 18)), fill=(235, 240, 255))
    d.ellipse((40, 12, 46, 16), fill=(230, 70, 220))


def icon_dodge_em(d):
    for i, radius in enumerate((26, 20, 14, 8)):
        d.ellipse((32 - radius * 1.2, 15 - radius * 0.55, 32 + radius * 1.2,
                   15 + radius * 0.55), outline=(110, 40, 130))
    for angle_x in range(8, 58, 4):
        d.point((angle_x, 15 + 9 - abs(angle_x - 32) // 5), fill=(255, 220, 60))
    d.rectangle((28, 22, 36, 26), fill=(40, 220, 235))
    d.rectangle((14, 5, 20, 8), fill=(235, 50, 50))


def icon_catch_the_robots(d):
    for x in range(0, 64, 8):
        d.line((x, 0, x, 29), fill=(20, 70, 36))
    for y in range(2, 30, 8):
        d.line((0, y, 63, y), fill=(20, 70, 36))
    for x, y in ((12, 6), (40, 14), (52, 22), (22, 22)):
        d.rectangle((x, y, x + 5, y + 5), fill=(110, 120, 140))
        d.point((x + 1, y + 1), fill=(70, 220, 90))
        d.point((x + 4, y + 1), fill=(70, 220, 90))
    d.rectangle((30, 6, 35, 11), fill=(255, 220, 60))


def icon_rim_runner(d):
    d.ellipse((-20, 12, 84, 70), outline=(230, 150, 50))
    d.ellipse((-18, 14, 82, 68), outline=(110, 60, 20))
    d.rectangle((29, 6, 34, 12), fill=(70, 110, 255))
    d.rectangle((29, 3, 34, 4), fill=(255, 220, 60))
    d.polygon(((12, 14), (18, 8), (24, 14)), fill=(150, 80, 220))
    d.ellipse((46, 9, 50, 14), fill=(235, 240, 255))


def icon_defender(d):
    d.polygon(((0, 29), (0, 22), (8, 16), (14, 21), (22, 12), (30, 20), (40, 14),
               (50, 22), (58, 17), (63, 22), (63, 29)), fill=(110, 40, 30))
    d.line((0, 22, 8, 16, 14, 21, 22, 12, 30, 20, 40, 14, 50, 22, 58, 17, 63, 22),
           fill=(230, 90, 60))
    d.polygon(((14, 6), (24, 8), (14, 10)), fill=(235, 240, 255))
    d.rectangle((40, 4, 47, 8), fill=(230, 70, 220))
    d.rectangle((48, 5, 54, 5), fill=(235, 50, 50))


GAME_NAMES = ("spiral_tunnel", "catch_the_robots", "rim_runner", "dodge_em", "defender")


def main():
    for name in GAME_NAMES:
        (GAMES / name / "images").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FONT, GAMES / name / "images" / "steel8x8.png")
    make_spiral_tunnel()
    make_catch_the_robots()
    make_rim_runner()
    make_dodge_em()
    make_defender()
    icon("spiral_tunnel", icon_spiral_tunnel)
    icon("catch_the_robots", icon_catch_the_robots)
    icon("rim_runner", icon_rim_runner)
    icon("dodge_em", icon_dodge_em)
    icon("defender", icon_defender)
    print("wrote art for", ", ".join(GAME_NAMES))


if __name__ == "__main__":
    main()
