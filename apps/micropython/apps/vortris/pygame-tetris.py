# todo esto lo hizo copilot, no lo hice yo
# Tetris game implemented in Python using Pygame

import random
import sys
import pygame

# Game config
CELL_SIZE = 30
COLS = 16
ROWS = 12
WIDTH = CELL_SIZE * COLS
HEIGHT = CELL_SIZE * ROWS
FPS = 10

# Colors
BLACK = (0, 0, 0)
GRAY = (128, 128, 128)
COLORS = [
    (0, 255, 255),  # I
    (0, 0, 255),    # J
    (255, 165, 0),  # L
    (255, 255, 0),  # O
    (0, 255, 0),    # S
    (128, 0, 128),  # T
    (255, 0, 0),    # Z
]

# Tetromino shapes
SHAPES = [
    [[1, 1, 1, 1]],  # I
    [[1, 0, 0],
     [1, 1, 1]],     # J
    [[0, 0, 1],
     [1, 1, 1]],     # L
    [[1, 1],
     [1, 1]],        # O
    [[0, 1, 1],
     [1, 1, 0]],     # S
    [[0, 1, 0],
     [1, 1, 1]],     # T
    [[1, 1, 0],
     [0, 1, 1]],     # Z
]

def rotate(shape):
    return [ [ shape[y][x] for y in range(len(shape)) ] for x in range(len(shape[0])-1, -1, -1) ]

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

class Tetris:
    def __init__(self):
        self.board = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.score = 0
        self.gameover = False
        self.spawn()

    def spawn(self):
        self.current = Tetromino(COLS // 2 - 2, 0, random.randint(0, 6))
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

def draw_board(screen, game):
    screen.fill(BLACK)
    # Draw board
    for y in range(ROWS):
        for x in range(COLS):
            color = game.board[y][x]
            if color:
                pygame.draw.rect(screen, color, (x*CELL_SIZE, y*CELL_SIZE, CELL_SIZE, CELL_SIZE))
    # Draw current tetromino
    for x, y in game.current.get_coords():
        if y >= 0:
            pygame.draw.rect(screen, game.current.color, (x*CELL_SIZE, y*CELL_SIZE, CELL_SIZE, CELL_SIZE))
    # Draw grid
    for x in range(COLS):
        pygame.draw.line(screen, GRAY, (x*CELL_SIZE, 0), (x*CELL_SIZE, HEIGHT))
    for y in range(ROWS):
        pygame.draw.line(screen, GRAY, (0, y*CELL_SIZE), (WIDTH, y*CELL_SIZE))

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Tetris")
    clock = pygame.time.Clock()
    game = Tetris()
    fall_time = 0

    while True:
        if game.gameover:
            print("Game Over! Score:", game.score)
            pygame.quit()
            sys.exit()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT:
                    game.move(-1, 0)
                elif event.key == pygame.K_RIGHT:
                    game.move(1, 0)
                elif event.key == pygame.K_DOWN:
                    game.drop()
                elif event.key == pygame.K_UP:
                    game.rotate()
                elif event.key == pygame.K_SPACE:
                    while game.move(0, 1):
                        pass
                    game.freeze()

        fall_time += clock.get_rawtime()
        if fall_time > 1000 // FPS:
            game.drop()
            fall_time = 0

        draw_board(screen, game)
        pygame.display.flip()
        clock.tick(FPS)

if __name__ == "__main__":
    main()