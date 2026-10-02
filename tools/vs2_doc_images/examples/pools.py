import vs2
from vs2.controls import *

SHOT_SPEED = 3
SHOT_RANGE = 170


class Pools(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.ship = self.world.sprite("ship.png", x=128, y=0)
        self.shots = self.world.sprite_pool("shots.png", count=8)
        self.enemies = self.world.sprite_pool("enemy.png", count=16)
        self.booms = self.world.sprite_pool(
            "explosion.png", count=4, on_empty=vs2.RECYCLE)
        for i in range(7):
            self.enemies.spawn(x=128 + (i - 3) * 14, y=70)

    def update(self):
        if joy1.just_pressed(A):
            shot = self.shots.spawn(x=self.ship.x, y=self.ship.y + 4)
            if shot is None:
                return

        for shot in self.shots:
            shot.y += SHOT_SPEED
            if shot.y > SHOT_RANGE:
                self.shots.despawn(shot)
                continue

            enemy = shot.first_overlap(self.enemies)
            if enemy:
                self.enemies.despawn(enemy)
                self.booms.spawn(x=enemy.x, y=enemy.y)
                self.shots.despawn(shot)


def main():
    return Pools()
