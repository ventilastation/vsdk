"""Defender: shoot every alien before they shoot you, over a planet in the middle.

The idea for this game is by @borisvanschooten. It is one of the five games in
the Ludum Dare 60 entry "Circular Arcade", originally published at
https://tmtg.nl/ludumdare/ld60/jgame.html?game=jgame-games/ld60/
This is a port of it to Ventilastation (see games/ld60/README.md).

The planet's mountains rise toward the rim, and the aliens hover over them and
fire at you when they see you. Flying into the ground, an alien or a shot ends
the game. The camera turns with you: you always fly at the top of the disc.

Controls: the arrows fly, A fires the way you are facing.
"""

import math

from urandom import randrange

import vs2
from vs2.controls import *

W = vs2.display.width      # 256 columns round the disc
TILE = 8
COLS = W // TILE
ROWS = 18                  # the planet fills the bottom of this, toward the centre
ANCHOR = W // 2 - TILE // 2    # the player is drawn at the top of the disc
FLOOR = (ROWS - 8) * TILE      # the deepest you can fly
ALIENS = 21
SHOTS = 4
ALIEN_SHOTS = 6
BOOMS = 6

SHIP, SHIP_THRUST, ALIEN, SHOT, ALIEN_SHOT, BOOM = 0, 1, 2, 4, 5, 6   # frames of sprites.png
BOOM_FRAMES = 3
NO_TILE = vs2.EMPTY_TILE

SPEED = 1.2                # columns or rows of depth per tick
SHOT_SPEED = 2.9
SHOT_LIFE = 33
FIRE_TICKS = 8
ALIEN_SHOT_SPEED = 1.0
ALIEN_SHOT_LIFE = 66
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


def wrapped(a, b):
    """How far round the disc from b to a, the short way."""
    return (a - b + W // 2) % W - W // 2


class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)

        self.solid = bytearray(COLS * ROWS)
        self.cells = bytearray([NO_TILE] * (COLS * ROWS))
        self.planet = self.world.tilemap(
            "tiles.png", columns=COLS, rows=ROWS, cells=self.cells,
            view_width=W, view_height=ROWS * TILE)
        tops = self.raise_mountains()
        self.autotile()

        self.aliens = []
        for col in range(6, COLS - 5):
            alien = self.world.sprite("sprites.png", frame=ALIEN)
            alien.wx = col * TILE
            alien.wy = (tops[col] - 2) * TILE
            alien.vx = alien.vy = 0.0
            alien.turn = 0
            alien.reload = randrange(90, 300)
            alien.alive = True
            self.aliens.append(alien)
        self.shots = self.bullets(SHOT, SHOTS)
        self.alien_shots = self.bullets(ALIEN_SHOT, ALIEN_SHOTS)
        self.ship = self.world.sprite("sprites.png", frame=SHIP)
        self.booms = []
        for _ in range(BOOMS):
            boom = self.world.sprite("sprites.png", frame=BOOM, visible=False)
            boom.wx = boom.wy = boom.age = 0
            boom.active = False
            self.booms.append(boom)

        # "TIME" then four digits, and "LEFT" then the aliens still flying,
        # centred on the bottom of the disc. x counts up toward the left there,
        # so a caption sits at the higher x.
        self.hud.label("steel8x8.png", columns=4, x=4, y=1, text="TIME")
        self.clock = self.hud.label("steel8x8.png", columns=4, x=-36, y=1)
        self.hud.label("steel8x8.png", columns=4, x=4, y=10, text="LEFT")
        self.left_label = self.hud.label("steel8x8.png", columns=4, x=-36, y=10)

        self.wx = float(TILE)
        self.wy = float(TILE)
        self.facing = 1
        self.cooldown = 0
        self.left = ALIENS
        self.ticks = 0
        self.playing = True
        self.show_clock()
        self.left_label.set_number(self.left, width=4, pad=" ")
        self.place()

    def bullets(self, frame, count):
        out = []
        for _ in range(count):
            bullet = self.world.sprite("sprites.png", frame=frame, visible=False)
            bullet.wx = bullet.wy = bullet.vx = bullet.vy = 0.0
            bullet.life = 0
            out.append(bullet)
        return out

    # -- the planet ------------------------------------------------------

    def raise_mountains(self):
        """Fill the bottom of the map with ground that rises and falls round the
        disc. Returns the row of each column's summit."""
        first = randrange(0, 1000) * 0.012
        second = randrange(0, 1000) * 0.012
        mix = randrange(25, 75) * 0.01
        tops = []
        for col in range(COLS):
            turn = 2 * math.pi * col / COLS
            wave = mix * math.sin(3 * (turn + first)) + (1 - mix) * math.cos(5 * (turn + second))
            top = int(5 + 7 * (0.5 + 0.5 * wave))
            tops.append(top)
            for row in range(top, ROWS):
                self.solid[row * COLS + col] = 1
        return tops

    def is_solid(self, col, row):
        if row < 0:
            return False
        if row >= ROWS:
            return True
        return self.solid[row * COLS + col % COLS] == 1

    def autotile(self):
        """Pick each ground tile by which of its neighbours are open, so the
        mountains are outlined in light."""
        for row in range(ROWS):
            for col in range(COLS):
                if self.solid[row * COLS + col]:
                    mask = 0
                    if not self.is_solid(col + 1, row):
                        mask |= 1
                    if not self.is_solid(col - 1, row):
                        mask |= 2
                    if row + 1 < ROWS and not self.is_solid(col, row + 1):
                        mask |= 4
                    if not self.is_solid(col, row - 1):
                        mask |= 8
                    self.cells[row * COLS + col] = mask

    def solid_at(self, px, py):
        if py < 0:
            return False
        return self.is_solid(int(px) // TILE, int(py) // TILE)

    # -- the game ------------------------------------------------------------

    def update(self):
        if self.playing:
            self.ticks += 1
            self.fly()
            for alien in self.aliens:
                if alien.alive:
                    self.hover(alien)
            self.move_shots()
            self.check_hits()
            if self.ticks % 33 == 0:
                self.show_clock()
        self.move_booms()
        self.place()

    def fly(self):
        step = joy1.held(RIGHT) - joy1.held(LEFT)
        if step:
            self.facing = step
        self.wx = (self.wx + step * SPEED) % W
        self.wy += SPEED * (joy1.held(DOWN) - joy1.held(UP))
        self.wy = min(max(self.wy, 0), FLOOR)
        if self.cooldown:
            self.cooldown -= 1
        elif joy1.held(A):
            self.fire()
        if (self.solid_at(self.wx + 2, self.wy + 6) or self.solid_at(self.wx + 5, self.wy + 6)):
            self.lose()

    def fire(self):
        for shot in self.shots:
            if not shot.life:
                shot.wx = self.wx
                shot.wy = self.wy
                shot.vx = self.facing * SHOT_SPEED
                shot.flip_x = self.facing < 0
                shot.life = SHOT_LIFE
                shot.show()
                self.cooldown = FIRE_TICKS
                vs2.audio.sound("shoot")
                return

    def hover(self, alien):
        if alien.turn <= 0:
            alien.turn = randrange(27, 55)
            alien.vx = randrange(-20, 21) * 0.024
            alien.vy = randrange(-20, 21) * 0.024
        alien.turn -= 1
        alien.wx = (alien.wx + alien.vx) % W
        alien.wy = min(max(alien.wy + alien.vy, TILE), (ROWS - 2) * TILE)
        if self.solid_at(alien.wx + 4, alien.wy + 7):
            alien.vy = -0.73
        alien.frame = ALIEN + (self.ticks // 8) % 2
        alien.flip_x = alien.vx > 0
        alien.reload -= 1
        if alien.reload <= 0:
            alien.reload = randrange(165, 220)
            self.shoot_at_player(alien)

    def shoot_at_player(self, alien):
        for shot in self.alien_shots:
            if not shot.life:
                dx = wrapped(self.wx, alien.wx)
                dy = self.wy - alien.wy
                length = math.sqrt(dx * dx + dy * dy) or 1.0
                shot.wx = alien.wx
                shot.wy = alien.wy
                shot.vx = ALIEN_SHOT_SPEED * dx / length
                shot.vy = ALIEN_SHOT_SPEED * dy / length
                shot.life = ALIEN_SHOT_LIFE
                shot.show()
                return

    def move_shots(self):
        for shot in self.shots:
            if shot.life:
                shot.wx = (shot.wx + shot.vx) % W
                shot.life -= 1
                if not shot.life or self.solid_at(shot.wx + 4, shot.wy + 4):
                    shot.life = 0
                    shot.hide()
        for shot in self.alien_shots:
            if shot.life:
                shot.wx = (shot.wx + shot.vx) % W
                shot.wy += shot.vy
                shot.life -= 1
                if not shot.life or self.solid_at(shot.wx + 4, shot.wy + 4):
                    shot.life = 0
                    shot.hide()

    def check_hits(self):
        for alien in self.aliens:
            if not alien.alive:
                continue
            if self.touching(alien.wx, alien.wy, self.wx, self.wy, 6, 6):
                self.boom(alien.wx, alien.wy)
                self.kill(alien)
                self.lose()
                return
            for shot in self.shots:
                if shot.life and self.touching(alien.wx, alien.wy, shot.wx, shot.wy, 6, 5):
                    shot.life = 0
                    shot.hide()
                    self.boom(alien.wx, alien.wy)
                    self.kill(alien)
                    vs2.audio.sound("explo")
                    break
        for shot in self.alien_shots:
            if shot.life and self.touching(shot.wx, shot.wy, self.wx, self.wy, 5, 5):
                self.lose()
                return
        if not self.left:
            self.win()

    def touching(self, ax, ay, bx, by, reach_x, reach_y):
        return -reach_x < wrapped(ax, bx) < reach_x and -reach_y < ay - by < reach_y

    def kill(self, alien):
        alien.alive = False
        alien.hide()
        self.left -= 1
        self.left_label.set_number(self.left, width=4, pad=" ")

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
        self.ship.hide()
        self.boom(self.wx, self.wy)
        vs2.audio.sound("die")
        self.call_later(1000, self.finish, False)

    def win(self):
        if not self.playing:
            return
        self.playing = False
        self.ship.hide()
        vs2.audio.sound("win")
        self.call_later(800, self.finish, True)

    def finish(self, won):
        self.switch(Result(won, self.ticks))

    def show_clock(self):
        self.clock.set_number(self.ticks * 30 // 1000, width=4, pad=" ")

    def place(self):
        """Put everything on the disc, with the camera on the ship."""
        cam = int(self.wx)
        self.planet.x = ANCHOR - cam
        self.ship.x = ANCHOR + self.wx - cam
        self.ship.y = self.wy
        self.ship.flip_x = self.facing < 0
        self.ship.frame = SHIP_THRUST if (joy1.held(LEFT) or joy1.held(RIGHT)) else SHIP
        for group in (self.aliens, self.shots, self.alien_shots, self.booms):
            for item in group:
                if item.visible:
                    item.x = (ANCHOR + item.wx - cam) % W
                    item.y = item.wy


class Title(vs2.Scene):
    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        title_label(hud, "DEFENDER")
        best = vs2.saves.load(BEST, 0)
        centred_label(hud, "BEST " + format_time(best) if best else "ARROWS  A=FIRE", y=10)
        centred_label(hud, "PRESS A", y=1)

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
            title_label(hud, "NEW BEST!", y=RESULT_Y)
        else:
            title_label(hud, "ALL CLEAR" if self.won else "GAME OVER", y=RESULT_Y)
        centred_label(hud, "TIME " + format_time(self.ticks), y=10)
        centred_label(hud, "PRESS A", y=1)

    def update(self):
        if joy1.just_pressed(A):
            self.switch(Game())


def main():
    return Title()
