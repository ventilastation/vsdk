"""Catch the Robots: run down every robot in a maze that wraps round the disc.

The idea for this game is by @borisvanschooten. It is one of the five games in
the Ludum Dare 60 entry "Circular Arcade", originally published at
https://tmtg.nl/ludumdare/ld60/jgame.html?game=jgame-games/ld60/
This is a port of it to Ventilastation (see games/ld60/README.md).

The maze is a new one every time. The robots trudge along the walls and never
look for you, so the trick is to work out where they will come round. The
camera turns with you and follows you down the maze: you always run at the top
of the disc.

Controls: the arrows run you through the maze.
"""

from urandom import randrange

import vs2
from vs2.controls import *

W = vs2.display.width      # 256 columns round the disc
TILE = 8
COLS = W // TILE
ROWS = 36                  # rows 1 and 33 are the outer walls of the maze
LAST_ROW = 33
VIEW_ROWS = 18             # how many rows of it are drawn at a time
VIEW_H = VIEW_ROWS * TILE
ANCHOR = W // 2 - TILE // 2    # the player is drawn at the top of the disc
# The player is kept this many rows down the view, which is about halfway to the
# centre of the disc (depth 40). Further in, things get too small to read, so the
# camera goes on following the player right to the bottom of the maze instead of
# stopping when the map runs out: the view then shows empty space past the maze.
PLAYER_ROW = 5
ROBOTS = 20

PLAYER, ROBOT, BOOM = 0, 2, 4      # frames of sprites.png
BOOM_FRAMES = 3
NO_TILE = vs2.EMPTY_TILE

PLAYER_TICKS = 4           # ticks the player takes to cross a tile
ROBOT_TICKS = 40           # ticks a robot takes to cross two
BEST = "best"

# Up is toward the rim, so a step up is one row less deep.
STEPS = ((-1, 0), (0, 1), (1, 0), (0, -1))     # left, down, right, up


def format_time(ticks):
    tenths = ticks * 30 // 100
    return "%d.%d" % (tenths // 10, tenths % 10)


def centred_label(layer, text, y):
    """A label for ``text``, centred on the bottom of the disc, where it reads
    upright. steel8x8.png is a full CP437 font, 8 columns per character."""
    label = layer.label("steel8x8.png", columns=len(text), x=0, y=y, text=text)
    label.x = -(len(text) * label.image.width) // 2
    return label


class Walker:
    """A sprite that walks from tile to tile, taking some ticks over each step."""

    def __init__(self, sprite, col, row):
        self.sprite = sprite
        self.col = col
        self.row = row
        self.x = col * TILE        # not wrapped: it keeps counting round the disc
        self.y = row * TILE
        self.from_x = self.from_y = self.to_x = self.to_y = 0
        self.ticks = 0             # left to go on this step
        self.length = 1
        self.alive = True
        self.heading = 0
        self.turn = 1

    def go(self, d_col, d_row, ticks):
        self.from_x, self.from_y = self.x, self.y
        self.to_x = self.from_x + d_col * TILE
        self.to_y = self.from_y + d_row * TILE
        self.col = (self.col + d_col) % COLS
        self.row += d_row
        self.ticks = self.length = ticks

    def advance(self):
        self.ticks -= 1
        reached = 1.0 if self.ticks <= 0 else 1.0 - self.ticks / self.length
        self.x = self.from_x + (self.to_x - self.from_x) * reached
        self.y = self.from_y + (self.to_y - self.from_y) * reached


class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)

        self.solid = bytearray(COLS * ROWS)
        self.cells = bytearray([NO_TILE] * (COLS * ROWS))
        self.maze = self.world.tilemap(
            "tiles.png", columns=COLS, rows=ROWS, cells=self.cells,
            view_width=W, view_height=VIEW_H)
        open_cells = self.dig_maze()
        self.autotile()

        self.robots = []
        for _ in range(ROBOTS):
            col, row = open_cells.pop(randrange(5, len(open_cells)))
            sprite = self.world.sprite("sprites.png", frame=ROBOT)
            robot = Walker(sprite, col, row)
            robot.heading = randrange(4)
            robot.turn = 1 if randrange(2) else -1
            self.robots.append(robot)
        self.player = Walker(self.world.sprite("sprites.png", frame=PLAYER), 2, 2)
        self.booms = []
        for _ in range(3):
            boom = self.world.sprite("sprites.png", frame=BOOM, visible=False)
            boom.wx = boom.wy = boom.age = 0
            boom.active = False
            self.booms.append(boom)

        # "TIME" then four digits, and "LEFT" then the robots still running,
        # centred on the bottom of the disc. x counts up toward the left there,
        # so a caption sits at the higher x.
        self.hud.label("steel8x8.png", columns=4, x=4, y=1, text="TIME")
        self.clock = self.hud.label("steel8x8.png", columns=4, x=-36, y=1)
        self.hud.label("steel8x8.png", columns=4, x=4, y=10, text="LEFT")
        self.left_label = self.hud.label("steel8x8.png", columns=4, x=-36, y=10)

        self.left = ROBOTS
        self.ticks = 0
        self.playing = True
        self.show_clock()
        self.left_label.set_number(self.left, width=4, pad=" ")
        self.place()

    # -- the maze ----------------------------------------------------------

    def dig_maze(self):
        """Carve a random maze: rooms on the even tiles, joined by gaps in the
        walls between them. Returns the rooms, as (column, row) pairs."""
        for row in range(1, LAST_ROW + 1):
            for col in range(COLS):
                self.solid[row * COLS + col] = 1
        rooms = [(2, 2)]
        self.solid[2 * COLS + 2] = 0
        stack = [(2, 2)]
        while stack:
            col, row = stack[-1]
            start = randrange(4)
            for i in range(4):
                d_col, d_row = STEPS[(start + i) % 4]
                new_col = (col + 2 * d_col) % COLS
                new_row = row + 2 * d_row
                if 2 <= new_row < LAST_ROW and self.solid[new_row * COLS + new_col]:
                    self.solid[(row + d_row) * COLS + (col + d_col) % COLS] = 0
                    self.solid[new_row * COLS + new_col] = 0
                    stack.append((new_col, new_row))
                    rooms.append((new_col, new_row))
                    break
            else:
                stack.pop()
        return rooms

    def is_wall(self, col, row):
        if row < 0 or row >= ROWS:
            return False
        return self.solid[row * COLS + col % COLS] == 1

    def autotile(self):
        """Pick each wall tile by which of its neighbours are open, so the
        passages are outlined in light."""
        for row in range(1, LAST_ROW + 1):
            for col in range(COLS):
                index = row * COLS + col
                if self.solid[index]:
                    mask = 0
                    if not self.is_wall(col + 1, row):
                        mask |= 1
                    if not self.is_wall(col - 1, row):
                        mask |= 2
                    if not self.is_wall(col, row + 1):
                        mask |= 4
                    if not self.is_wall(col, row - 1):
                        mask |= 8
                    self.cells[index] = mask

    # -- the game ------------------------------------------------------------

    def update(self):
        if self.playing:
            self.ticks += 1
            self.run_player()
            for robot in self.robots:
                if robot.alive:
                    self.walk_robot(robot)
            self.catch()
            if self.ticks % 33 == 0:
                self.show_clock()
        self.move_booms()
        self.place()

    def run_player(self):
        walker = self.player
        if walker.ticks:
            walker.advance()
            return
        if joy1.held(UP):
            d_col, d_row = 0, -1
        elif joy1.held(DOWN):
            d_col, d_row = 0, 1
        elif joy1.held(LEFT):
            d_col, d_row = -1, 0
            walker.sprite.flip_x = True
        elif joy1.held(RIGHT):
            d_col, d_row = 1, 0
            walker.sprite.flip_x = False
        else:
            return
        if not self.is_wall(walker.col + d_col, walker.row + d_row):
            walker.go(d_col, d_row, PLAYER_TICKS)

    def walk_robot(self, robot):
        """Follow the wall on one side: turn that way if it is open, else carry
        on, else turn the other way."""
        if robot.ticks:
            robot.advance()
            return
        heading = robot.heading - robot.turn
        for _ in range(4):
            heading %= 4
            d_col, d_row = STEPS[heading]
            if not self.is_wall(robot.col + d_col, robot.row + d_row):
                robot.heading = heading
                robot.go(2 * d_col, 2 * d_row, ROBOT_TICKS)
                robot.sprite.flip_x = d_col < 0
                return
            heading += robot.turn

    def catch(self):
        player = self.player
        for robot in self.robots:
            if not robot.alive:
                continue
            dx = (robot.x - player.x + W // 2) % W - W // 2
            if -6 < dx < 6 and -6 < robot.y - player.y < 6:
                robot.alive = False
                robot.sprite.hide()
                self.left -= 1
                self.left_label.set_number(self.left, width=4, pad=" ")
                self.boom(robot.x, robot.y)
                if self.left:
                    vs2.audio.sound("pickup")
                else:
                    self.win()

    def boom(self, x, y):
        for boom in self.booms:
            if not boom.active:
                boom.wx = x
                boom.wy = y
                boom.age = 0
                boom.frame = BOOM
                boom.active = True
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

    def win(self):
        if not self.playing:
            return
        self.playing = False
        vs2.audio.sound("win")
        self.call_later(800, self.finish)

    def finish(self):
        self.switch(Result(self.ticks))

    def show_clock(self):
        self.clock.set_number(self.ticks * 30 // 1000, width=4, pad=" ")

    def place(self):
        """Put everything on the disc, with the camera on the player."""
        cam_x = int(self.player.x)
        cam_y = int(max(self.player.y - PLAYER_ROW * TILE, 0))
        self.maze.x = ANCHOR - cam_x
        self.maze.view_y = cam_y
        self.show(self.player.sprite, self.player.x, self.player.y, cam_x, cam_y)
        for robot in self.robots:
            if robot.alive:
                self.show(robot.sprite, robot.x, robot.y, cam_x, cam_y)
                robot.sprite.frame = ROBOT + (self.ticks // 8) % 2
        for boom in self.booms:
            if boom.active:
                self.show(boom, boom.wx, boom.wy, cam_x, cam_y)
        self.player.sprite.frame = PLAYER + (self.player.ticks // 2) % 2

    def show(self, sprite, x, y, cam_x, cam_y):
        """Place a sprite at world (x, y), and hide it when it is out of view."""
        sprite.x = (ANCHOR + x - cam_x) % W
        sprite.y = y - cam_y
        sprite.visible = -TILE < sprite.y < VIEW_H


class Title(vs2.Scene):
    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "CATCH THE ROBOTS", y=1)
        best = vs2.saves.load(BEST, 0)
        centred_label(hud, "BEST " + format_time(best) if best else "ARROWS RUN", y=10)
        centred_label(hud, "PRESS A", y=19)

    def update(self):
        if joy1.just_pressed(A):
            self.switch(Game())


class Result(vs2.Scene):
    def __init__(self, ticks):
        vs2.Scene.__init__(self)
        self.ticks = ticks
        self.best = vs2.saves.load(BEST, 0)
        self.new_best = not self.best or ticks < self.best
        if self.new_best:
            self.best = ticks
            vs2.saves.save(BEST, ticks)

    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "NEW BEST!" if self.new_best else "ALL CAUGHT", y=1)
        centred_label(hud, "TIME " + format_time(self.ticks), y=10)
        centred_label(hud, "PRESS A", y=19)

    def update(self):
        if joy1.just_pressed(A):
            self.switch(Game())


def main():
    return Title()
