"""Runnable presentation checkpoint: 07-scroll."""
import vs2
from vs2.controls import A, B, LEFT, RIGHT, joy1
from urandom import randrange

PATTERN_ROWS = 12
SEED_SPEED_RATIO = 0.85
# (column, row, first tile, width in cells, height in cells)
CLOUD_PATCHES = ((1, 0, 0, 1, 1), (7, 1, 1, 2, 1), (11, 4, 3, 3, 2),
                 (5, 6, 9, 1, 1), (13, 8, 10, 2, 1), (1, 9, 12, 3, 2))


def cloud_tiles(air):
    ground = air.tilemap("clouds.png", columns=16, rows=22,
                         view_width=256, view_height=160)
    for base_row in range(0, ground.rows, PATTERN_ROWS):
        for col, row, first, width, height in CLOUD_PATCHES:
            for dy in range(height):
                target_row = base_row + row + dy
                if target_row < ground.rows:
                    for dx in range(width):
                        ground[col + dx, target_row] = first + dy * width + dx
    return ground


class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.air = self.layer("air", projection=vs2.TUNNEL)
        self.ground = cloud_tiles(self.air)
        self.seeds = self.air.sprite_pool("seed.png", count=16)
        self.flowers = self.world.sprite_pool("flowers.png", count=24, on_empty=vs2.RECYCLE)
        self.dreamer = self.world.sprite("dreamer.png", y=0)
        self.dreamer.x = -(self.dreamer.width // 2)
        self.last_direction = 1
        self.plant_side = 1
        self.moving = False
        self.speed = 0.45
        self.spawn_ms = 1800
        self.dream_time = 0
        self.call_later(self.spawn_ms, self.spawn_seed)
        self.scroll = 0

    def update(self):
        steer = joy1.held(LEFT) - joy1.held(RIGHT)
        self.dreamer.x = (self.dreamer.x + steer) % vs2.display.width
        self.moving = bool(steer)
        if steer:
            self.last_direction = steer
            self.plant_side = steer
        self.dreamer.frame = (3 if joy1.held(A) else 1 if steer > 0 else
                              2 if steer < 0 else 0)
        self.dream_time = (self.dream_time + 0.45) % 96
        frame = int(self.dream_time // 3) % self.image("seed.png").frames
        self.scroll = (self.scroll + 0.45) % (PATTERN_ROWS * self.ground.tile_height)
        self.ground.view_y = self.scroll
        for flower in self.flowers:
            flower.y += 0.45 * SEED_SPEED_RATIO * 0.08
            if flower.y >= 255:
                self.flowers.despawn(flower)
        for seed in self.seeds:
            seed.y -= self.speed * SEED_SPEED_RATIO
            seed.frame = frame
            if seed.overlaps(self.dreamer):
                self.bloom(seed)
            elif seed.y < -seed.image.height:
                self.seeds.despawn(seed)

    def spawn_seed(self):
        self.seeds.spawn(x=randrange(vs2.display.width), y=160)
        self.call_later(self.spawn_ms, self.spawn_seed)

    def bloom(self, seed):
        centre = self.dreamer.x + self.dreamer.width // 2
        centre += self.plant_side * self.dreamer.width * 0.75
        self.flowers.spawn(x=(centre - self.image("flowers.png").width // 2) % vs2.display.width,
                           y=self.dreamer.y, frame=randrange(4) * 2)
        if not self.moving:
            self.plant_side = -self.plant_side
        self.seeds.despawn(seed)

def main():
    return Game()
