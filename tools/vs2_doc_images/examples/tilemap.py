import vs2

GRASS, WATER, ROCK, SAND, MARKER, WALL = range(6)


class Tilemap(vs2.Scene):
    def build(self):
        world = self.layer("world", projection=vs2.TUNNEL)
        self.ground = world.tilemap("terrain.png", columns=16, rows=16,
                                    view_width=256, view_height=128, y=16)
        # Fill only the cells that have something in them. Every other cell
        # stays EMPTY_TILE, so the rest of the disc is left dark.
        for row in range(1, 7):
            for col in range(3, 10):
                tile = GRASS
                if col == 6:
                    tile = WATER
                elif row in (1, 6):
                    tile = SAND
                elif (col + row) % 5 == 0:
                    tile = ROCK
                self.ground[col, row] = tile
        self.ship = world.sprite("ship.png", x=128, y=0)


def main():
    return Tilemap()
