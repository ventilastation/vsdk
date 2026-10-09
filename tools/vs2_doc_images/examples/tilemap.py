import vs2

PLATE, SEAM, PIPE, WINDOWS, VENT, HAZARD, LIGHTS, CONDUIT = range(8)


class Tilemap(vs2.Scene):
    def build(self):
        world = self.layer("world", projection=vs2.TUNNEL)
        self.ground = world.tilemap("trench.png", columns=16, rows=16,
                                    view_width=256, view_height=160)
        self.ground.fill(PLATE)
        for col in range(16):
            self.ground[col, 0] = PIPE          # a ring of pipe at the rim
            self.ground[col, 4] = CONDUIT       # a glowing ring further in
        for col in range(1, 16, 4):
            self.ground[col, 2] = WINDOWS
            self.ground[col + 2, 2] = VENT
        for col in range(2, 16, 8):
            self.ground[col, 5] = LIGHTS
            self.ground[col + 4, 5] = HAZARD
        self.ship = world.sprite("ship.png", y=0)
        self.ship.x = -(self.ship.width // 2)


def main():
    return Tilemap()
