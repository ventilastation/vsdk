import vs2


class Frames(vs2.Scene):
    def build(self):
        world = self.layer("world", projection=vs2.TUNNEL)
        for frame in range(4):
            world.sprite("ship.png", x=104 + frame * 16, y=10, frame=frame)


def main():
    return Frames()
