"""POV render stress demo.

A deliberately heavy, *constant and reproducible* vs2 scene for profiling the
rotor's render pipeline (see tools/pov_profile_report.py). Unlike a real game,
the load here doesn't vary with play: the same terrain scrolls, the same 60
sprites always stay on screen, and the scoreboard keeps ticking, so every
profiling window sees the same drawing cost.

It reuses Vixeous's assets and terrain so the pieces are the exact sizes of a
real game:
  - a base terrain tilemap identical to Vixeous (games/alecu/vixeous),
  - a scoreboard (5 score digits + 3 life icons),
  - 6 layers of 10 sprites each (60 total), sized like Vixeous's ship,
    bullet, missile and explosion, moving through the screen at a different
    speed per layer.
"""

from vs2 import HUD, TUNNEL, Scene, Sprite, Tilemap

from ventilastation.director import director


COLUMNS = 256

# --- terrain: identical to games/alecu/vixeous ---
TERRAIN_COLS = 8
TERRAIN_ROWS = 8
TERRAIN_TILE_W = 32
TERRAIN_TILE_H = 16
TERRAIN_NEAR_Y = 0
# one extra buffer row scrolls in from the far edge
TERRAIN_BUFFER_ROWS = TERRAIN_ROWS + 1
TERRAIN_VIEW_H = TERRAIN_ROWS * TERRAIN_TILE_H
TERRAIN_SCROLL_SPEED = 2

# --- scoreboard: identical placement to Vixeous ---
TOP_SCORE_X = 93
TOP_LIVES_X = 140

# --- moving sprite field ---
NUM_LAYERS = 6
SPRITES_PER_LAYER = 10
SPRITE_Y_MIN = 10
SPRITE_Y_MAX = 190
SPRITE_Y_SPAN = SPRITE_Y_MAX - SPRITE_Y_MIN

KIND_SHIP = 0
KIND_BULLET = 1
KIND_MISSILE = 2
KIND_EXPLOSION = 3
# Repeating mix so each 10-sprite layer carries every Vixeous object size.
KIND_PATTERN = (KIND_SHIP, KIND_BULLET, KIND_MISSILE, KIND_EXPLOSION)

# strip name + fixed/animated frame behaviour per kind, sized like Vixeous:
#   ship.png      18x13 (4 frames)   shots.png     6x10 (frame 0 shot, 1 bomb)
#   explosion.png 20x20 (6 frames)
_KIND_STRIP = {
    KIND_SHIP: "ship.png",
    KIND_BULLET: "shots.png",
    KIND_MISSILE: "shots.png",
    KIND_EXPLOSION: "explosion.png",
}
_EXPLOSION_FRAMES = 6
_SHIP_FRAMES = 4


def clamp(value, low, high):
    return max(low, min(high, value))


def terrain_river_center(row, area):
    return (row // 3 + area * 2) % TERRAIN_COLS


def terrain_frame_for(col, row, area):
    river = terrain_river_center(row, area)
    delta = abs(col - river)
    delta = min(delta, TERRAIN_COLS - delta)
    next_river = terrain_river_center(row + 3, area)
    next_delta = abs(col - next_river)
    next_delta = min(next_delta, TERRAIN_COLS - next_delta)
    if delta == 0:
        return (row + col) & 1
    if delta == 1 and next_delta == 0:
        return 8 + ((row + col) & 1)
    if delta == 1:
        return 2 + ((row + col) & 1)
    if delta == 2 and next_delta <= 1:
        return 10 + ((row + col) & 1)
    if delta == 2:
        return 4 + ((row + col) & 1)
    if delta == 3 and next_delta == 2:
        return 12
    if delta == 3:
        return 6 + ((row + col + area) & 1)
    if row % 13 == 0 and col in (0, 4):
        return 14
    if row % 17 == 4 and col in (3, 7):
        return 15
    return 6 + ((row + col + area) & 1)


class ScoreBoard:
    """Identical to Vixeous's scoreboard: 5 score digits + 3 life icons."""

    def __init__(self, hud):
        self.score_digits = [
            hud.add(Sprite("digits.png", x=TOP_SCORE_X + n * 5, y=1, frame=0))
            for n in range(5)
        ]
        self.life_icons = [
            hud.add(Sprite("digits.png", x=TOP_LIVES_X + n * 6, y=1, frame=11))
            for n in range(3)
        ]

    def set_score(self, value):
        text = "%05d" % clamp(value, 0, 99999)
        for n, digit in enumerate(text):
            self.score_digits[n].frame = ord(digit) - 48

    def set_lives(self, lives):
        for n, icon in enumerate(self.life_icons):
            icon.frame = 11 if n < lives else 10


class Mover:
    """One always-visible sprite that loops through the screen at a fixed
    per-layer speed. Kept deterministic (no RNG) so the render load is
    identical on every run."""

    def __init__(self, sprite, kind, theta, y, dy, dtheta, frame_base):
        self.sprite = sprite
        self.kind = kind
        self.theta = theta
        self.y = y
        self.dy = dy
        self.dtheta = dtheta
        self.frame_base = frame_base
        self.anim = 0

    def step(self):
        y = self.y + self.dy
        if y >= SPRITE_Y_MAX:
            y -= SPRITE_Y_SPAN
        elif y < SPRITE_Y_MIN:
            y += SPRITE_Y_SPAN
        self.y = y
        self.theta = (self.theta + self.dtheta) % COLUMNS
        self.anim += 1

        sprite = self.sprite
        sprite.x = self.theta
        sprite.y = y
        if self.kind == KIND_EXPLOSION:
            sprite.frame = (self.anim // 3) % _EXPLOSION_FRAMES
        elif self.kind == KIND_SHIP:
            # slow orientation cycle so ships aren't visually frozen
            sprite.frame = (self.frame_base + (self.anim // 12)) % _SHIP_FRAMES


class PovStress(Scene):
    stripes_rom = "demos.povstress"
    keep_music = False

    def on_enter(self):
        super().on_enter()

        self.depth = 0
        self.camera_theta = 0
        self.area = 0
        self.score = 0
        self.lives = 3
        self.tick = 0

        # Base terrain tilemap, identical to Vixeous.
        self.terrain_layer = self.layer("terrain", mode=TUNNEL)
        self.terrain_data = bytearray(TERRAIN_COLS * TERRAIN_BUFFER_ROWS)
        self.terrain_base_row = None
        self.terrain = self.terrain_layer.add(Tilemap(
            "terrain.png", self.terrain_data,
            columns=TERRAIN_COLS, rows=TERRAIN_BUFFER_ROWS,
            tile_width=TERRAIN_TILE_W, tile_height=TERRAIN_TILE_H,
            x=0, y=TERRAIN_NEAR_Y,
            viewport=(0, 0, COLUMNS, TERRAIN_VIEW_H),
        ))
        self.update_terrain()

        # Scoreboard on a HUD layer.
        self.hud = self.layer("hud", mode=HUD)
        self.scoreboard = ScoreBoard(self.hud)
        self.scoreboard.set_score(self.score)
        self.scoreboard.set_lives(self.lives)

        # 6 layers x 10 sprites, each layer at its own speed.
        self.movers = []
        for layer_index in range(NUM_LAYERS):
            layer = self.layer("field%d" % layer_index, mode=TUNNEL)
            # distinct per-layer speeds: dy 1..6 outward, theta drift spread
            # across -2..+3 so both movement axes vary between layers.
            dy = layer_index + 1
            dtheta = layer_index - 2
            for i in range(SPRITES_PER_LAYER):
                kind = KIND_PATTERN[i % len(KIND_PATTERN)]
                theta = (i * (COLUMNS // SPRITES_PER_LAYER) + layer_index * 8) % COLUMNS
                y = SPRITE_Y_MIN + (i * (SPRITE_Y_SPAN // SPRITES_PER_LAYER)
                                    + layer_index * 9) % SPRITE_Y_SPAN
                frame_base = i % _SHIP_FRAMES
                initial_frame = 1 if kind == KIND_MISSILE else 0
                sprite = layer.add(Sprite(
                    _KIND_STRIP[kind], x=theta, y=y, frame=initial_frame))
                self.movers.append(
                    Mover(sprite, kind, theta, y, dy, dtheta, frame_base))

    def update_terrain(self):
        base_row = self.depth // TERRAIN_TILE_H
        if base_row != self.terrain_base_row:
            self.terrain_base_row = base_row
            for row in range(TERRAIN_BUFFER_ROWS):
                world_row = base_row + row
                offset = row * TERRAIN_COLS
                for col in range(TERRAIN_COLS):
                    self.terrain_data[offset + col] = terrain_frame_for(
                        col, world_row, self.area)
        self.terrain.x = (self.area * 13 - self.camera_theta
                          - TERRAIN_TILE_W // 2) % COLUMNS
        self.terrain.viewport = (
            0, self.depth % TERRAIN_TILE_H, COLUMNS, TERRAIN_VIEW_H)

    def step(self):
        if director.was_pressed(director.BUTTON_D):
            director.pop()
            raise StopIteration()

        self.tick += 1
        self.depth += TERRAIN_SCROLL_SPEED
        self.camera_theta = (self.camera_theta + 1) % COLUMNS
        self.update_terrain()

        for mover in self.movers:
            mover.step()

        # keep the HUD live so the whole scene is in motion
        self.score = (self.score + 7) % 100000
        self.scoreboard.set_score(self.score)
        if self.tick % 40 == 0:
            self.lives = (self.lives + 1) % 4
            self.scoreboard.set_lives(self.lives)


def main():
    return PovStress()
