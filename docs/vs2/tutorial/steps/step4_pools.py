# Trench Run, chapter 4: enemies come down the tunnel.
import vs2
from vs2.controls import *

LEVEL, TURN_LEFT, TURN_RIGHT = range(3)      # the frames of ship.png
ENEMY_SPEED = 0.5    # depth units per tick, toward the ship
ENEMY_START = 160    # depth at which enemies appear


class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.ship = self.world.sprite("ship.png", x=128, y=0)
        self.enemies = self.world.sprite_pool("enemy.png", count=16)
        for i in range(5):
            self.enemies.spawn(x=i * 51, y=ENEMY_START)
        self.ticks = 0                              # counts update() calls

    def update(self):
        self.ticks += 1

        # -1 for left, +1 for right, 0 for neither (or both held: they cancel).
        steer = joy1.held(RIGHT) - joy1.held(LEFT)
        self.ship.x = (self.ship.x + steer) % vs2.display.width
        if steer < 0:
            self.ship.frame = TURN_LEFT
        elif steer > 0:
            self.ship.frame = TURN_RIGHT
        else:
            self.ship.frame = LEVEL

        self.move_enemies()

    def move_enemies(self):
        for enemy in self.enemies:
            enemy.y -= ENEMY_SPEED
            enemy.frame = (self.ticks // 6) % enemy.image.frames
            if enemy.y < -enemy.image.height:
                self.enemies.despawn(enemy)      # flew past the ship


def main():
    return Game()
