"""Draws the images of the five LD60 "Circular Arcade" games in games/ld60/.

    python3 tools/ld60_assets/make_art.py

Every game gets ``images/tiles.png`` (an autotiled wall set plus a few extra
tiles; Catch the Robots draws its wall outlines from ``images/outlines.png``
over a plain fill), ``images/sprites.png`` (8x8 frames) and copies of four
fonts: the tutorial's ``steel8x8.png`` for the in-game text, and from the
system ``rainbow8x8.png`` for the headings of the title and end screens and the
4x6 ``tinyfont_white.png`` and ``tinyfont_red.png`` for the lines below them.
Each ``menu.png`` is a moment of play drawn with these, so run
capture_menu_icons.py after this. Needs Pillow.

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
FONTS = (
    ROOT / "games" / "demos" / "tutorial_game" / "images" / "steel8x8.png",
    ROOT / "system" / "shared" / "other" / "images" / "8x8fonts" / "rainbow8x8.png",
    ROOT / "system" / "shared" / "other" / "images" / "tinyfont_white.png",
    ROOT / "system" / "shared" / "other" / "images" / "tinyfont_red.png",
)

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
    are drawn upright and turned with the rest of the strip. With no ``fill``
    the tiles hold only those lines, on a clear background.
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
        image = Image.new("RGBA", (TILE, TILE), fill + (255,) if fill else CLEAR)
        draw = ImageDraw.Draw(image)
        for y in range(TILE):
            for x in range(TILE):
                if fill and (x * 3 + y * 5) % 7 == 0:
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


def slope_tiles(top, fill, edge):
    """The walls of Spiral Tunnel: one solid tile, then the diagonal tiles that
    join a row of the tunnel to the next one.

    The tunnel's edge moves 2 to 5 tiles sideways from each row to the next, so
    the edge is a straight line that crosses that many tiles while it drops one
    tile: `shift` tiles, each holding a slice of it. Frame 0 is solid. Then the
    left edge, wall below the line, for shifts 2..5 (2 + 3 + 4 + 5 = 14 frames),
    then the right edge, wall above the line, the same. Drawn upright, with +x to
    the right and the centre of the disc down, like the original game's tiles.
    """
    def tile(shift, k, left):
        image = Image.new("RGBA", (TILE, TILE), CLEAR)
        for y in range(TILE):
            for x in range(TILE):
                line = (k * TILE + x + 0.5) / shift         # the line's y at this x
                below = (y + 0.5) - line                     # > 0: under the line
                if left:
                    if below >= 1.0:
                        image.putpixel((x, y), fill + (255,))
                    elif below >= 0.0:
                        image.putpixel((x, y), edge + (255,))
                else:
                    if below <= -1.0:
                        image.putpixel((x, y), fill + (255,))
                    elif below <= 0.0:
                        image.putpixel((x, y), edge + (255,))
        return image

    frames = [Image.new("RGBA", (TILE, TILE), fill + (255,))]
    for left in (True, False):
        for shift in range(2, 6):
            for k in range(shift):
                frames.append(tile(shift, k, left))
    return frames


def make_spiral_tunnel():
    top = True
    out = GAMES / "spiral_tunnel" / "images"
    strip(slope_tiles(top, (190, 62, 0), (255, 200, 60)), top).save(out / "tiles.png")
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
    # obvious which is which. The fill and the bright outlines are two tilemaps
    # over the same cells. A TUNNEL layer can land several rows of a tile on one
    # LED, and the last row drawn wins, so an outline drawn in the same tile as
    # the fill behind it could vanish. In a tilemap of its own, drawn over the
    # fill, it always shows. The fill has a frame for each outline frame, all
    # alike, so that both can read the same cells.
    fill = Image.new("RGBA", (TILE, TILE), (24, 110, 48, 255))
    strip([fill] * 16, top).save(out / "tiles.png")
    strip(wall_tiles(top, None, None, (150, 255, 170)), top).save(out / "outlines.png")
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


GAME_NAMES = ("spiral_tunnel", "catch_the_robots", "rim_runner", "dodge_em", "defender")


def main():
    for name in GAME_NAMES:
        (GAMES / name / "images").mkdir(parents=True, exist_ok=True)
        for font in FONTS:
            shutil.copyfile(font, GAMES / name / "images" / font.name)
    make_spiral_tunnel()
    make_catch_the_robots()
    make_rim_runner()
    make_dodge_em()
    make_defender()
    print("wrote art for", ", ".join(GAME_NAMES))


if __name__ == "__main__":
    main()
