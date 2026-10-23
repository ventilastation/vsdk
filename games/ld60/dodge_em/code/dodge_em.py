"""Dodge 'Em: eat every pill on the circular race track without crashing.

One of five LD60 "Circular Arcade" concept games (games/ld60). Five lanes run
round the disc, walled off from each other except for four gaps. You drive
round the track one way, the red cars come the other way and slip through the
gaps to cut you off. The camera turns with you: you always drive at the top of
the disc.

Controls: up and down change lane when you are at a gap, right speeds you up and
left slows you down.
"""

from urandom import randrange

import vs2
from vs2.controls import *

W = vs2.display.width      # 256 columns round the disc
TILE = 8
COLS = W // TILE
ROWS = 12
ANCHOR = W // 2 - TILE // 2    # the player is drawn at the top of the disc
LANES = (1, 3, 5, 7, 9)        # rows you can drive on; the even rows are walls
# The whole track is drawn this far in from where its rows say, so the top wall,
# row 0, shows as just its last line of pixels: one LED right on the rim.
SHIFT = -(TILE - 1)
GAP_EVERY = 8                  # a gap in the walls every this many columns...
GAP_AT = 6                     # ...at this column

CAR, ENEMY, BOOM = 0, 2, 4     # frames of sprites.png
BOOM_FRAMES = 3
PILL = 16                      # a frame of tiles.png; 0..15 are the wall tiles
NO_TILE = vs2.EMPTY_TILE

# Ticks a car takes to cross one tile.
SLOW, NORMAL, FAST = 11, 7, 4
BEST = "best"


def format_time(ticks):
    tenths = ticks * 30 // 100
    return "%d.%d" % (tenths // 10, tenths % 10)


def centred_label(layer, text, y):
    """A label for ``text``, centred on the bottom of the disc, where it reads
    upright. steel8x8.png is a full CP437 font, 8 columns per character."""
    label = layer.label("steel8x8.png", columns=len(text), x=0, y=y, text=text)
    label.x = -(len(text) * label.image.width) // 2
    return label


class Car:
    """A sprite that drives from tile to tile, taking some ticks over each."""

    def __init__(self, sprite, col, row, frame):
        self.sprite = sprite
        self.frame = frame
        self.col = col
        self.row = row
        self.x = col * TILE        # not wrapped: it keeps counting round the disc
        self.y = row * TILE
        self.from_x = self.from_y = self.to_x = self.to_y = 0
        self.ticks = 0             # left to go on this step
        self.length = 1
        self.changed_lane = False  # a step along the track must come between lane changes

    def go(self, col, row, ticks):
        self.from_x, self.from_y = self.x, self.y
        self.to_x = self.from_x + (col - self.col) * TILE
        self.to_y = row * TILE
        self.col = col % COLS
        self.row = row
        self.ticks = self.length = ticks

    def advance(self):
        """Move on; True when this tick completes the step."""
        self.ticks -= 1
        done = self.ticks <= 0
        reached = 1.0 if done else 1.0 - self.ticks / self.length
        self.x = self.from_x + (self.to_x - self.from_x) * reached
        self.y = self.from_y + (self.to_y - self.from_y) * reached
        return done


class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)

        self.solid = bytearray(COLS * ROWS)
        self.cells = bytearray([NO_TILE] * (COLS * ROWS))
        self.track = self.world.tilemap(
            "tiles.png", columns=COLS, rows=ROWS, cells=self.cells,
            y=SHIFT, view_width=W, view_height=ROWS * TILE)
        self.pills = self.lay_track()

        self.enemies = []
        for lane in (3, 5, 7):
            sprite = self.world.sprite("sprites.png", frame=ENEMY, flip_x=True)
            enemy = Car(sprite, randrange(COLS // 2, COLS), lane, ENEMY)
            enemy.step_ticks = randrange(22, 34)
            enemy.lane_ticks = randrange(11, 17)
            self.enemies.append(enemy)
        self.player = Car(self.world.sprite("sprites.png", frame=CAR), 1, 1, CAR)
        self.cars = [self.player] + self.enemies
        self.booms = []
        for _ in range(2):
            boom = self.world.sprite("sprites.png", frame=BOOM, visible=False)
            boom.age = 0
            self.booms.append(boom)

        # "TIME" then four digits, centred on the bottom of the disc. x counts
        # up toward the left there, so the caption sits at the higher x.
        self.hud.label("steel8x8.png", columns=4, x=4, y=1, text="TIME")
        self.clock = self.hud.label("steel8x8.png", columns=4, x=-36, y=1)

        self.ticks = 0
        self.playing = True
        self.show_clock()
        self.place()

    def lay_track(self):
        """Walls between the lanes, with gaps, and a pill on every free lane
        tile. Returns how many pills there are."""
        pills = 0
        for row in range(ROWS - 1):
            for col in range(COLS):
                index = row * COLS + col
                if row % 2 == 0:
                    # The outer and inner walls have no gaps.
                    self.solid[index] = 1 if not (
                        0 < row < ROWS - 2 and col % GAP_EVERY == GAP_AT) else 0
                elif col % GAP_EVERY != GAP_AT:
                    self.cells[index] = PILL
                    pills += 1
        for row in range(0, ROWS - 1, 2):
            for col in range(COLS):
                index = row * COLS + col
                if self.solid[index]:
                    mask = 0
                    if not self.wall(col + 1, row):
                        mask |= 1
                    if not self.wall(col - 1, row):
                        mask |= 2
                    if not self.wall(col, row + 1):
                        mask |= 4
                    if not self.wall(col, row - 1):
                        mask |= 8
                    self.cells[index] = mask
        return pills

    def wall(self, col, row):
        if row < 0 or row >= ROWS:
            return True
        return self.solid[row * COLS + col % COLS] == 1

    def update(self):
        if self.playing:
            self.ticks += 1
            self.drive_player()
            for enemy in self.enemies:
                self.drive_enemy(enemy)
            self.check_crash()
            if self.ticks % 33 == 0:
                self.show_clock()
        self.move_booms()
        self.place()

    def drive_player(self):
        car = self.player
        if car.ticks:
            if car.advance():
                self.eat(car.col, car.row)
            return
        if joy1.held(RIGHT):
            speed = FAST
        elif joy1.held(LEFT):
            speed = SLOW
        else:
            speed = NORMAL
        lane = joy1.held(DOWN) - joy1.held(UP)       # down is toward the centre
        if lane and not car.changed_lane and not self.wall(car.col, car.row + lane):
            car.go(car.col, car.row + 2 * lane, speed * 2)
            car.changed_lane = True
        else:
            car.go(car.col + 1, car.row, speed)
            car.changed_lane = False

    def eat(self, col, row):
        index = row * COLS + col
        if self.cells[index] == PILL:
            self.cells[index] = NO_TILE
            self.pills -= 1
            vs2.audio.sound("pickup")
            if self.pills == 0:
                self.win()

    def drive_enemy(self, car):
        if car.ticks:
            car.advance()
            return
        lane = 0
        if car.row > self.player.row + 1:
            lane = -1
        elif car.row < self.player.row - 1:
            lane = 1
        if lane and not car.changed_lane and not self.wall(car.col, car.row + lane):
            car.go(car.col, car.row + 2 * lane, car.lane_ticks)
            car.changed_lane = True
            vs2.audio.sound("lane")
        else:
            car.go(car.col - 1, car.row, car.step_ticks)
            car.changed_lane = False

    def check_crash(self):
        player = self.player
        for car in self.enemies:
            dx = (car.x - player.x + W // 2) % W - W // 2
            if -6 < dx < 6 and -6 < car.y - player.y < 6:
                self.lose()
                return

    def move_booms(self):
        for boom in self.booms:
            if boom.visible:
                boom.age += 1
                if boom.age >= BOOM_FRAMES * 4:
                    boom.hide()
                else:
                    boom.frame = BOOM + boom.age // 4

    def lose(self):
        if not self.playing:
            return
        self.playing = False
        self.player.sprite.hide()
        boom = self.booms[0]
        boom.age = 0
        boom.frame = BOOM
        boom.x = ANCHOR
        boom.y = self.player.y + SHIFT
        boom.show()
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
        """Put everything on the disc, with the camera on the player."""
        cam = int(self.player.x)
        self.track.x = ANCHOR - cam
        for car in self.cars:
            sprite = car.sprite
            sprite.x = (ANCHOR + car.x - cam) % W
            sprite.y = car.y + SHIFT
            sprite.frame = car.frame + (self.ticks // 4) % 2


class Title(vs2.Scene):
    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "DODGE 'EM", y=1)
        best = vs2.saves.load(BEST, 0)
        centred_label(hud, "BEST " + format_time(best) if best else "UP DOWN AT GAPS", y=10)
        centred_label(hud, "PRESS A", y=19)

    def update(self):
        if joy1.just_pressed(A):
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
            centred_label(hud, "NEW BEST!", y=1)
        else:
            centred_label(hud, "TRACK CLEAR" if self.won else "CRASH!", y=1)
        centred_label(hud, "TIME " + format_time(self.ticks), y=10)
        centred_label(hud, "PRESS A", y=19)

    def update(self):
        if joy1.just_pressed(A):
            self.switch(Game())


def main():
    return Title()
