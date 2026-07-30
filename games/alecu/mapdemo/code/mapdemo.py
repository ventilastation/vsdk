"""One editable VS2 tilemap, with scalar allocation-free scrolling."""

from urandom import randrange

import vs2
from vs2.controls import A, DOWN, LEFT, RIGHT, UP, joy1


MAP_COLUMNS = 16
MAP_ROWS = 16
TILE_W = 16
TILE_H = 16
MAP_H = MAP_ROWS * TILE_H
GRASS, WATER, ROCK, SAND, MARKER, WALL = range(6)
MAP_Y = 51
VIEW_H = 128
CURSOR_COLUMN = 0


class MapDemo(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)
        self.map_data = bytearray(MAP_COLUMNS * MAP_ROWS)
        self.generate_map()
        self.view_y = 0
        self.map = self.world.tilemap("terrain.png", columns=MAP_COLUMNS, rows=MAP_ROWS,
                                      cells=self.map_data, x=0, y=MAP_Y,
                                      view_width=vs2.display.width, view_height=VIEW_H)
        self.cursor = self.world.sprite("ship.png", x=CURSOR_COLUMN + TILE_W // 2 - 4,
                                        y=MAP_Y + VIEW_H // 2)
        self.badge = self.hud.sprite("ship.png", x=124, y=0)

    def generate_map(self):
        for row in range(MAP_ROWS):
            for col in range(MAP_COLUMNS):
                if (col + row) % 7 == 0:
                    tile = WATER
                elif (col * row) % 11 == 0:
                    tile = SAND
                elif (col + 2 * row) % 13 == 0:
                    tile = ROCK
                elif randrange(12) == 0:
                    tile = MARKER
                else:
                    tile = GRASS
                self.map_data[row * MAP_COLUMNS + col] = tile

    def cursor_cell(self):
        map_x = int(self.map.x) % vs2.display.width
        source_x = (CURSOR_COLUMN - map_x) % vs2.display.width
        col = (source_x // TILE_W) % MAP_COLUMNS
        row = (self.view_y + VIEW_H // 2) // TILE_H
        return col, min(row, MAP_ROWS - 1)

    def update(self):
        if joy1.held(LEFT):
            self.map.x -= 1
        if joy1.held(RIGHT):
            self.map.x += 1
        if joy1.held(UP):
            self.view_y = max(self.view_y - 1, 0)
        if joy1.held(DOWN):
            self.view_y = min(self.view_y + 1, MAP_H - VIEW_H)
        self.map.view_y = self.view_y
        if joy1.just_pressed(A):
            col, row = self.cursor_cell()
            self.map[col, row] = GRASS if self.map[col, row] == WALL else WALL


def main():
    return MapDemo()
