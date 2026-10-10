"""Dream Garden: a shared, unhurried circular garden for Overkill 2026.

LEFT/RIGHT drift, hold A to slow the whole garden, B rests, X toggles audio.
A second controller can join at any time. Watching is also a way to play.
"""

from urandom import randrange

import vs2
from vs2.controls import A, B, X, LEFT, RIGHT, joy1, joy2

AWAKE, LEFT_POSE, RIGHT_POSE, ASLEEP = range(4)
DRIFT_SPEED = 0.45
REST_SPEED = 0.12
DRIFT_SPAWN_MS = 1800
REST_SPAWN_MS = 4000
SEED_DEPTH = 160
FLOWER_COUNT = 24
PATTERN_ROWS = 6


def garden_tiles(world):
    ground = world.tilemap("garden.png", columns=16, rows=16,
                           view_width=256, view_height=160)
    for row in range(16):
        for col in range(16):
            band = row % PATTERN_ROWS
            ground[col, row] = ((col + band) % 8
                                if (col + band * 3) % 5 == 0
                                else vs2.EMPTY_TILE)
    return ground


def centred_label(hud, text, y):
    label = hud.label("steel8x8.png", columns=len(text), y=y, text=text)
    label.x = -(len(text) * label.image.width) // 2
    return label


class Garden(vs2.Scene):
    # Waiting and watching are intentional here. Y/Back still exits.
    idle_timeout = None

    def __init__(self, joined=False):
        vs2.Scene.__init__(self)
        self.joined = joined

    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)
        self.ground = garden_tiles(self.world)
        self.flowers = self.world.sprite_pool(
            "flowers.png", count=FLOWER_COUNT, on_empty=vs2.RECYCLE)
        self.seeds = self.world.sprite_pool("seed.png", count=16)
        self.dreamer = self.world.sprite("dreamer.png", x=-9, y=0)
        self.friend = self.world.sprite("dreamer.png", x=55, y=0,
                                        frame=4, visible=self.joined)
        self.mood = self.hud.label("steel8x8.png", columns=5, x=108, y=1,
                                   flip_x=True, flip_y=True, text="DRIFT")
        self.scroll = 0
        self.dream_time = 0
        self.slow = False
        self.sound_on = False
        self.speed = DRIFT_SPEED
        self.spawn_ms = DRIFT_SPAWN_MS
        for index in range(4):
            self.flowers.spawn(x=23 + index * 64, y=24, frame=index * 2)
        self.call_later(self.spawn_ms, self.spawn_seed)

    def steer(self, dreamer, controller, base_frame):
        direction = controller.held(LEFT) - controller.held(RIGHT)
        dreamer.x = (dreamer.x + direction) % vs2.display.width
        pose = (ASLEEP if controller.held(A) else
                LEFT_POSE if direction > 0 else
                RIGHT_POSE if direction < 0 else AWAKE)
        dreamer.frame = base_frame + pose

    def update(self):
        if joy1.just_pressed(B) or joy2.just_pressed(B):
            flowers = [(flower.x, flower.frame) for flower in self.flowers]
            vs2.audio.stop_music()
            return self.switch(Rest(flowers))

        if not self.joined and (joy2.held(LEFT) or joy2.held(RIGHT)
                                or joy2.held(A)):
            self.joined = True
            self.friend.show()
        self.steer(self.dreamer, joy1, 0)
        if self.joined:
            self.steer(self.friend, joy2, 4)

        slow = joy1.held(A) or (self.joined and joy2.held(A))
        if slow != self.slow:
            self.slow = slow
            self.mood.text = "REST" if slow else "DRIFT"
        self.speed = REST_SPEED if slow else DRIFT_SPEED
        self.spawn_ms = REST_SPAWN_MS if slow else DRIFT_SPAWN_MS
        self.dream_time = (self.dream_time + self.speed) % 96
        self.scroll = (self.scroll + self.speed) % (
            PATTERN_ROWS * self.ground.tile_height)
        self.ground.view_y = self.scroll
        phase = int(self.dream_time // 6) % 2
        for flower in self.flowers:
            flower.frame = (flower.frame // 2) * 2 + phase
        self.move_seeds()

        if joy1.just_pressed(X) or joy2.just_pressed(X):
            self.sound_on = not self.sound_on
            if self.sound_on:
                vs2.audio.music("lullaby", loop=True)
            else:
                vs2.audio.stop_music()

    def bloom(self, seed):
        centre = seed.x + seed.width // 2
        self.flowers.spawn(x=centre - 8, y=24, frame=randrange(4) * 2)
        self.seeds.despawn(seed)
        if self.sound_on:
            vs2.audio.sound("bloom")

    def move_seeds(self):
        for seed in self.seeds:
            seed.y -= self.speed
            seed.frame = int(self.dream_time // 3) % seed.image.frames
            if (seed.overlaps(self.dreamer)
                    or (self.joined and seed.overlaps(self.friend))):
                self.bloom(seed)
            elif seed.y < -seed.image.height:
                self.seeds.despawn(seed)  # passing seeds cause no harm

    def spawn_seed(self):
        self.seeds.spawn(x=randrange(vs2.display.width), y=SEED_DEPTH)
        # Already scheduled seeds keep their deadline. Subsequent gaps adapt.
        self.call_later(self.spawn_ms, self.spawn_seed)


class Title(vs2.Scene):
    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "DREAM GARDEN", y=1)
        centred_label(hud, "A TO DRIFT", y=13)
        centred_label(hud, "HOLD A: SLOW", y=25)

    def update(self):
        if joy1.just_pressed(A) or joy2.just_pressed(A):
            self.switch(Garden(joined=joy2.held(A)))


class Rest(vs2.Scene):
    idle_timeout = None

    def __init__(self, flowers):
        vs2.Scene.__init__(self)
        self.saved_flowers = flowers

    def build(self):
        world = self.layer("world", projection=vs2.TUNNEL)
        flowers = world.sprite_pool("flowers.png", count=FLOWER_COUNT)
        for x, frame in self.saved_flowers:
            # Settle inward, leaving the rim clear for the invitation.
            flowers.spawn(x=x, y=48, frame=frame)
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "REST A WHILE", y=1)
        centred_label(hud, "A: NEW DREAM", y=14)

    def update(self):
        if joy1.just_pressed(A) or joy2.just_pressed(A):
            self.switch(Garden(joined=joy2.held(A)))


def main():
    return Title()
