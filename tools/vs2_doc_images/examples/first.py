import vs2
from vs2.controls import *


class MyGame(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.ship = self.world.sprite("ship.png", y=0)
        self.ship.x = -(self.ship.width // 2)     # centred on the bottom of the disc

    def update(self):
        if joy1.held(LEFT):
            self.ship.x += 1
        if joy1.held(RIGHT):
            self.ship.x -= 1


def main():
    return MyGame()
