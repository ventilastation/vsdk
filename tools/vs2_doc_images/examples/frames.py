"""One sprite per frame of the tutorial game's drone, side by side on the bottom
of the disc. Increasing x runs right to left there, so the frames are laid out at
decreasing x. The spacing leaves a gap between them."""

import vs2

WIDTH = 16           # columns in one frame of the strip
SPACING = 22         # columns between neighbours, so there is a gap


class Frames(vs2.Scene):
    def build(self):
        world = self.layer("world", projection=vs2.TUNNEL)
        for frame in range(4):
            x = (int(1.5 * SPACING) - WIDTH // 2 - frame * SPACING) % vs2.display.width
            world.sprite("enemy.png", x=x, y=2, frame=frame)


def main():
    return Frames()
