import vs2


class Angles(vs2.Scene):
    def build(self):
        world = self.layer("world", projection=vs2.TUNNEL)
        for x in (0, 64, 128, 192):
            world.sprite("ship.png", x=x, y=0)


def main():
    return Angles()
