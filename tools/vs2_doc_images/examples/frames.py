"""One sprite per frame of the tutorial game's ship (level, turned left, turned
right), side by side on the bottom of the disc, with the level ship in the middle.

x counts up from right to left at the bottom of the disc, so the frame for a left
turn goes at a larger x. A gap of 6 columns separates neighbours. The width comes from the sprite, so a change to
the art cannot throw the spacing off."""

import vs2

GAP = 6                      # columns between neighbouring ships
LEVEL, LEFT, RIGHT = range(3)


class Frames(vs2.Scene):
    def build(self):
        world = self.layer("world", projection=vs2.TUNNEL)
        ships = {frame: world.sprite("ship.png", y=2, frame=frame)
                 for frame in (LEVEL, LEFT, RIGHT)}
        width = ships[LEVEL].width
        # x = 0 is the bottom of the disc; centre the level ship on it.
        for frame, offset in ((LEVEL, 0), (LEFT, width + GAP), (RIGHT, -(width + GAP))):
            ships[frame].x = (offset - width // 2) % vs2.display.width


def main():
    return Frames()
