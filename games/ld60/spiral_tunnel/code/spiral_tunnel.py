"""Spiral Tunnel: dive down a winding tunnel to the centre of the disc.

One of five LD60 "Circular Arcade" concept games (games/ld60). The tunnel
spirals round the disc as it sinks, so you must keep flying round it while you
steer toward the centre. Walls kill you, so do the UFOs that patrol the tunnel;
lob bombs to clear them. The camera turns with you: you always fly at the top
of the disc.

Controls: arrows steer (left and right also change the speed you fly round at),
A drops a bomb.
"""

from urandom import randrange

import vs2
from vs2.controls import *

W = vs2.display.width      # 256 columns round the disc
TILE = 8
COLS = W // TILE
ROWS = 56                  # the tunnel is this many tiles deep
VIEW_ROWS = 18             # how many rows of it are drawn at a time
VIEW_H = VIEW_ROWS * TILE
ANCHOR = W // 2 - TILE // 2    # the player is drawn at the top of the disc
PLAYER_ROW = 5             # which row of the view the player is kept on

SHIP, UFO, BOMB, BOOM = 0, 1, 4, 5     # frames of sprites.png
UFO_FRAMES = 3
BOOM_FRAMES = 3
NO_TILE = vs2.EMPTY_TILE

CRUISE = 1.2               # columns per tick the player flies round at
STEER_X = 0.75             # extra or less with right and left
STEER_Y = 1.0              # rows of depth per tick with up and down
BOMB_VX = 3.0
BOMB_VY = 0.7
BOMB_GRAVITY = 0.06
BOMB_LIFE = 45
FIRE_TICKS = 8
BEST = "best"

UFO_COUNT = (ROWS - 4) // 2
BOMBS = 4
BOOMS = 4


def format_time(ticks):
    tenths = ticks * 30 // 100
    return "%d.%d" % (tenths // 10, tenths % 10)


def centred_label(layer, text, y):
    """A label for ``text``, centred on the bottom of the disc, where it reads
    upright. steel8x8.png is a full CP437 font, 8 columns per character."""
    label = layer.label("steel8x8.png", columns=len(text), x=0, y=y, text=text)
    label.x = -(len(text) * label.image.width) // 2
    return label


class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)

        self.solid = bytearray(COLS * ROWS)
        self.cells = bytearray([NO_TILE] * (COLS * ROWS))
        self.walls = self.world.tilemap(
            "tiles.png", columns=COLS, rows=ROWS, cells=self.cells,
            view_width=W, view_height=VIEW_H)
        ufo_spots = self.carve_tunnel()
        self.autotile()

        self.ufos = []
        for col, row in ufo_spots:
            ufo = self.world.sprite("sprites.png", frame=UFO)
            ufo.wx = col * TILE
            ufo.wy = row * TILE
            ufo.vy = (1 if randrange(2) else -1) * (0.5 + randrange(4) * 0.12)
            ufo.alive = True
            self.ufos.append(ufo)
        self.bombs = []
        for _ in range(BOMBS):
            bomb = self.world.sprite("sprites.png", frame=BOMB, visible=False)
            bomb.wx = bomb.wy = bomb.vx = bomb.vy = bomb.life = 0
            self.bombs.append(bomb)
        self.ship = self.world.sprite("sprites.png", frame=SHIP)
        self.booms = []
        for _ in range(BOOMS):
            boom = self.world.sprite("sprites.png", frame=BOOM, visible=False)
            boom.wx = boom.wy = boom.age = 0
            self.booms.append(boom)

        # "TIME" then four digits, centred on the bottom of the disc. x counts
        # up toward the left there, so the caption sits at the higher x.
        self.hud.label("steel8x8.png", columns=4, x=4, y=1, text="TIME")
        self.clock = self.hud.label("steel8x8.png", columns=4, x=-36, y=1)

        self.wx = float(self.start_col * TILE)
        self.wy = float(TILE)
        self.cam_x = int(self.wx)
        self.cam_y = 0
        self.ticks = 0
        self.cooldown = 0
        self.playing = True
        self.show_clock()
        self.place()

    # -- the level -------------------------------------------------------

    def carve_tunnel(self):
        """Fill the map with wall, then cut a tunnel that drifts round the disc
        as it goes down. Returns where the UFOs start."""
        cells = self.solid
        for i in range(len(cells)):
            cells[i] = 1
        centre = COLS // 2
        width = 15
        ufo_spots = []
        for row in range(ROWS):
            for c in range(width):
                cells[row * COLS + (centre - width // 2 + c) % COLS] = 0
            if row == 0:
                self.start_col = centre
            if row > 3 and row % 2 == 1 and len(ufo_spots) < UFO_COUNT:
                ufo_spots.append((centre % COLS, row))
            centre = (centre + randrange(2, 6)) % COLS
            width = min(16, max(13, width + randrange(-1, 2)))
        return ufo_spots

    def is_wall(self, col, row):
        if row < 0 or row >= ROWS:
            return True
        return self.solid[row * COLS + col % COLS] == 1

    def autotile(self):
        """Pick each wall tile by which of its neighbours are open, so the
        tunnel is outlined in light."""
        for row in range(ROWS):
            for col in range(COLS):
                index = row * COLS + col
                if not self.solid[index]:
                    continue
                mask = 0
                if not self.is_wall(col + 1, row):
                    mask |= 1
                if not self.is_wall(col - 1, row):
                    mask |= 2
                if row + 1 < ROWS and not self.is_wall(col, row + 1):
                    mask |= 4
                if row > 0 and not self.is_wall(col, row - 1):
                    mask |= 8
                self.cells[index] = mask

    def wall_at(self, px, py):
        if py < 0:
            return True
        return self.is_wall(int(px) // TILE, int(py) // TILE)

    # -- the game --------------------------------------------------------

    def update(self):
        if self.playing:
            self.ticks += 1
            self.fly()
            self.move_ufos()
            if self.playing:
                self.move_bombs()
                self.check_hits()
            if self.ticks % 33 == 0:
                self.show_clock()
        self.move_booms()
        self.place()

    def fly(self):
        steer = joy1.held(RIGHT) - joy1.held(LEFT)
        self.wx = (self.wx + CRUISE + STEER_X * steer) % W
        self.wy += STEER_Y * (joy1.held(DOWN) - joy1.held(UP))
        if self.wy < 0:
            self.wy = 0
        if self.cooldown:
            self.cooldown -= 1
        elif joy1.held(A):
            self.drop_bomb()
        # The corners of the ship, a little inside its picture.
        left, right = self.wx + 1, self.wx + TILE - 2
        top, bottom = self.wy + 1, self.wy + TILE - 2
        if (self.wall_at(left, top) or self.wall_at(right, top)
                or self.wall_at(left, bottom) or self.wall_at(right, bottom)):
            self.lose()
        elif self.wy > (ROWS - 4) * TILE:
            self.win()

    def drop_bomb(self):
        for bomb in self.bombs:
            if not bomb.visible:
                bomb.wx = self.wx + TILE / 2
                bomb.wy = self.wy
                bomb.vx = BOMB_VX
                bomb.vy = BOMB_VY
                bomb.life = BOMB_LIFE
                bomb.show()
                self.cooldown = FIRE_TICKS
                vs2.audio.sound("bomb")
                return

    def move_ufos(self):
        for ufo in self.ufos:
            if not ufo.alive:
                continue
            ufo.wy += ufo.vy
            if self.wall_at(ufo.wx + TILE / 2, ufo.wy + (TILE if ufo.vy > 0 else 0)):
                ufo.vy = -ufo.vy
                ufo.wy += ufo.vy * 2
            ufo.frame = UFO + (self.ticks // 6) % UFO_FRAMES

    def move_bombs(self):
        for bomb in self.bombs:
            if not bomb.visible:
                continue
            bomb.wx = (bomb.wx + bomb.vx) % W
            bomb.vy += BOMB_GRAVITY
            bomb.wy += bomb.vy
            bomb.life -= 1
            if bomb.life <= 0:
                bomb.hide()
            elif self.wall_at(bomb.wx, bomb.wy + TILE / 2):
                self.boom(bomb.wx, bomb.wy)
                bomb.hide()

    def check_hits(self):
        for ufo in self.ufos:
            if not ufo.alive:
                continue
            if near(ufo.wx, ufo.wy, self.wx, self.wy):
                self.boom(ufo.wx, ufo.wy)
                ufo.alive = False
                ufo.hide()
                self.lose()
                return
            for bomb in self.bombs:
                if bomb.visible and near(ufo.wx, ufo.wy, bomb.wx - TILE / 2, bomb.wy):
                    self.boom(ufo.wx, ufo.wy)
                    ufo.alive = False
                    ufo.hide()
                    bomb.hide()
                    vs2.audio.sound("explo")
                    break

    def boom(self, wx, wy):
        for boom in self.booms:
            if not boom.visible:
                boom.wx = wx
                boom.wy = wy
                boom.age = 0
                boom.frame = BOOM
                boom.show()
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
        self.ship.hide()
        self.boom(self.wx, self.wy)
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

    # -- drawing -----------------------------------------------------------

    def place(self):
        """Put everything on the disc, with the camera on the ship."""
        self.cam_x = int(self.wx)
        top = self.wy - PLAYER_ROW * TILE
        self.cam_y = int(min(max(top, 0), ROWS * TILE - VIEW_H))
        self.walls.x = ANCHOR - self.cam_x
        self.walls.view_y = self.cam_y
        self.ship.x = ANCHOR + self.wx - self.cam_x
        self.ship.y = self.wy - self.cam_y
        for group in (self.ufos, self.bombs, self.booms):
            for item in group:
                if item.visible:
                    item.x = (ANCHOR + item.wx - self.cam_x) % W
                    item.y = item.wy - self.cam_y


def near(ax, ay, bx, by):
    dx = (ax - bx + W // 2) % W - W // 2
    return -6 < dx < 6 and -6 < ay - by < 6


class Title(vs2.Scene):
    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "SPIRAL TUNNEL", y=1)
        best = vs2.saves.load(BEST, 0)
        centred_label(hud, "BEST " + format_time(best) if best else "ARROWS  A=BOMB", y=10)
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
            centred_label(hud, "TUNNEL CLEAR" if self.won else "GAME OVER", y=1)
        centred_label(hud, "TIME " + format_time(self.ticks), y=10)
        centred_label(hud, "PRESS A", y=19)

    def update(self):
        if joy1.just_pressed(A):
            self.switch(Game())


def main():
    return Title()
