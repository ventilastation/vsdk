"""Draws games/demos/tutorial_game/menu.png: the game's 64x30 menu icon.

    python3 make_menu_icon.py

A dark trench with a ring of cyan conduit, a few lit windows and the ship at
the bottom, in the same palette as the game. The launcher shows this icon at
64x30 pixels, like every game's. Needs Pillow.
"""
from pathlib import Path

from PIL import Image, ImageDraw

W, H = 64, 30
ROOT = Path(__file__).resolve().parents[2] / "games/demos/tutorial_game"

HULL = (10, 13, 20)
HULL_LIT = (22, 28, 42)
CYAN = (30, 215, 235)
CYAN_DIM = (10, 72, 84)
AMBER = (255, 176, 32)
ORANGE = (255, 112, 20)


def main():
    img = Image.new("RGB", (W, H), HULL)
    draw = ImageDraw.Draw(img)

    # Trench walls: bands that narrow toward the vanishing point at the top.
    for i, y in enumerate(range(0, 22, 3)):
        inset = 2 + i * 3
        draw.line((inset, y, W - 1 - inset, y), fill=HULL_LIT)
    for x in (4, 14, 24, 40, 50, 60):
        draw.line((x, H - 1, 32 + (x - 32) // 3, 0), fill=HULL_LIT)

    # The conduit ring, seen as an ellipse, with a dim shadow row under it.
    draw.arc((8, 4, 55, 22), 0, 360, fill=CYAN_DIM)
    draw.arc((9, 3, 54, 21), 0, 360, fill=CYAN)

    # Lit windows and vents.
    for x, y, colour in ((12, 9, AMBER), (15, 9, AMBER), (48, 11, AMBER),
                         (51, 11, AMBER), (22, 15, ORANGE), (41, 16, ORANGE)):
        draw.rectangle((x, y, x + 1, y), fill=colour)

    # The ship, from the game's own strip: frame 0, flying level.
    ship = Image.open(ROOT / "images/ship.png").convert("RGBA").crop((0, 0, 18, 18))
    img.paste(ship, ((W - 18) // 2, H - 18 + 1), ship)

    out = ROOT / "menu.png"
    img.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
