"""One sprite per frame of the tutorial game's ship (level, turned left, turned
right), side by side on the bottom of the disc. The level ship is in the middle.
Increasing x runs right to left there, so the left-turned frame 1 is the one at
the larger x. The spacing leaves a gap between neighbours."""

import vs2

WIDTH = 18           # columns in one frame of the strip
SPACING = 26         # columns between neighbours, so there is a gap
LEVEL, LEFT, RIGHT = range(3)


class Frames(vs2.Scene):
    def build(self):
        world = self.layer("world", projection=vs2.TUNNEL)
        middle = -WIDTH // 2         # centres the level ship on x = 0, the bottom
        for frame, offset in ((LEVEL, 0), (LEFT, SPACING), (RIGHT, -SPACING)):
            x = (middle + offset) % vs2.display.width
            world.sprite("ship.png", x=x, y=2, frame=frame)


def main():
    return Frames()
