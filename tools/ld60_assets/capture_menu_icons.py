"""Captures the menu icons of the five LD60 "Circular Arcade" games in games/ld60/
from the games themselves.

    python3 tools/ld60_assets/capture_menu_icons.py

Each ``menu.png`` is a real moment of play. The game runs headless, the way
tests/test_ld60_games.py drives it, from a fixed seed with scripted input, and
its world layer (its tilemaps and every visible sprite, in the game's own
images) is painted flat in game coordinates: x round the disc, y in from the
rim. The 64 x 30 window round the player is the icon, turned the way the player
sees it. The four games played at the top of the disc store their pictures
turned through 180 degrees (see make_art.py), so each picture is turned back;
Rim Runner is played at the bottom, where x and y run the other way, so its
whole window is turned instead.

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
ABOVE = 64              # rows of the map a whole_map painting shows above the view
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


def fly_down_and_into_the_aliens(game, tick):
    """Defender: down toward the planet, then left, at a crowd of aliens."""
    return director.JOY_DOWN if tick <= 25 else director.JOY_LEFT


def stand_still(game, tick):
    return 0


# Which moment each icon shows: the seed, how many ticks into the game, the input,
# the player's sprite, and how far below the player-centred window it is taken
# (positive moves it toward the centre of the disc). Picked by eye for a frame
# with the player, enemies and the level all in view. Spiral Tunnel's walls are
# further apart than the icon is wide, so its window paints the whole map (not
# only what the camera shows) and is ``squeeze``d: rows of empty tunnel are cut
# from between the walls, so they come closer together and the icon looks full.
MOMENTS = {
    "spiral_tunnel": dict(seed="s4", ticks=86, play=dive_down_the_tunnel,
                          player=lambda game: game.ship, shift=-11, top=True,
                          whole_map=True, squeeze=14),
    "catch_the_robots": dict(seed="s0", ticks=200, play=stand_still,
                             player=lambda game: game.player.sprite, shift=0, top=True),
    "rim_runner": dict(seed="s2", ticks=64, play=run_left_now_and_then,
                       player=lambda game: game.runner, shift=8, top=False),
    "dodge_em": dict(seed="s0", ticks=120, play=stand_still,
                     player=lambda game: game.player.sprite, shift=0, top=True),
    "defender": dict(seed="s4", ticks=76, play=fly_down_and_into_the_aliens,
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


def paint_world(name, game, whole_map=False):
    """The world layer, flat, in game coordinates, each picture turned back
    upright from how a top-of-the-disc game stores it. It is ABOVE rows taller
    than the view, at the top: with ``whole_map`` the tilemaps are painted there
    too, beyond the edge of the view the game draws, and anywhere below it."""
    images = {}

    def frames_for(image):
        if image.name not in images:
            images[image.name] = frames_of(GAMES / name / "images" / image.name)
        return images[image.name]

    canvas = Image.new("RGBA", (W, ABOVE + DEPTH), (0, 0, 0, 255))

    def put(picture, x, y):
        x = int(x) % W
        for wrap in (0, -W):
            canvas.paste(picture, (x + wrap, ABOVE + int(y)), picture)

    for tilemap in game.world.tilemaps:
        if not tilemap.visible:
            continue
        frames = frames_for(tilemap.image)
        view_x, view_y = tilemap.view_x, tilemap.view_y
        view_right = view_x + tilemap._view_width
        view_bottom = view_y + tilemap._view_height
        if whole_map:
            view_top, view_bottom = view_y - ABOVE, DEPTH
        else:
            view_top = view_y
        for row in range(tilemap.rows):
            for col in range(tilemap.columns):
                frame = tilemap.cells[row * tilemap.columns + col]
                if frame == EMPTY_TILE:
                    continue
                # Only the part of the tile inside the view is drawn.
                sx, sy = col * TILE, row * TILE
                left, top = max(sx, view_x), max(sy, view_top)
                right, bottom = min(sx + TILE, view_right), min(sy + TILE, view_bottom)
                if left >= right or top >= bottom:
                    continue
                picture = frames[frame % len(frames)].rotate(180)
                picture = picture.crop((left - sx, top - sy, right - sx, bottom - sy))
                put(picture, tilemap.x + left - view_x, tilemap.y + top - view_y)

    for sprite in game.world.sprites:
        if not sprite.visible:
            continue
        picture = frames_for(sprite.image)[sprite.frame].rotate(180)
        if sprite.flip_x:
            picture = picture.transpose(Image.FLIP_LEFT_RIGHT)
        if sprite.flip_y:
            picture = picture.transpose(Image.FLIP_TOP_BOTTOM)
        put(picture, sprite.x, sprite.y)
    return canvas


def squeeze(window, rows):
    """Cut ``rows`` rows that are empty all the way across out of the window,
    the ones nearest its middle, then trim it to the icon's height. Nothing
    drawn is cut: the walls on either side just come closer together."""
    width, height = window.size
    pixels = window.load()
    middle = height // 2
    empty = [y for y in range(height)
             if all(pixels[x, y][:3] == (0, 0, 0) for x in range(width))]
    cut = set(sorted(empty, key=lambda y: abs(y - middle))[:rows])
    kept = [y for y in range(height) if y not in cut]
    out = Image.new("RGBA", (width, len(kept)))
    for new_y, y in enumerate(kept):
        out.paste(window.crop((0, y, width, y + 1)), (0, new_y))
    extra = len(kept) - ICON_H
    return out.crop((0, extra // 2, width, extra // 2 + ICON_H))


def icon(name, moment):
    game = play(name, moment)
    whole_map = moment.get("whole_map", False)
    world = paint_world(name, game, whole_map)
    player = moment["player"](game)
    rows = moment.get("squeeze", 0)
    height = ICON_H + rows
    left = int(player.x) + TILE // 2 - ICON_W // 2
    top = ABOVE + int(player.y) + TILE // 2 - height // 2 + moment["shift"]
    top = max(top, 0 if whole_map else ABOVE)
    # Three copies side by side, so a window across x = 0 needs no special case.
    round_the_disc = Image.new("RGBA", (W * 3, ABOVE + DEPTH))
    for copy in range(3):
        round_the_disc.paste(world, (copy * W, 0))
    window = round_the_disc.crop((W + left, top, W + left + ICON_W, top + height))
    if rows:
        window = squeeze(window, rows)
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
