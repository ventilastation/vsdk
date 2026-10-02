import vs2

GRASS, WATER, ROCK, SAND = range(4)


class Labels(vs2.Scene):
    def build(self):
        world = self.layer("world", projection=vs2.TUNNEL)
        hud = self.layer("hud", projection=vs2.HUD)
        self.ground = world.tilemap("terrain.png", columns=16, rows=16,
                                    view_width=256, view_height=128, y=16)
        for row in range(1, 7):
            for col in range(3, 10):
                self.ground[col, row] = SAND if row in (1, 6) else GRASS
        self.ship = world.sprite("ship.png", x=128, y=0)

        # Upright at the bottom of the disc...
        self.score = hud.label("numerals.png", columns=5,
                               x=246, y=1)
        self.score.set_number(420, width=5, pad="0")

        # ...and flipped both ways at the top.
        self.top = hud.label("numerals.png", columns=5,
                             x=118, y=14, flip_x=True, flip_y=True)
        self.top.set_number(420, width=5, pad="0")


def main():
    return Labels()
