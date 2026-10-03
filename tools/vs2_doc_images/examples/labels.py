import vs2

PLATE, SEAM, PIPE, WINDOWS, VENT, HAZARD, LIGHTS, CONDUIT = range(8)


class Labels(vs2.Scene):
    def build(self):
        world = self.layer("world", projection=vs2.TUNNEL)
        hud = self.layer("hud", projection=vs2.HUD)
        self.ground = world.tilemap("trench.png", columns=16, rows=16,
                                    view_width=256, view_height=160)
        self.ground.fill(PLATE)
        for col in range(16):
            self.ground[col, 0] = PIPE
            self.ground[col, 4] = CONDUIT
        for col in range(1, 16, 4):
            self.ground[col, 2] = WINDOWS
            self.ground[col + 2, 2] = VENT
        self.ship = world.sprite("ship.png", x=128, y=0)

        # Upright at the bottom of the disc...
        self.score = hud.label("numerals.png", columns=5, x=246, y=1)
        self.score.set_number(7260, width=5, pad="0")

        # ...and flipped both ways at the top.
        self.top = hud.label("numerals.png", columns=5, x=118, y=14,
                             flip_x=True, flip_y=True)
        self.top.set_number(7260, width=5, pad="0")


def main():
    return Labels()
