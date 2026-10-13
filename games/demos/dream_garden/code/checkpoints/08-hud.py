"""Runnable presentation checkpoint: 08-hud."""
import vs2
from vs2.controls import A, B, LEFT, RIGHT, joy1
from urandom import randrange
from utime import ticks_ms, ticks_diff

HUD_EXIT_MS = 450


def slide_text_out(label, start_y, started):
    elapsed = ticks_diff(ticks_ms(), started)
    if elapsed >= HUD_EXIT_MS:
        label.hide()
        return None
    label.y = start_y - (start_y + label.tile_height) * elapsed / HUD_EXIT_MS
    return started


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
        self.speed = 0.45
        self.spawn_ms = 1800
        self.dream_time = 0
        self.call_later(self.spawn_ms, self.spawn_seed)
        self.scroll = 0
        hud = self.layer("hud", projection=vs2.HUD)
        self.mood = hud.label("steel8x8.png", columns=5, x=108, y=1,
                              flip_x=True, flip_y=True, text="RELAX", visible=False)
        self.mood_exit = None
        self.slow = False
        self.slow_ready = not joy1.held(A)

    def update(self):
        if not joy1.held(A):
            self.slow_ready = True
        slow = self.slow_ready and joy1.held(A)
        if slow != self.slow:
            self.slow = slow
            if slow:
                self.mood.y = 1
                self.mood.show()
                self.mood_exit = None
            else:
                self.mood_exit = ticks_ms()
        if self.mood_exit is not None:
            self.mood_exit = slide_text_out(self.mood, 1, self.mood_exit)
        self.speed = 0.12 if slow else 0.45
        self.spawn_ms = 4000 if slow else 1800
        steer = joy1.held(LEFT) - joy1.held(RIGHT)
        self.dreamer.x = (self.dreamer.x + steer) % vs2.display.width
        if steer:
            self.last_direction = steer
        self.dreamer.frame = (3 if slow else 1 if steer > 0 else
                              2 if steer < 0 else 0)
        self.dream_time = (self.dream_time + self.speed) % 96
        frame = int(self.dream_time // 3) % self.image("seed.png").frames
        self.scroll = (self.scroll + self.speed) % (PATTERN_ROWS * self.ground.tile_height)
        self.ground.view_y = self.scroll
        for flower in self.flowers:
            flower.y += self.speed * SEED_SPEED_RATIO * 0.08
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
        centre += self.last_direction * self.dreamer.width * 0.75
        self.flowers.spawn(x=(centre - self.image("flowers.png").width // 2) % vs2.display.width,
                           y=self.dreamer.y, frame=randrange(4) * 2)
        self.seeds.despawn(seed)

def main():
    return Game()
