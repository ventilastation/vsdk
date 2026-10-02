import vs2

GRASS, WATER, ROCK, SAND, MARKER, WALL = range(6)


class Tilemap(vs2.Scene):
    def build(self):
        world = self.layer("world", projection=vs2.TUNNEL)
        self.ground = world.tilemap("terrain.png", columns=16, rows=16,
                                    view_width=256, view_height=128)
        self.ground.fill(GRASS)
        for row in range(16):
            for col in range(16):
                if (col + row) % 7 == 0:
                    self.ground[col, row] = WATER
                elif (col * row) % 11 == 0:
                    self.ground[col, row] = SAND
                elif (col + 2 * row) % 13 == 0:
                    self.ground[col, row] = ROCK
        self.ship = world.sprite("ship.png", x=128, y=30)


def main():
    return Tilemap()
