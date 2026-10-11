"""Runnable presentation checkpoint: 07-scroll."""
import vs2
from vs2.controls import A, B, LEFT, RIGHT, joy1
from urandom import randrange

class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.ground = self.world.tilemap("garden.png", columns=16, rows=16,
                                         view_width=256, view_height=160)
        for row in range(16):
            for col in range(16):
                band = row % 6
                self.ground[col, row] = ((col + band) % 8 if (col + band * 3) % 5 == 0
                                         else vs2.EMPTY_TILE)
        self.seeds = self.world.sprite_pool("seed.png", count=16)
        self.flowers = self.world.sprite_pool("flowers.png", count=24, on_empty=vs2.RECYCLE)
        self.dreamer = self.world.sprite("dreamer.png", y=0)
        self.dreamer.x = -(self.dreamer.width // 2)
        self.speed = 0.45
        self.spawn_ms = 1800
        self.dream_time = 0
        self.call_later(self.spawn_ms, self.spawn_seed)
        self.scroll = 0

    def update(self):
        steer = joy1.held(LEFT) - joy1.held(RIGHT)
        self.dreamer.x = (self.dreamer.x + steer) % vs2.display.width
        self.dreamer.frame = (3 if joy1.held(A) else 1 if steer > 0 else
                              2 if steer < 0 else 0)
        self.dream_time = (self.dream_time + self.speed) % 96
        frame = int(self.dream_time // 3) % self.image("seed.png").frames
        self.scroll = (self.scroll + self.speed) % (6 * self.ground.tile_height)
        self.ground.view_y = self.scroll
        for seed in self.seeds:
            seed.y -= self.speed
            seed.frame = frame
            if seed.overlaps(self.dreamer):
                self.bloom(seed)
            elif seed.y < -seed.image.height:
                self.seeds.despawn(seed)

    def spawn_seed(self):
        self.seeds.spawn(x=randrange(vs2.display.width), y=160)
        self.call_later(self.spawn_ms, self.spawn_seed)

    def bloom(self, seed):
        centre = seed.x + seed.width // 2
        self.flowers.spawn(x=centre - self.image("flowers.png").width // 2,
                           y=24, frame=randrange(4) * 2)
        self.seeds.despawn(seed)

def main():
    return Game()
