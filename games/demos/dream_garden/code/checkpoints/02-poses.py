"""Runnable presentation checkpoint: 02-poses."""
import vs2
from vs2.controls import A, B, LEFT, RIGHT, joy1

class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.dreamer = self.world.sprite("dreamer.png", y=0)
        self.dreamer.x = -(self.dreamer.width // 2)

    def update(self):
        steer = joy1.held(LEFT) - joy1.held(RIGHT)
        self.dreamer.x = (self.dreamer.x + steer) % vs2.display.width
        self.dreamer.frame = (3 if joy1.held(A) else 1 if steer > 0 else
                              2 if steer < 0 else 0)

def main():
    return Game()
