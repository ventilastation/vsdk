from ventilastation.director import director, PIXELS, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from urandom import choice, randrange, seed


def make_me_a_planet(strip):
    planet = sprites.Sprite()
    planet.set_strip(stripes[strip])
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet

CENTRO_WIDTH = 32

DAMERO_COLS = 3
DAMERO_ROWS = 8
TILE_WIDTH = 32
TILE_HEIGHT = 16

ROWS_HEIGHT = TILE_HEIGHT * DAMERO_ROWS
ROWS_HI_HEIGHT = TILE_HEIGHT * (DAMERO_ROWS - 5)
ROWS_LO_HEIGHT = TILE_HEIGHT * (DAMERO_ROWS - 3)

COLS_CENTERS = [int(TILE_WIDTH * (c - DAMERO_COLS/2 + 0.5) ) for c in range(DAMERO_COLS)]

# FIXME
DESFAZAJES = [0, 1, 2, 1, 1, 0, -1, -1]
VELOCIDADES = [-5, -4, -3, -2, -1, -1/2, -1/4, -1/8, 0, 1/8, 1/4, 1/2, 1, 2, 3, 4, 5]

def get_damero_strip(x, y, tile_x, tile_y):
    #return stripes["damero.png"]
    # return stripes["suelo.png"]
    return stripes["suelo_dof.png"]

def get_damero_frame(x, y, tile_x, tile_y):
    #return (tile_x + tile_y) % 2
    # return 0
    if y < ROWS_HI_HEIGHT:
        return 0
    elif y < ROWS_LO_HEIGHT:
        return 1
    else:
        return 2
    # return tile_y % DAMERO_ROWS // 2

class Nivel01(Scene):
    stripes_rom = "vvv"

    def on_enter(self):
        super(Nivel01, self).on_enter()

        self.tiles_centro = []
        for i in range(256 // CENTRO_WIDTH):
            tile = Sprite()
            self.tiles_centro.append(tile)
            tile.set_strip(stripes["centro.png"])
            tile.set_x(i * CENTRO_WIDTH)
            tile.set_y(54-tile.height())
            tile.set_frame(0)
            tile.set_perspective(2)

        self.tiles_suelo = {}
        for tile_x in range(DAMERO_COLS):
            x = COLS_CENTERS[tile_x] - TILE_WIDTH // 2
            for tile_y in range(DAMERO_ROWS):
                tile = Sprite()
                self.tiles_suelo[(tile_x, tile_y)] = tile
                tile.set_x(x + DESFAZAJES[tile_y]*2)
                y = tile_y * TILE_HEIGHT
                tile.set_y(y)
                tile.set_perspective(1)
                tile.set_strip(get_damero_strip(x, y, tile_x, tile_y))
                tile.set_frame(get_damero_frame(x, y, tile_x, tile_y))

        self.bg = Sprite()
        self.bg.set_strip(stripes["negro.png"])
        self.bg.set_x(0)
        self.bg.set_y(255)
        self.bg.set_frame(0)
        self.bg.set_perspective(0)

        self.run_vel = 1/4
        self.run_acc = 0
        self.has_centro = True

        self.duration = 1000
        self.dir_acelerar = 1
        self.call_later(self.duration, self.acelerar)

    def step(self):
        if self.run_vel >= 1 or self.run_vel <= -1:
            self.animar_paisaje(self.run_vel)
        else:
            self.run_acc += self.run_vel
            if int(self.run_acc):
                self.animar_paisaje(int(self.run_acc))
                self.run_acc = 0

        y_axis = director.was_released(director.JOY_UP) - director.was_released(director.JOY_DOWN)
        new_index = VELOCIDADES.index(self.run_vel) + y_axis
        self.run_vel = VELOCIDADES[max(min(new_index, len(VELOCIDADES)-1), 0)]

        if director.was_pressed(director.BUTTON_A):
            self.run_vel = 0
            self.has_centro = not self.has_centro
            for t in self.tiles_centro:
                t.disable() if not self.has_centro else t.set_frame(0)

        if director.was_pressed(director.BUTTON_D): # or director.timedout:
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()

    def animar_paisaje(self, dy):
        for tile in self.tiles_suelo.values():
            y = tile.y() - dy
            if y > ROWS_HEIGHT:
                tile.set_y(y - ROWS_HEIGHT)
            elif y < 0:
                tile.set_y(ROWS_HEIGHT + y)
            else:
                tile.set_y(y)
            tile.set_frame(get_damero_frame(0, tile.y(), 0, 0))

    def acelerar(self):
        cur_index = VELOCIDADES.index(self.run_vel)
        if cur_index == 0 or cur_index == len(VELOCIDADES)-1:
            self.dir_acelerar *= -1
        new_index = VELOCIDADES.index(self.run_vel) + self.dir_acelerar
        self.run_vel = VELOCIDADES[max(min(new_index, len(VELOCIDADES)-1), 0)]
        self.call_later(self.duration, self.acelerar)
