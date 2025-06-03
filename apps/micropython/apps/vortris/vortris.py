import utime
from urandom import randrange
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from .rotaciones import ROTACIONES

COLS = 16
ROWS = 18

DEBUG = True

class Vortex(Sprite):
    def __init__(self):
        super().__init__()
        self.set_strip(stripes["fondo.png"])
        self.set_perspective(0)
        self.set_frame(0)
        self.set_x(0)
        self.row = ROWS - 4
        self.set_y(self.row * 8)

    def grow(self):
        self.row += 1
        self.set_y(self.row * 8)


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
        self.unused_pieces = [Pieza() for _ in range(80)]
        self.board = [[0 for _ in range(COLS)] for _ in range(ROWS)]
        self.score = 0
        self.gameover = False
        self.vortex = Vortex()
        self.spawn()

    def spawn(self):
        self.current = self.unused_pieces.pop()
        shape_id = randrange(7)
        self.current.reset(COLS // 2 - 2, 2, shape_id)
        if self.collision(self.current.col, self.current.row, self.current.rotation):
            self.gameover = True

    def collision(self, new_col, new_row, new_rotation):
        grilla_pieza = ROTACIONES[self.current.shape_id][new_rotation]
        for y in range(4):
            for x in range(4):
                if grilla_pieza[y*4+x] == "X":
                    if x + new_col < 0 or x + new_col >= COLS or y + new_row >= ROWS:
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
            for row in range(ROWS):
                for col in range(COLS):
                    print("X" if self.board[row][col] else "_", end='')
                print()
        self.spawn()

    def clear_lines(self):
        new_board = [row for row in self.board if any(cell is None for cell in row)]
        lines_cleared = ROWS - len(new_board)
        self.score += lines_cleared
        for _ in range(lines_cleared):
            new_board.insert(0, [None for _ in range(COLS)])
        self.board = new_board

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
        
        if gap_time >= 10:
            self.game.vortex.grow()
            self.last_vortex_growth = now

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Vortris()