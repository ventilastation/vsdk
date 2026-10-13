"""Dream Garden: a shared, unhurried circular garden for Overkill 2026.

LEFT/RIGHT drift, hold A to relax the whole garden, B rests.
A second controller can join at any time. Watching is also a way to play.
"""

from urandom import randrange
from utime import ticks_ms, ticks_diff

import vs2
from vs2.controls import A, B, LEFT, RIGHT, joy1, joy2

AWAKE, LEFT_POSE, RIGHT_POSE, ASLEEP = range(4)
DRIFT_SPEED = 0.45
SLOW_SPEED = 0.12
DRIFT_SPAWN_MS = 1800
SLOW_SPAWN_MS = 4000
SEED_DEPTH = 160
FLOWER_COUNT = 24
PATTERN_ROWS = 12
SEED_SPEED_RATIO = 0.85
# (column, row, first tile, width in cells, height in cells)
CLOUD_PATCHES = ((1, 0, 0, 1, 1), (7, 1, 1, 2, 1), (11, 4, 3, 3, 2),
                 (5, 6, 9, 1, 1), (13, 8, 10, 2, 1), (1, 9, 12, 3, 2))
FLOWER_DRIFT_RATIO = 0.08
FLOWER_DEPTH = 255
GLOW_FRAMES = (1, 2, 3, 2, 1, 0)
GLOW_FRAME_TICKS = 6
HUD_EXIT_MS = 450


def slide_text_out(label, start_y, started):
    elapsed = ticks_diff(ticks_ms(), started)
    if elapsed >= HUD_EXIT_MS:
        label.hide()
        return None
    label.y = start_y - (start_y + label.tile_height) * elapsed / HUD_EXIT_MS
    return started



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


def centred_label(hud, text, y):
    label = hud.label("steel8x8.png", columns=len(text), y=y, text=text)
    label.x = -(len(text) * label.image.width) // 2
    return label


class Garden(vs2.Scene):
    def __init__(self, joined=False):
        vs2.Scene.__init__(self)
        self.joined = joined
        self.slow_ready1 = not joy1.held(A)
        self.slow_ready2 = not joy2.held(A)

    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.air = self.layer("air", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)
        self.ground = cloud_tiles(self.air)
        self.flowers = self.world.sprite_pool(
            "flowers.png", count=FLOWER_COUNT, on_empty=vs2.RECYCLE)
        self.seeds = self.air.sprite_pool("seed.png", count=16)
        self.dreamer = self.world.sprite("dreamer.png", y=0)
        self.dreamer.x = -(self.dreamer.width // 2)
        self.friend = self.world.sprite("dreamer.png", x=64 - self.dreamer.width // 2, y=0,
                                        frame=4, visible=self.joined)
        self.mood = self.hud.label("steel8x8.png", columns=5, x=108, y=1,
                                   flip_x=True, flip_y=True, text="RELAX", visible=False)
        self.mood_exit = None
        self.flower_half = self.image("flowers.png").width // 2
        self.flower_phase = 0
        self.scroll = 0
        self.dream_time = 0
        self.slow = False
        # Start toward LEFT; stopping keeps each player’s last steering direction.
        self.last_direction1 = 1
        self.last_direction2 = 1
        self.seed_glows = {}
        self.speed = DRIFT_SPEED
        self.spawn_ms = DRIFT_SPAWN_MS
        self.call_later(self.spawn_ms, self.spawn_seed)

    def steer(self, dreamer, controller, base_frame, sleeping):
        direction = controller.held(LEFT) - controller.held(RIGHT)
        dreamer.x = (dreamer.x + direction) % vs2.display.width
        if direction:
            if dreamer is self.friend:
                self.last_direction2 = direction
            else:
                self.last_direction1 = direction
        pose = (ASLEEP if sleeping else
                LEFT_POSE if direction > 0 else
                RIGHT_POSE if direction < 0 else AWAKE)
        dreamer.frame = base_frame + pose

    def update(self):
        if joy1.just_pressed(B) or joy2.just_pressed(B):
            flowers = [(flower.x, flower.y, flower.frame) for flower in self.flowers]
            return self.switch(Rest(flowers))

        if not self.joined and (joy2.held(LEFT) or joy2.held(RIGHT)
                                or joy2.held(A)):
            self.joined = True
            self.friend.show()
        if not joy1.held(A):
            self.slow_ready1 = True
        if not joy2.held(A):
            self.slow_ready2 = True
        slow1 = self.slow_ready1 and joy1.held(A)
        slow2 = self.slow_ready2 and self.joined and joy2.held(A)
        self.steer(self.dreamer, joy1, 0, slow1)
        if self.joined:
            self.steer(self.friend, joy2, 4, slow2)

        slow = slow1 or slow2
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
        self.speed = SLOW_SPEED if slow else DRIFT_SPEED
        self.spawn_ms = SLOW_SPAWN_MS if slow else DRIFT_SPAWN_MS
        self.dream_time = (self.dream_time + self.speed) % 96
        self.scroll = (self.scroll + self.speed) % (
            PATTERN_ROWS * self.ground.tile_height)
        self.ground.view_y = self.scroll
        phase = int(self.dream_time // 6) % 2
        if phase != self.flower_phase:
            self.flower_phase = phase
            for flower in self.flowers:
                flower.frame = (flower.frame // 2) * 2 + phase
        for flower in self.flowers:
            flower.y += self.speed * SEED_SPEED_RATIO * FLOWER_DRIFT_RATIO
            if flower.y >= FLOWER_DEPTH:
                self.flowers.despawn(flower)
        self.move_seeds()

    def bloom(self, seed, player):
        side = self.last_direction2 if player is self.friend else self.last_direction1
        centre = player.x + player.width // 2
        self.flowers.spawn(x=(centre + side * player.width * 0.75
                              - self.flower_half) % vs2.display.width, y=player.y,
                           frame=randrange(4) * 2 + self.flower_phase)
        self.retire_seed(seed)

    def move_seeds(self):
        for seed in self.seeds:
            seed.y -= self.speed * SEED_SPEED_RATIO
            self.glow_seed(seed)
            if seed.overlaps(self.dreamer):
                self.bloom(seed, self.dreamer)
            elif self.joined and seed.overlaps(self.friend):
                self.bloom(seed, self.friend)
            elif seed.y < -seed.image.height:
                self.retire_seed(seed)  # passing seeds cause no harm

    def glow_seed(self, seed):
        state = self.seed_glows.get(seed)
        if state is None:
            state = [randrange(90, 241), 0]
            self.seed_glows[seed] = state
        if state[0] > 0:
            state[0] -= 1
            seed.frame = 0
            return
        seed.frame = GLOW_FRAMES[state[1] // GLOW_FRAME_TICKS]
        state[1] += 1
        if state[1] == len(GLOW_FRAMES) * GLOW_FRAME_TICKS:
            state[0] = randrange(90, 241)
            state[1] = 0

    def retire_seed(self, seed):
        self.seed_glows.pop(seed, None)
        self.seeds.despawn(seed)

    def spawn_seed(self):
        self.seeds.spawn(x=randrange(vs2.display.width), y=SEED_DEPTH)
        # Already scheduled seeds keep their deadline. Subsequent gaps adapt.
        self.call_later(self.spawn_ms, self.spawn_seed)


class Title(vs2.Scene):
    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "DREAM GARDEN", y=1)
        centred_label(hud, "A TO BEGIN", y=13)
        centred_label(hud, "HOLD A: RELAX", y=25)

    def update(self):
        if joy1.just_pressed(A) or joy2.just_pressed(A):
            self.switch(Garden(joined=joy2.held(A)))


class Rest(vs2.Scene):
    def __init__(self, flowers):
        vs2.Scene.__init__(self)
        self.saved_flowers = flowers

    def build(self):
        world = self.layer("world", projection=vs2.TUNNEL)
        flowers = world.sprite_pool("flowers.png", count=FLOWER_COUNT)
        for x, y, frame in self.saved_flowers:
            flowers.spawn(x=x, y=y, frame=frame)
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "REST A WHILE", y=1)
        centred_label(hud, "A: NEW DREAM", y=14)

    def update(self):
        if joy1.just_pressed(A) or joy2.just_pressed(A):
            self.switch(Garden(joined=joy2.held(A)))


def main():
    return Title()
