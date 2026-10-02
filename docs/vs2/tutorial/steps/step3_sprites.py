# Trench Run, chapter 3: the ship leans into its turns.
import vs2
from vs2.controls import *

LEVEL, TURN_LEFT, TURN_RIGHT = range(3)      # the frames of ship.png


class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.ship = self.world.sprite("ship.png", x=128, y=0)

    def update(self):
        # -1 for left, +1 for right, 0 for neither (or both held: they cancel).
        steer = joy1.held(RIGHT) - joy1.held(LEFT)
        self.ship.x = (self.ship.x + steer) % vs2.display.width
        if steer < 0:
            self.ship.frame = TURN_LEFT
        elif steer > 0:
            self.ship.frame = TURN_RIGHT
        else:
            self.ship.frame = LEVEL


def main():
    return Game()
