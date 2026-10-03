# Trench Run, chapter 2: a ship that flies all the way round.
import vs2
from vs2.controls import *


class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.ship = self.world.sprite("ship.png", x=128, y=0)

    def update(self):
        if joy1.held(LEFT):
            self.ship.x = (self.ship.x - 1) % vs2.display.width
        if joy1.held(RIGHT):
            self.ship.x = (self.ship.x + 1) % vs2.display.width


def main():
    return Game()
