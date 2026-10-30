"""Captures the menu icons of the five LD60 "Circular Arcade" games in games/ld60/
from the games themselves.

    python3 tools/ld60_assets/capture_menu_icons.py

Each ``menu.png`` is a real moment of play. The game runs headless, the way
tests/test_ld60_games.py drives it, from a fixed seed with scripted input, and
its world layer (the tilemap and every visible sprite, in the game's own
``images/tiles.png`` and ``images/sprites.png``) is painted flat in game
coordinates: x round the disc, y in from the rim. The 64 x 30 window round the
player is the icon, turned the way the player sees it. The four games played at
the top of the disc store their pictures turned through 180 degrees (see
make_art.py), so each picture is turned back; Rim Runner is played at the bottom,
where x and y run the other way, so its whole window is turned instead.

Run make_art.py first when the art changes. Needs Pillow.
"""
import os
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "micropython"))
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("uos", os)
sys.modules.setdefault("urandom", random)

TICK_MS = 30
CLOCK = [1000]


class _Utime:
    """A virtual clock, so the games' timers run at the pace of the steps."""

    @staticmethod
    def ticks_ms():
        return CLOCK[0]

    @staticmethod
    def ticks_add(value, delta):
        return value + delta

    @staticmethod
    def ticks_diff(end, start):
        return end - start

    @staticmethod
    def sleep_ms(ms):
        pass


sys.modules["utime"] = _Utime

from PIL import Image  # noqa: E402

from ventilastation import api_guard  # noqa: E402
from ventilastation.app_loader import load_app  # noqa: E402
from ventilastation.director import configure_runtime, director, reset_runtime, stripes  # noqa: E402

GAMES = ROOT / "games" / "ld60"
W = 256                 # columns round the disc
DEPTH = 256             # rows in from the rim
TILE = 8
ICON_W, ICON_H = 64, 30
EMPTY_TILE = 255


# --- Playing ---------------------------------------------------------------------

def dive_down_the_tunnel(game, tick):
    """Spiral Tunnel's autopilot: dive, and keep the ship in the middle of the
    tunnel just below it, using the game's own slanted edges."""
    depth = game.wy + TILE // 2 + 6
    row = int(depth) // TILE
    into = depth - row * TILE
    start = game.left[row] * TILE + game.left_shift[row] * into
    width = game.span[row] * TILE + (game.right_shift[row] - game.left_shift[row]) * into
    across = ((game.wx + TILE // 2 - start) % W) / width
    buttons = director.JOY_DOWN if tick % 3 else 0
    if across < 0.4:
        buttons |= director.JOY_RIGHT
    elif across > 0.6:
        buttons |= director.JOY_LEFT
    return buttons


def run_left_now_and_then(game, tick):
    return director.JOY_LEFT if (tick // 40) % 2 else 0


def fly_down_to_the_planet(game, tick):
    return director.JOY_DOWN if tick <= 25 else 0


def stand_still(game, tick):
    return 0


# Which moment each icon shows: the seed, how many ticks into the game, the input,
# the player's sprite, and how far below the player-centred window it is taken
# (positive moves it toward the centre of the disc). Picked by eye for a frame
# with the player, an enemy and the level all in view.
MOMENTS = {
    "spiral_tunnel": dict(seed="s2", ticks=84, play=dive_down_the_tunnel,
                          player=lambda game: game.ship, shift=-6, top=True),
    "catch_the_robots": dict(seed="s0", ticks=200, play=stand_still,
                             player=lambda game: game.player.sprite, shift=0, top=True),
    "rim_runner": dict(seed="s2", ticks=64, play=run_left_now_and_then,
                       player=lambda game: game.runner, shift=8, top=False),
    "dodge_em": dict(seed="s0", ticks=120, play=stand_still,
                     player=lambda game: game.player.sprite, shift=0, top=True),
    "defender": dict(seed="s3", ticks=136, play=fly_down_to_the_planet,
                     player=lambda game: game.ship, shift=3, top=True),
}


def step(buttons):
    director.platform.comms.push_input(bytes([buttons]))
    CLOCK[0] += TICK_MS
    try:
        director.step_once()
    except StopIteration:
        pass


def play(name, moment):
    """Start the game and play it up to its moment; returns the Game scene."""
    reset_runtime()
    api_guard.reset()
    runtime = configure_runtime("headless")
    stripes.clear()
    text = (GAMES / name / "images" / "__images__.yaml").read_text()
    strips = [(strip, int(frames)) for strip, frames
              in re.findall(r"strip: (\S+)\s+frames: (\d+)", text)]

    def fake_load_rom(_filename):
        for index, (strip, frames) in enumerate(strips):
            stripes[strip] = index
            runtime.platform.sprites.stripes[index] = {
                "width": TILE, "height": TILE, "frames": frames, "palette": 0, "glyphs": None,
            }

    runtime.load_rom = fake_load_rom
    random.seed(moment["seed"])
    load_app("ld60." + name)
    step(director.BUTTON_A)
    step(0)
    game = director.scene_stack[-1]
    for tick in range(1, moment["ticks"] + 1):
        step(moment["play"](game, tick))
    if type(director.scene_stack[-1]).__name__ != "Game":
        raise SystemExit("%s: the game ended before tick %d" % (name, moment["ticks"]))
    return game


# --- Painting ----------------------------------------------------------------

def frames_of(path):
    strip = Image.open(path).convert("RGBA")
    return [strip.crop((index * TILE, 0, index * TILE + TILE, TILE))
            for index in range(strip.width // TILE)]


def paint_world(name, game):
    """The world layer, flat, in game coordinates, each picture turned back
    upright from how a top-of-the-disc game stores it."""
    images = {strip: frames_of(GAMES / name / "images" / strip)
              for strip in ("tiles.png", "sprites.png")}
    canvas = Image.new("RGBA", (W, DEPTH), (0, 0, 0, 255))

    def put(picture, x, y):
        x = int(x) % W
        for wrap in (0, -W):
            canvas.paste(picture, (x + wrap, int(y)), picture)

    for tilemap in game.world.tilemaps:
        if not tilemap.visible:
            continue
        frames = images[tilemap.image.name]
        view_x, view_y = tilemap.view_x, tilemap.view_y
        view_right = view_x + tilemap._view_width
        view_bottom = view_y + tilemap._view_height
        for row in range(tilemap.rows):
            for col in range(tilemap.columns):
                frame = tilemap.cells[row * tilemap.columns + col]
                if frame == EMPTY_TILE:
                    continue
                # Only the part of the tile inside the view is drawn.
                sx, sy = col * TILE, row * TILE
                left, top = max(sx, view_x), max(sy, view_y)
                right, bottom = min(sx + TILE, view_right), min(sy + TILE, view_bottom)
                if left >= right or top >= bottom:
                    continue
                picture = frames[frame % len(frames)].rotate(180)
                picture = picture.crop((left - sx, top - sy, right - sx, bottom - sy))
                put(picture, tilemap.x + left - view_x, tilemap.y + top - view_y)

    for sprite in game.world.sprites:
        if not sprite.visible:
            continue
        picture = images[sprite.image.name][sprite.frame].rotate(180)
        if sprite.flip_x:
            picture = picture.transpose(Image.FLIP_LEFT_RIGHT)
        if sprite.flip_y:
            picture = picture.transpose(Image.FLIP_TOP_BOTTOM)
        put(picture, sprite.x, sprite.y)
    return canvas


def icon(name, moment):
    game = play(name, moment)
    world = paint_world(name, game)
    player = moment["player"](game)
    left = int(player.x) + TILE // 2 - ICON_W // 2
    top = max(int(player.y) + TILE // 2 - ICON_H // 2 + moment["shift"], 0)
    # Three copies side by side, so a window across x = 0 needs no special case.
    round_the_disc = Image.new("RGBA", (W * 3, DEPTH))
    for copy in range(3):
        round_the_disc.paste(world, (copy * W, 0))
    window = round_the_disc.crop((W + left, top, W + left + ICON_W, top + ICON_H))
    if not moment["top"]:
        window = window.rotate(180)
    return window.convert("RGB")


def main():
    for name, moment in MOMENTS.items():
        icon(name, moment).save(GAMES / name / "menu.png")
    reset_runtime()
    api_guard.reset()
    print("captured menu icons for", ", ".join(MOMENTS))


if __name__ == "__main__":
    main()
