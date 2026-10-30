"""Spiral Tunnel: dive down a winding tunnel to the centre of the disc.

The idea for this game is by @borisvanschooten. It is one of the five games in
the Ludum Dare 60 entry "Circular Arcade", originally published at
https://tmtg.nl/ludumdare/ld60/jgame.html?game=jgame-games/ld60/
This is a port of it to Ventilastation (see games/ld60/README.md).

The tunnel spirals round the disc as it sinks, so you must keep flying round it
while you steer toward the centre. Walls kill you, so do the UFOs that patrol
the tunnel; lob bombs to clear them. The camera turns with you: you always fly
at the top of the disc.

Controls: arrows steer (left and right also change the speed you fly round at),
A drops a bomb. Either controller plays.
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
# The ship is kept this deep in the view: about a quarter of the radius in from
# the rim (depth 18, LED 40), where tunnel walls and UFOs are still big enough to
# steer by. Further in, things are too small to read, so the camera goes on
# following the ship to the end of the tunnel instead of stopping when the map
# runs out: the view then shows empty space past the tunnel.
PLAYER_DEPTH = 18

SHIP, UFO, BOMB, BOOM = 0, 1, 4, 5     # frames of sprites.png
UFO_FRAMES = 3
BOOM_FRAMES = 3
NO_TILE = vs2.EMPTY_TILE
# Frames of tiles.png: 0 is solid wall. The tunnel's edge slants across `shift`
# tiles (2..5) in each row, and each slanted piece is one frame, in order along
# the edge. LEFT_AT[shift] is the first of them on the left edge, RIGHT_AT[shift]
# on the right edge.
LEFT_AT = (0, 0, 1, 3, 6, 10)
RIGHT_AT = (0, 0, 15, 17, 20, 24)

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

        self.cells = bytearray([NO_TILE] * (COLS * ROWS))
        self.walls = self.world.tilemap(
            "tiles.png", columns=COLS, rows=ROWS, cells=self.cells,
            view_width=W, view_height=VIEW_H)
        ufo_spots = self.carve_tunnel()
        self.draw_tunnel()

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

        # Start on the rim, in the middle of the first row: the edges slant away
        # as the ship goes down, so a lower start can already be in the wall.
        self.wx = float(self.start_col * TILE - TILE // 2)
        self.wy = 0.0
        self.cam_x = int(self.wx)
        self.cam_y = 0
        self.ticks = 0
        self.cooldown = 0
        self.playing = True
        self.show_clock()
        self.place()

    # -- the level -------------------------------------------------------

    def carve_tunnel(self):
        """Lay out a tunnel that drifts round the disc as it goes down. Each row
        has its left edge, its width and how far each edge moves sideways by the
        next row (2 to 5 tiles), which is what makes the edges slant. Returns
        where the UFOs start."""
        self.left = [0] * ROWS
        self.span = [0] * ROWS
        self.left_shift = [0] * ROWS
        self.right_shift = [0] * ROWS
        left = COLS // 2 - 7
        width = 15
        ufo_spots = []
        for row in range(ROWS):
            shift = randrange(2, 6)
            # The right edge moves by whatever keeps the tunnel 13 to 16 wide.
            options = [s for s in range(2, 6) if 13 <= width + s - shift <= 16]
            right_shift = options[randrange(len(options))]
            self.left[row] = left
            self.span[row] = width
            self.left_shift[row] = shift
            self.right_shift[row] = right_shift
            if row > 3 and row % 2 == 1 and len(ufo_spots) < UFO_COUNT:
                ufo_spots.append(((left + width // 2) % COLS, row))
            left = (left + shift) % COLS
            width += right_shift - shift
        self.start_col = self.left[0] + self.span[0] // 2
        return ufo_spots

    def draw_tunnel(self):
        """Fill the map with wall and cut the tunnel out of it, with a slanted
        tile where each edge crosses from one row to the next."""
        for row in range(ROWS):
            left = self.left[row]
            width = self.span[row]
            shift = self.left_shift[row]
            right_shift = self.right_shift[row]
            for col in range(COLS):
                k = (col - left) % COLS             # tiles in from the left edge
                if k < shift:
                    tile = LEFT_AT[shift] + k
                elif k < width:
                    tile = NO_TILE
                elif k - width < right_shift:
                    tile = RIGHT_AT[right_shift] + k - width
                else:
                    tile = 0
                self.cells[row * COLS + col] = tile

    def wall_at(self, px, py):
        """Whether the point is in the wall, along the same slanted edges that
        are drawn."""
        if py < 0 or py >= ROWS * TILE:
            return True
        row = int(py) // TILE
        into = py - row * TILE                      # how far down this row
        start = self.left[row] * TILE + self.left_shift[row] * into
        width = self.span[row] * TILE + (self.right_shift[row] - self.left_shift[row]) * into
        return (px - start) % W >= width

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
        steer = held(RIGHT) - held(LEFT)
        self.wx = (self.wx + CRUISE + STEER_X * steer) % W
        self.wy += STEER_Y * (held(DOWN) - held(UP))
        if self.wy < 0:
            self.wy = 0
        if self.cooldown:
            self.cooldown -= 1
        elif held(A):
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
        top = self.wy - PLAYER_DEPTH
        self.cam_y = int(max(top, 0))
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
        title_label(hud, "SPIRAL TUNNEL")
        best = vs2.saves.load(BEST, 0)
        centred_label(hud, "BEST " + format_time(best) if best else "ARROWS  A=BOMB", y=8)
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
            title_label(hud, "TUNNEL CLEAR" if self.won else "GAME OVER", y=RESULT_Y)
        centred_label(hud, "TIME " + format_time(self.ticks), y=8)
        centred_label(hud, "PRESS A", y=1, font="tinyfont_red.png")

    def update(self):
        if pressed(A):
            self.switch(Game())


def main():
    return Title()
