"""Constant heavy V2 scene used for real render-timing profiling."""

import vs2


TERRAIN_COLS = 8
TERRAIN_ROWS = 8
TERRAIN_TILE_W = 32
TERRAIN_TILE_H = 16
TERRAIN_NEAR_Y = 0
TERRAIN_BUFFER_ROWS = TERRAIN_ROWS + 1
TERRAIN_VIEW_H = TERRAIN_ROWS * TERRAIN_TILE_H
TERRAIN_SCROLL_SPEED = 2
TOP_SCORE_X = 93
NUM_LAYERS = 6
SPRITES_PER_LAYER = 10
SPRITE_Y_MIN = 10
SPRITE_Y_MAX = 190
SPRITE_Y_SPAN = SPRITE_Y_MAX - SPRITE_Y_MIN
KIND_SHIP, KIND_BULLET, KIND_MISSILE, KIND_EXPLOSION = range(4)
KIND_PATTERN = (KIND_SHIP, KIND_BULLET, KIND_MISSILE, KIND_EXPLOSION)
_KIND_IMAGE = ("ship.png", "shots.png", "shots.png", "explosion.png")


def terrain_river_center(row, area):
    return (row // 3 + area * 2) % TERRAIN_COLS


def terrain_frame_for(col, row, area):
    river = terrain_river_center(row, area)
    delta = min(abs(col - river), TERRAIN_COLS - abs(col - river))
    next_river = terrain_river_center(row + 3, area)
    next_delta = min(abs(col - next_river), TERRAIN_COLS - abs(col - next_river))
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


class Mover:
    def __init__(self, sprite, kind, theta, y, dy, dtheta, frame_base):
        self.sprite, self.kind, self.theta, self.y = sprite, kind, theta, y
        self.dy, self.dtheta, self.frame_base, self.anim = dy, dtheta, frame_base, 0

    def update(self):
        self.y += self.dy
        if self.y >= SPRITE_Y_MAX:
            self.y -= SPRITE_Y_SPAN
        self.theta = (self.theta + self.dtheta) % vs2.display.width
        self.anim += 1
        self.sprite.x, self.sprite.y = self.theta, self.y
        if self.kind == KIND_EXPLOSION:
            self.sprite.frame = (self.anim // 3) % self.sprite.image.frames
        elif self.kind == KIND_SHIP:
            self.sprite.frame = (self.frame_base + self.anim // 12) % self.sprite.image.frames


class PovStress(vs2.Scene):
    def build(self):
        self.depth = self.camera_theta = self.area = self.tick = 0
        self.score = 0
        self.terrain_layer = self.layer("terrain", projection=vs2.TUNNEL)
        self.terrain_data = bytearray(TERRAIN_COLS * TERRAIN_BUFFER_ROWS)
        self.terrain_base_row = None
        self.terrain = self.terrain_layer.tilemap(
            "terrain.png", columns=TERRAIN_COLS, rows=TERRAIN_BUFFER_ROWS,
            cells=self.terrain_data, x=0, y=TERRAIN_NEAR_Y,
            view_width=vs2.display.width, view_height=TERRAIN_VIEW_H)
        self.update_terrain()
        self.hud = self.layer("hud", projection=vs2.HUD)
        self.scoreboard = self.hud.label("digits.png", columns=5, x=TOP_SCORE_X, y=1,
                                         glyphs="0123456789")
        self.scoreboard.set_number(0, width=5, pad="0")
        self.movers = []
        for layer_index in range(NUM_LAYERS):
            layer = self.layer("field%d" % layer_index, projection=vs2.TUNNEL)
            for index in range(SPRITES_PER_LAYER):
                kind = KIND_PATTERN[index % len(KIND_PATTERN)]
                theta = (index * (vs2.display.width // SPRITES_PER_LAYER) + layer_index * 8) % vs2.display.width
                y = SPRITE_Y_MIN + (index * (SPRITE_Y_SPAN // SPRITES_PER_LAYER) + layer_index * 9) % SPRITE_Y_SPAN
                frame = 1 if kind == KIND_MISSILE else 0
                sprite = layer.sprite(_KIND_IMAGE[kind], x=theta, y=y, frame=frame)
                self.movers.append(Mover(sprite, kind, theta, y, layer_index + 1,
                                         layer_index - 2, index % sprite.image.frames))

    def update_terrain(self):
        base_row = self.depth // TERRAIN_TILE_H
        if base_row != self.terrain_base_row:
            self.terrain_base_row = base_row
            for row in range(TERRAIN_BUFFER_ROWS):
                for col in range(TERRAIN_COLS):
                    self.terrain[col, row] = terrain_frame_for(col, base_row + row, self.area)
        self.terrain.x = (self.area * 13 - self.camera_theta - TERRAIN_TILE_W // 2) % vs2.display.width
        self.terrain.view_y = self.depth % TERRAIN_TILE_H

    def update(self):
        self.tick += 1
        self.depth += TERRAIN_SCROLL_SPEED
        self.camera_theta = (self.camera_theta + 1) % vs2.display.width
        self.update_terrain()
        for mover in self.movers:
            mover.update()
        self.score = (self.score + 7) % 100000
        self.scoreboard.set_number(self.score, width=5, pad="0")


def main():
    return PovStress()
