"""Draws games/demos/tutorial_game/images/enemy.png: the tutorial game's drone.

    python3 make_enemy_art.py

Six 16x16 frames of a spinning drone: a dark steel hull with a glowing core and
four arms that each end in a red light. The arms turn 15 degrees per frame, and
the drone looks the same every 90 degrees, so six frames make a seamless loop and
every frame is visibly different from its neighbours. Needs Pillow.
"""
from math import cos, radians, sin
from pathlib import Path

from PIL import Image

SIZE = 16
FRAMES = 6
CENTRE = (SIZE - 1) / 2

HULL = (52, 60, 78)
HULL_RIM = (112, 126, 150)
ARM = (150, 164, 188)
ARM_SHADE = (84, 96, 120)
LIGHT = (255, 70, 60)
LIGHT_HOT = (255, 190, 150)
CORE = (255, 150, 30)
CORE_HOT = (255, 235, 140)


def put(px, x, y, colour):
    if 0 <= x < SIZE and 0 <= y < SIZE:
        px[x, y] = colour + (255,)


def frame(index):
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    px = img.load()
    turn = index * 90 / FRAMES                      # degrees; 90 loops the drone

    # Arms first, so the hull sits over their roots.
    for arm in range(4):
        angle = radians(turn + arm * 90)
        dx, dy = cos(angle), sin(angle)
        for step in range(8, 15):
            distance = step / 2
            x = round(CENTRE + dx * distance)
            y = round(CENTRE + dy * distance)
            put(px, x, y, ARM)
            # A second row of pixels one side of the arm gives it thickness
            # and a shaded edge.
            put(px, round(x - dy), round(y + dx), ARM_SHADE)
        tip_x = round(CENTRE + dx * 7)
        tip_y = round(CENTRE + dy * 7)
        put(px, tip_x, tip_y, LIGHT)
        put(px, round(tip_x - dx), round(tip_y - dy), LIGHT_HOT)

    # Hull: a disc with a lighter rim.
    for y in range(SIZE):
        for x in range(SIZE):
            distance = ((x - CENTRE) ** 2 + (y - CENTRE) ** 2) ** 0.5
            if distance <= 3.6:
                put(px, x, y, HULL_RIM if distance > 2.7 else HULL)

    # The core pulses once per loop: brightest on frame 0, dimmest on frame 3.
    hot = index in (0, 1, FRAMES - 1)
    for x, y in ((7, 7), (8, 7), (7, 8), (8, 8)):
        put(px, x, y, CORE_HOT if hot else CORE)
    return img


def main():
    strip = Image.new("RGBA", (SIZE * FRAMES, SIZE), (0, 0, 0, 0))
    for index in range(FRAMES):
        strip.paste(frame(index), (index * SIZE, 0))
    out = Path(__file__).resolve().parents[2] / "games/demos/tutorial_game/images/enemy.png"
    strip.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
