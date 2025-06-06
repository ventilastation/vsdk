import utime
from urandom import randrange
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from .rotaciones import ROTACIONES

COLS = 16
ROWS = 18

VORTEX_TIME = 30  # in seconds

DEBUG = True

class ScoreBoard:
    def __init__(self):
        self.chars = []
        for n in range(9):
            s = Sprite()
            s.set_strip(stripes["numerals.png"])
            s.set_x(120 + n * 4)
            s.set_y(0)
            s.set_frame(10)
            s.set_perspective(2)
            self.chars.append(s)

        self.setscore(0)

    def setscore(self, value):
        for n, l in enumerate("%05d" % value):
            v = ord(l) - 0x30
            self.chars[n].set_frame(v)


class Vortex(Sprite):
    def __init__(self):
        super().__init__()
        self.set_strip(stripes["fondo.png"])
        self.set_perspective(0)
        self.set_frame(0)
        self.set_x(0)
        self.edge = ROWS - 4
        self.set_y(self.edge * 8)
        self.steps = 0

    def grow(self):
        self.edge += 1
        self.set_y(self.edge * 8)
        self.steps += 1


class Pieza(Sprite):
    def reset(self, col, row, shape_id):
        self.col = col
        self.row = row
        self.shape_id = shape_id
        self.rotation = randrange(4)
        self.show()
    
    def show(self):
        self.set_x(self.col * 8 + 64)
        self.set_y(self.row * 8)
        self.set_strip(stripes["vortris.png"])
        self.set_frame(self.shape_id * 4 + self.rotation)

    def rotate(self):
        self.rotation = (self.rotation + 1) % 4
        self.show()

    def grilla_actual(self):
        return ROTACIONES[self.shape_id][self.rotation]


class Tablero:
    def __init__(self):
        self.scoreboard = ScoreBoard()
        self.vortex = Vortex()
        self.unused_pieces = [Pieza() for _ in range(80)]
        self.used_pieces: list[Pieza] = []
        self.board = [[0 for _ in range(COLS)] for _ in range(ROWS - 1)]
        self.score = 0
        self.gameover = False
        self.spawn()

    def spawn(self):
        self.current = self.unused_pieces.pop()
        self.used_pieces.append(self.current)
        shape_id = randrange(7)
        self.current.reset(COLS // 2 - 2, 2, shape_id)
        if self.collision(self.current.col, self.current.row, self.current.rotation):
            self.gameover = True

        if DEBUG:
            print(f"Num. of pieces on the board: {len(self.used_pieces)}")

    def collision(self, new_col, new_row, new_rotation):
        grilla_pieza = ROTACIONES[self.current.shape_id][new_rotation]
        for y in range(4):
            for x in range(4):
                if grilla_pieza[y*4+x] == "X":
                    if x + new_col < 0 or x + new_col >= COLS or y + new_row >= ROWS - self.vortex.steps:
                        return True
                    if self.board[(new_row + y) - 1][(new_col + x) - 1]:
                        return True
        return False

    def freeze(self):
        grilla_pieza = ROTACIONES[self.current.shape_id][self.current.rotation]
        for y in range(4):
            for x in range(4):
                if grilla_pieza[y*4+x] == "X":
                    self.board[(y + self.current.row) - 1][(self.current.col + x) - 1] = self.current.shape_id + 1
        if DEBUG:
            for row in range(len(self.board)):
                for col in range(COLS):
                    print("X" if self.board[row][col] else "_", end='')
                print()
            print("*"*10)
        self.spawn()

    def move(self, dx, dy):
        new_col = self.current.col + dx
        new_row = self.current.row + dy
        if not self.collision(new_col, new_row, self.current.rotation):
            self.current.col = new_col
            self.current.row = new_row
            self.current.show()
            return True
        return False

    def rotate(self):
        new_rotation = (self.current.rotation + 1) % 4
        if not self.collision(self.current.col, self.current.row, new_rotation):
            self.current.rotation = new_rotation
            self.current.show()

    def drop(self):
        if not self.move(0, 1):
            self.freeze()
    
    def is_row_completed(self, row_id: int):
        return all([x > 0 for x in self.board[row_id]])

    def check_last_row(self):
        is_row_completed = self.is_row_completed(-1)

        if is_row_completed:
            self.score += COLS * 3 # More points if a line is fully completed
            self.scoreboard.setscore(self.score)
            self.vortex.grow()

        self.remove_covered_pieces()

    def vortex_eats(self):
        is_row_completed = self.is_row_completed(-1)
        if is_row_completed:
            self.score += COLS * 3 # More points if a line is fully completed
            self.scoreboard.setscore(self.score)
            self.vortex.grow()
        else:
            self.score += sum([x > 0 for x in self.board[-self.vortex.steps]])
            self.scoreboard.setscore(self.score)
            for piece in self.used_pieces:
                new_row = piece.row + 1
                piece.row = new_row
                piece.show()
        self.board = [[0 for _ in range(COLS)]] + self.board
        self.remove_covered_pieces()
        self.board.pop()
        
    def remove_covered_pieces(self):
        for piece in self.used_pieces:
            blocks_covered = 0
            grilla_pieza = ROTACIONES[piece.shape_id][piece.rotation]
            for y in range(4):
                for x in range(4):
                    if grilla_pieza[y*4+x] == "X":
                        row = (y + piece.row) - 1

                        if row >= ROWS - self.vortex.steps:
                            blocks_covered += 1
            if blocks_covered == 4:
                self.used_pieces.remove(piece)
                piece.set_y(255)
                piece.disable()
                self.unused_pieces.append(piece)

class Vortris(Scene):
    stripes_rom = "vortris"

    def on_enter(self):
        super().on_enter()
        self.game = Tablero()
        self.last_vortex_growth = utime.ticks_ms()

    def step(self):
        if self.game.gameover:
            print("Game Over! Score:", self.game.score)
            self.finished()

        if director.was_pressed(director.JOY_LEFT):
            self.game.move(-1, 0)
        if director.was_pressed(director.JOY_RIGHT):
            self.game.move(1, 0)
        if director.was_pressed(director.JOY_DOWN):
            self.game.drop()
        if director.was_pressed(director.JOY_UP):
            self.game.rotate()
        if director.was_pressed(director.BUTTON_A):
            while self.game.move(0, 1):
                pass
            self.game.freeze()

        # caída automática
        # fall_time += clock.get_rawtime()
        # if fall_time > 1000 // FPS:
        #     self.game.drop()
        #     fall_time = 0

        now = utime.ticks_ms()
        gap_time = utime.ticks_diff(now, self.last_vortex_growth) / 1000 # should be in secs.
        
        if gap_time >= VORTEX_TIME:
            print("Eating time!!")
            self.game.vortex_eats()
            self.last_vortex_growth = now

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Vortris()