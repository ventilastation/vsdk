import vs2


class Projections(vs2.Scene):
    def build(self):
        world = self.layer("world", projection=vs2.TUNNEL)
        hud = self.layer("hud", projection=vs2.HUD)
        for y in (0, 40, 80, 120, 170, 220):
            world.sprite("ship.png", x=128, y=y)
        for y in (0, 14, 28, 40):
            hud.sprite("ship.png", x=0, y=y)


def main():
    return Projections()
