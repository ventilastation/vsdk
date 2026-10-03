# Trench Run, chapter 3: the ship leans into its turns.
import vs2
from vs2.controls import *

LEVEL, TURN_LEFT, TURN_RIGHT = range(3)      # the frames of ship.png


class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.ship = self.world.sprite("ship.png", y=0)
        self.ship.x = -(self.ship.width // 2)     # centred on x = 0, the bottom of the disc

    def update(self):
        # +1 for left, -1 for right, 0 for neither (or both held: they cancel).
        # At the bottom of the disc x counts up toward the left.
        steer = joy1.held(LEFT) - joy1.held(RIGHT)
        self.ship.x = (self.ship.x + steer) % vs2.display.width
        if steer > 0:
            self.ship.frame = TURN_LEFT
        elif steer < 0:
            self.ship.frame = TURN_RIGHT
        else:
            self.ship.frame = LEVEL


def main():
    return Game()
