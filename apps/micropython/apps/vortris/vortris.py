from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

COLS = 16
ROWS = 12

rotaciones = [
    [ # S
        "0000"
        "0000"
        "0110"
        "1100",
        "0000"
        "1000"
        "1100"
        "0100",
        "0000"
        "0000"
        "0110"
        "1100",
        "0000"
        "1000"
        "1100"
        "0100",
    ],
    [ # T
        "0000"
        "0000"
        "0100"
        "1110",
        "0000"
        "1000"
        "1100"
        "1000",
        "0000"
        "0000"
        "1110"
        "0100",
        "0000"
        "1100"
        "1100"
        "0100",
    ],
    [ # L
        "0000"
        "1000"
        "1000"
        "1100",
        "0000"
        "0000"
        "0010"
        "1110",
        "0000"
        "1100"
        "0100"
        "0100",
        "0000"
        "0000"
        "1110"
        "1000",
    ],
    [ # I
        "1000"
        "1000"
        "1000"
        "1000",
        "0000"
        "0000"
        "0000"
        "1111",
        "1000"
        "1000"
        "1000"
        "1000",
        "0000"
        "0000"
        "0000"
        "1111",
    ],
    [ # O
        "0000"
        "0000"
        "1100"
        "1100",
        "0000"
        "0000"
        "1100"
        "1100",
        "0000"
        "0000"
        "1100"
        "1100",
        "0000"
        "0000"
        "1100"
        "1100",
    ],
    [ # Z
        "0000"
        "0000"
        "1100"
        "0110",
        "0000"
        "0100"
        "1100"
        "1000",
        "0000"
        "0000"
        "1100"
        "0110",
        "0000"
        "0100"
        "1100"
        "1000",
    ],
    [ # J
        "0000"
        "0000"
        "1000"
        "1110",
        "0000"
        "0100"
        "0100"
        "1100",
        "0000"
        "0000"
        "1110"
        "0010",
        "0000"
        "1100"
        "1000"
        "1000",
    ],
]


class Pieza(Sprite):
    def reset(self, col, row, shape_id):
        self.col = col
        self.row = row
        self.shape_id = shape_id
        self.shape = SHAPES[shape_id]
        self.color = COLORS[shape_id]
        self.set_strip(stripes["vortris.png"])
        self.set_frame(self.shape_id * 4 + self.rotation)

    def rotate(self):
        self.rotation = (self.rotation + 1) % 4
        self.show()


class Tetromino:
    def __init__(self, x, y, shape_id):
        self.x = x
        self.y = y
        self.shape_id = shape_id
        self.shape = SHAPES[shape_id]
        self.color = COLORS[shape_id]

    def rotate(self):
        self.shape = rotate(self.shape)

    def get_coords(self):
        coords = []
        for dy, row in enumerate(self.shape):
            for dx, val in enumerate(row):
                if val:
                    coords.append((self.x + dx, self.y + dy))
        return coords


class Tablero:
    def __init__(self):
        self.unused_pieces = [Pieza() for _ in range(80)]
        self.board = bytearray(COLS * ROWS)
        self.score = 0
        self.gameover = False
        self.spawn()

    def spawn(self):
        self.current = self.unused_pieces.pop()
        self.current.reset(COLS // 2 - 2, 0, random.randint(0, 6))
        if self.collision(self.current.get_coords()):
            self.gameover = True

    def collision(self, coords):
        for x, y in coords:
            if x < 0 or x >= COLS or y < 0 or y >= ROWS:
                return True
            if y >= 0 and self.board[y][x]:
                return True
        return False

    def freeze(self):
        for x, y in self.current.get_coords():
            if y >= 0:
                self.board[y][x] = self.current.color
        self.clear_lines()
        self.spawn()

    def clear_lines(self):
        new_board = [row for row in self.board if any(cell is None for cell in row)]
        lines_cleared = ROWS - len(new_board)
        self.score += lines_cleared
        for _ in range(lines_cleared):
            new_board.insert(0, [None for _ in range(COLS)])
        self.board = new_board

    def move(self, dx, dy):
        moved = Tetromino(self.current.x + dx, self.current.y + dy, self.current.shape_id)
        moved.shape = self.current.shape
        if not self.collision(moved.get_coords()):
            self.current = moved
            return True
        return False

    def rotate(self):
        rotated = Tetromino(self.current.x, self.current.y, self.current.shape_id)
        rotated.shape = rotate(self.current.shape)
        if not self.collision(rotated.get_coords()):
            self.current = rotated

    def drop(self):
        if not self.move(0, 1):
            self.freeze()


class Vortris(Scene):
    stripes_rom = "vortris"

    def on_enter(self):
        super().on_enter()
        self.game = Tablero()

    def step(self):
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

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Vortris()