"""Rim Runner: run round the inside of the rim and collect every egg.

The idea for this game is by @borisvanschooten. It is one of the five games in
the Ludum Dare 60 entry "Circular Arcade", originally published at
https://tmtg.nl/ludumdare/ld60/jgame.html?game=jgame-games/ld60/
This is a port of it to Ventilastation (see games/ld60/README.md).

The ground is the outer ring of the disc and "up" is toward the centre, so you
run like a hamster in a wheel, with your head toward the middle. There are
holes in the rim (fall in and you are gone), platforms floating above it and
birds that kill you unless you land on them first. The camera turns with you:
you always run at the bottom of the disc.

Controls: left and right run, up or A jumps. Left runs toward higher x.
Either controller plays.
"""

from urandom import randrange

import vs2
from vs2.controls import *

W = vs2.display.width      # 256 columns round the disc
TILE = 8
COLS = W // TILE
ROWS = 40                  # tiles from the rim inward; the level is much taller than the view
VIEW_ROWS = 18             # how many rows of it are drawn at a time
VIEW_H = VIEW_ROWS * TILE
# The camera scrolls inward with the runner, keeping the runner's feet this deep,
# so there is room between the runner and the rim. Depth 12 is about eight LEDs in
# from the rim, where things are still big and clear; things near the middle of
# the disc are hard to read, so the view only stops following when the level runs
# out above you.
PLAYER_DEPTH = 12
# But it never scrolls outward past the lowest floor: only this many pixels of
# ground are shown below it, rather than spending the outer LEDs on solid ground.
GROUND_SHOWN = 4
BIRD_TOP = 16              # birds fly between this row and row 5
ANCHOR = -TILE // 2        # the player is drawn at the bottom of the disc
BIRDS = 16
# Platforms float this many tiles above the rim, and the small ones above those.
# A jump rises about 4.6 tiles, so each step up has to be 4 or less to be reachable
# (the original game put them 5 above, out of reach of a jump from the rim).
LOW = 4
HIGH = 8

RUNNER, JUMP_FRAME, BIRD, BOOM = 0, 2, 3, 5     # frames of sprites.png
BOOM_FRAMES = 3
EGG = 16                   # a frame of tiles.png; 0..15 are the wall tiles
NO_TILE = vs2.EMPTY_TILE

RUN = 1.2                  # columns per tick
JUMP = 2.4                 # rows of depth per tick, going up
GRAVITY = 0.08
FALL_MAX = 2.4
STOMP = 2.0
BEST = "best"


def held(button):
    """Whether ``button`` is down on either controller: it is a one-player game,
    so both sticks and both sets of buttons play it."""
    return joy1.held(button) or joy2.held(button)


def pressed(button):
    """Whether ``button`` went down on this tick, on either controller."""
    return joy1.just_pressed(button) or joy2.just_pressed(button)


def format_time(ticks):
    tenths = ticks * 30 // 100
    return "%d.%d" % (tenths // 10, tenths % 10)


def centred_label(layer, text, y, font="tinyfont_white.png"):
    """A label for ``text`` in a 4x6 tinyfont, centred on the bottom of the disc,
    where it reads upright. The tinyfonts are ASCII, 4 columns per character."""
    label = layer.label(font, columns=len(text), x=0, y=y, text=text)
    label.x = -(len(text) * label.image.width) // 2
    return label


# How far in from the rim the end-of-game heading sits: a little inward reads
# better than right on the rim.
RESULT_Y = 6


def title_label(layer, text, y=1):
    """A heading in rainbow8x8.png, centred on the top of the disc: the game's
    name, or how the game ended. A label there would read upside down, so it is
    flipped on both axes."""
    label = layer.label("rainbow8x8.png", columns=len(text), x=0, y=y, text=text,
                        flip_x=True, flip_y=True)
    label.x = W // 2 - (len(text) * label.image.width) // 2
    return label


class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)

        self.solid = bytearray(COLS * ROWS)
        self.cells = bytearray([NO_TILE] * (COLS * ROWS))
        self.rim = self.world.tilemap(
            "tiles.png", columns=COLS, rows=ROWS, cells=self.cells,
            view_width=W, view_height=VIEW_H)
        self.eggs = self.build_rim()
        self.autotile()

        self.birds = []
        for col in range(1, COLS, 2):
            bird = self.world.sprite("sprites.png", frame=BIRD)
            bird.wx = col * TILE
            bird.wy = randrange(8, BIRD_TOP) * TILE
            bird.vx = bird.vy = 0
            bird.turn = 0
            bird.alive = True
            self.birds.append(bird)
        self.runner = self.world.sprite("sprites.png", frame=RUNNER)
        self.booms = []
        for _ in range(3):
            boom = self.world.sprite("sprites.png", frame=BOOM, visible=False)
            boom.wx = boom.wy = boom.age = 0
            boom.active = False
            self.booms.append(boom)

        # "TIME" then four digits, centred on the top of the disc, where text
        # has to be flipped both ways to read upright.
        self.hud.label("steel8x8.png", columns=4, x=92, y=1, text="TIME",
                       flip_x=True, flip_y=True)
        self.clock = self.hud.label("steel8x8.png", columns=4, x=132, y=1,
                                    flip_x=True, flip_y=True)

        self.wx = float(TILE)
        self.wy = float(TILE * 3)
        self.vy = 0.0
        self.grounded = False
        self.facing = 1
        self.ticks = 0
        self.playing = True
        self.dead = False
        self.show_clock()
        self.place()

    # -- the level -------------------------------------------------------

    def build_rim(self):
        """A rim with a hole every fourth column, platforms above it and eggs
        on them. Returns how many eggs there are."""
        eggs = 0
        height = 2
        lowest = 99
        for col in range(COLS):
            if col % 4 == 3:
                height = randrange(1, 5)
                self.put(col, height + LOW)
                self.put(col + 1, height + LOW)
                self.put(col + 3, height + HIGH)
                if randrange(2):
                    eggs += self.egg(col + randrange(1, 3), height + LOW + 1)
                if randrange(10) < 7:
                    eggs += self.egg(col + 3, height + HIGH + 1)
            else:
                for row in range(height + 1):
                    self.put(col, row)
                lowest = min(lowest, height)
                if randrange(5) == 0:
                    eggs += self.egg(col, height + 1)
        # Depth of the surface of the lowest floor.
        self.floor_depth = (lowest + 1) * TILE
        return eggs

    def put(self, col, row):
        self.solid[row * COLS + col % COLS] = 1

    def egg(self, col, row):
        index = row * COLS + col % COLS
        if self.solid[index]:
            return 0
        self.cells[index] = EGG
        return 1

    def is_solid(self, col, row):
        if row < 0 or row >= ROWS:
            return False
        return self.solid[row * COLS + col % COLS] == 1

    def autotile(self):
        """Pick each solid tile by which of its neighbours are open, so every
        surface is outlined in light."""
        for row in range(ROWS):
            for col in range(COLS):
                if self.solid[row * COLS + col]:
                    mask = 0
                    if not self.is_solid(col + 1, row):
                        mask |= 1
                    if not self.is_solid(col - 1, row):
                        mask |= 2
                    if not self.is_solid(col, row + 1):
                        mask |= 4
                    if row and not self.is_solid(col, row - 1):
                        mask |= 8
                    self.cells[row * COLS + col] = mask

    def solid_at(self, px, py):
        if py < 0:
            return False
        return self.is_solid(int(px) // TILE, int(py) // TILE)

    # -- the game ----------------------------------------------------------

    def update(self):
        if self.playing:
            self.ticks += 1
            self.run()
            for bird in self.birds:
                if bird.alive:
                    self.fly(bird)
            self.check_birds()
            if self.ticks % 33 == 0:
                self.show_clock()
        self.move_booms()
        self.place()

    def run(self):
        # Left is toward higher x at the bottom of the disc.
        step = held(LEFT) - held(RIGHT)
        if step:
            self.facing = step
            new_x = (self.wx + step * RUN) % W
            ahead = new_x + (TILE - 2 if step > 0 else 1)
            if not (self.solid_at(ahead, self.wy + 1) or self.solid_at(ahead, self.wy + 6)):
                self.wx = new_x
        left, right = self.wx + 1, self.wx + TILE - 2
        if self.grounded:
            if held(UP) or held(A):
                self.vy = JUMP
                self.grounded = False
                vs2.audio.sound("jump")
            elif not (self.solid_at(left, self.wy - 1) or self.solid_at(right, self.wy - 1)):
                self.grounded = False
        if not self.grounded:
            self.vy = max(self.vy - GRAVITY, -FALL_MAX)
            new_y = self.wy + self.vy
            if self.vy < 0:
                if self.solid_at(left, new_y) or self.solid_at(right, new_y):
                    self.wy = (int(new_y) // TILE + 1) * TILE
                    self.vy = 0.0
                    self.grounded = True
                else:
                    self.wy = new_y
            else:
                if self.solid_at(left, new_y + 7) or self.solid_at(right, new_y + 7):
                    self.vy = 0.0
                else:
                    self.wy = new_y
        self.pick_eggs()
        if self.wy < -TILE + 1 or self.wy > (ROWS - 1) * TILE:
            self.lose()

    def pick_eggs(self):
        col = int(self.wx + TILE / 2) // TILE % COLS
        for row in (int(self.wy + 2) // TILE, int(self.wy + 6) // TILE):
            if 0 <= row < ROWS and self.cells[row * COLS + col] == EGG:
                self.cells[row * COLS + col] = NO_TILE
                self.eggs -= 1
                vs2.audio.sound("pickup")
                if not self.eggs:
                    self.win()

    def fly(self, bird):
        if bird.turn <= 0:
            bird.turn = randrange(28, 56)
            bird.vx = (randrange(-30, 31)) * 0.024
            bird.vy = (randrange(-30, 31)) * 0.024
        bird.turn -= 1
        bird.wx = (bird.wx + bird.vx) % W
        bird.wy = min(max(bird.wy + bird.vy, 5 * TILE), BIRD_TOP * TILE)
        bird.frame = BIRD + (self.ticks // 5) % 2

    def check_birds(self):
        for bird in self.birds:
            if not bird.alive or not self.playing:
                continue
            dx = (bird.wx - self.wx + W // 2) % W - W // 2
            dy = bird.wy - self.wy
            if -6 < dx < 6 and -6 < dy < 6:
                if dy < -2:                     # landed on it from above
                    bird.alive = False
                    bird.hide()
                    self.boom(bird.wx, bird.wy)
                    vs2.audio.sound("explo")
                    self.vy = max(self.vy, 0) + STOMP
                    self.grounded = False
                else:
                    self.lose()

    def boom(self, wx, wy):
        for boom in self.booms:
            if not boom.active:
                boom.wx = wx
                boom.wy = wy
                boom.age = 0
                boom.frame = BOOM
                boom.active = True
                boom.show()
                return

    def move_booms(self):
        for boom in self.booms:
            if boom.active:
                boom.age += 1
                if boom.age >= BOOM_FRAMES * 4:
                    boom.active = False
                    boom.hide()
                else:
                    boom.frame = BOOM + boom.age // 4

    def lose(self):
        if not self.playing:
            return
        self.playing = False
        self.dead = True
        self.runner.hide()
        self.boom(self.wx, max(self.wy, 0))
        vs2.audio.sound("die")
        self.call_later(1000, self.finish, False)

    def win(self):
        if not self.playing:
            return
        self.playing = False
        vs2.audio.sound("win")
        self.call_later(800, self.finish, True)

    def finish(self, won):
        self.switch(Result(won, self.ticks))

    def show_clock(self):
        self.clock.set_number(self.ticks * 30 // 1000, width=4, pad=" ")

    def place(self):
        """Put everything on the disc, with the camera on the runner."""
        cam = int(self.wx)
        follow = max(self.wy - PLAYER_DEPTH, self.floor_depth - GROUND_SHOWN, 0)
        cam_y = int(min(follow, ROWS * TILE - VIEW_H))
        self.rim.x = ANCHOR - cam
        self.rim.view_y = cam_y
        self.put_sprite(self.runner, self.wx, self.wy, cam, cam_y)
        if self.dead:
            self.runner.hide()
        # The picture faces screen-right, which at the bottom of the disc is
        # toward lower x.
        self.runner.flip_x = self.facing > 0
        if not self.grounded:
            self.runner.frame = JUMP_FRAME
        else:
            self.runner.frame = RUNNER + (self.ticks // 4) % 2 if held(LEFT) or held(RIGHT) else RUNNER
        for bird in self.birds:
            if bird.alive:
                self.put_sprite(bird, bird.wx, bird.wy, cam, cam_y)
                bird.flip_x = bird.vx > 0
        for boom in self.booms:
            if boom.active:
                self.put_sprite(boom, boom.wx, boom.wy, cam, cam_y)

    def put_sprite(self, sprite, wx, wy, cam, cam_y):
        """Place a sprite at world (wx, wy); hidden when it is out of view."""
        sprite.x = (ANCHOR + wx - cam) % W
        sprite.y = wy - cam_y
        sprite.visible = -TILE < sprite.y < VIEW_H


class Title(vs2.Scene):
    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        title_label(hud, "RIM RUNNER")
        best = vs2.saves.load(BEST, 0)
        centred_label(hud, "BEST " + format_time(best) if best else "ARROWS  UP=JUMP", y=8)
        centred_label(hud, "PRESS A", y=1, font="tinyfont_red.png")

    def update(self):
        if pressed(A):
            self.switch(Game())


class Result(vs2.Scene):
    def __init__(self, won, ticks):
        vs2.Scene.__init__(self)
        self.won = won
        self.ticks = ticks
        self.best = vs2.saves.load(BEST, 0)
        self.new_best = won and (not self.best or ticks < self.best)
        if self.new_best:
            self.best = ticks
            vs2.saves.save(BEST, ticks)

    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        if self.new_best:
            title_label(hud, "NEW BEST!", y=RESULT_Y)
        else:
            title_label(hud, "ALL EGGS!" if self.won else "GAME OVER", y=RESULT_Y)
        centred_label(hud, "TIME " + format_time(self.ticks), y=8)
        centred_label(hud, "PRESS A", y=1, font="tinyfont_red.png")

    def update(self):
        if pressed(A):
            self.switch(Game())


def main():
    return Title()
