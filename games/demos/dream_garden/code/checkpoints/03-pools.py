"""Runnable presentation checkpoint: 03-pools."""
import vs2
from vs2.controls import A, B, LEFT, RIGHT, joy1

SEED_SPEED_RATIO = 0.85

class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.seeds = self.world.sprite_pool("seed.png", count=16)
        self.flowers = self.world.sprite_pool("flowers.png", count=24, on_empty=vs2.RECYCLE)
        self.dreamer = self.world.sprite("dreamer.png", y=0)
        self.dreamer.x = -(self.dreamer.width // 2)
        self.speed = 0.45
        self.spawn_ms = 1800
        self.dream_time = 0
        self.seeds.spawn(x=100, y=160)

    def update(self):
        steer = joy1.held(LEFT) - joy1.held(RIGHT)
        self.dreamer.x = (self.dreamer.x + steer) % vs2.display.width
        self.dreamer.frame = (3 if joy1.held(A) else 1 if steer > 0 else
                              2 if steer < 0 else 0)
        self.dream_time = (self.dream_time + self.speed) % 96
        frame = int(self.dream_time // 3) % self.image("seed.png").frames
        for seed in self.seeds:
            seed.y -= self.speed * SEED_SPEED_RATIO
            seed.frame = frame
            if seed.y < -seed.image.height:
                self.seeds.despawn(seed)

def main():
    return Game()
