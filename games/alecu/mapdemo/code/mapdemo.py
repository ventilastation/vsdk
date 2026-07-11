"""Map Demo: a VS2 tilemap test scene.

One 16x16 map of 16x16-pixel tiles (256 px wide = the full circle) on a
TUNNEL layer, with a sprite drawn on top. The joystick pans the map:
left/right rotates it around the display, up/down pans the viewport
vertically. Button A edits the map cell under the cursor sprite, proving
in-place frame-buffer mutation. Button D exits.
"""

from urandom import randrange

from ventilastation.director import director
from vs2 import HUD, TUNNEL, Scene, Sprite, Tilemap

MAP_COLUMNS = 16
MAP_ROWS = 16
TILE_W = 16
TILE_H = 16
MAP_W = MAP_COLUMNS * TILE_W
MAP_H = MAP_ROWS * TILE_H

GRASS = 0
WATER = 1
ROCK = 2
SAND = 3
MARKER = 4
WALL = 5

MAP_Y = 64
VIEW_H = 128
CURSOR_COLUMN = 0


class MapDemo(Scene):
    stripes_rom = "alecu.mapdemo"

    def on_enter(self):
        super().on_enter()
        self.world = self.layer("world", mode=TUNNEL)
        self.hud = self.layer("hud", mode=HUD)

        self.map_data = bytearray(MAP_COLUMNS * MAP_ROWS)
        self.generate_map()

        self.view_y = 0
        self.map = self.world.add(Tilemap(
            "terrain.png", self.map_data,
            columns=MAP_COLUMNS, rows=MAP_ROWS,
            tile_width=TILE_W, tile_height=TILE_H,
            x=0, y=MAP_Y,
            viewport=(0, self.view_y, MAP_W, VIEW_H),
        ))

        # drawn over the terrain: the cursor marks the editable cell
        self.cursor = self.world.add(Sprite(
            "ship.png", x=CURSOR_COLUMN + TILE_W // 2 - 4,
            y=MAP_Y + VIEW_H // 2, frame=0,
        ))
        self.badge = self.hud.add(Sprite("ship.png", x=124, y=0, frame=0))

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
        map_x = int(self.map.x) % 256
        source_x = (CURSOR_COLUMN - map_x) % 256
        col = (source_x // TILE_W) % MAP_COLUMNS
        row = (self.view_y + VIEW_H // 2) // TILE_H
        return col, min(row, MAP_ROWS - 1)

    def step(self):
        if director.was_pressed(director.BUTTON_D):
            director.pop()
            raise StopIteration()

        if director.is_pressed(director.JOY_LEFT):
            self.map.x -= 1
        if director.is_pressed(director.JOY_RIGHT):
            self.map.x += 1
        if director.is_pressed(director.JOY_UP):
            self.view_y = max(self.view_y - 1, 0)
        if director.is_pressed(director.JOY_DOWN):
            self.view_y = min(self.view_y + 1, MAP_H - VIEW_H)
        self.map.viewport = (0, self.view_y, MAP_W, VIEW_H)

        if director.was_pressed(director.BUTTON_A):
            col, row = self.cursor_cell()
            index = row * MAP_COLUMNS + col
            current = self.map_data[index]
            self.map_data[index] = GRASS if current == WALL else WALL


def main():
    return MapDemo()
