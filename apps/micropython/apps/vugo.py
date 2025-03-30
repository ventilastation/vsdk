from ventilastation.director import director
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from ventilastation.imagenes import strips
from urandom import choice, randrange, seed

def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(strip)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(0)
    return planet

DAMERO_COLS = 3
DAMERO_ROWS = 12
TILE_WIDTH = 30
TILE_HEIGHT = 16
MONCHITO_HALFWIDTH = 7
MONCHITO_WIDTH = 14

COLS_CENTERS = [int(TILE_WIDTH * (c - DAMERO_COLS/2 + 0.5) ) for c in range(DAMERO_COLS)]
BUSH_COLS = [45, -105]
MONCHITO_DISPLAY_SHIFT = int(MONCHITO_HALFWIDTH)

def intersects(x1, w1, x2, w2):
    delta = min(x1, x2)
    x1 = (x1 - delta + 128) % 256
    x2 = (x2 - delta + 128) % 256
    return x1 < x2 + w2 and x1 + w1 > x2


class VugoGame(Scene):

    def on_enter(self):
        self.monchito = Sprite()
        self.monchito.set_x(-32)
        self.monchito.set_y(0)
        self.monchito.set_strip(strips.vugo.monchito_runs)
        self.monchito.set_frame(0)
        self.monchito.set_perspective(2)
        self.running_frame = 0

        # self.mario = Sprite()
        # self.mario.set_x(15)
        # self.mario.set_y(0)
        # self.mario.set_strip(strips.vugo.mario_runs)
        # self.mario.set_frame(0)
        # self.mario.set_perspective(2)

        self.grass_n_rocks = []
        for n in range(8):
            x = randrange(DAMERO_COLS)
            y = randrange(DAMERO_ROWS)
            gnr = Sprite()
            self.grass_n_rocks.append(gnr)
            gnr.set_strip(strips.vugo.obstacles)
            gnr.set_x(COLS_CENTERS[x] - TILE_WIDTH // 2)
            gnr.set_y(y * (TILE_HEIGHT-1) + 4 + randrange(8))
            gnr.set_perspective(1)
            if y > DAMERO_ROWS // 2:
                gnr.set_frame(randrange(2))


        self.fondos = {}
        for x in range(DAMERO_COLS):
            for y in range(DAMERO_ROWS):
                sf = Sprite()
                self.fondos[(x,y)] = sf 
                sf.set_strip(strips.vugo.moregrass)
                sf.set_x(COLS_CENTERS[x] - TILE_WIDTH // 2)
                sf.set_y(y * (TILE_HEIGHT-1))
                sf.set_perspective(1)
                sf.set_frame(randrange(3))

        self.bushes = []
        for y in range(DAMERO_ROWS):
            for x in range(2):
                sb = Sprite()
                self.bushes.append(sb)
                sb.set_strip(strips.vugo.bushes)
                sb.set_x(BUSH_COLS[x])
                sb.set_y(y * (TILE_HEIGHT-1))
                sb.set_perspective(1)
                sb.set_frame(x * 2 + randrange(2))

        self.nube = Sprite()
        self.nube.set_strip(strips.vugo.nube8bit)
        self.nube.set_perspective(2)
        self.nube.set_x(0)
        self.nube.set_y(3)
        self.nube.set_frame(x * 2 + randrange(2))
        self.nube_pos = 0

        self.fondo = make_me_a_planet(strips.vugo.bluesky)
        self.fondo.set_y(255)
        self.fondo.set_frame(0)
        director.music_play(b"other/piostart")
        self.walking_towards = 0
        self.monchito_pos = self.walking_towards
        self.running = True

    def is_monchito_chocado(self):
        vugo_x = (self.monchito_pos - MONCHITO_DISPLAY_SHIFT + 256) % 256
        for gnr in self.grass_n_rocks:
            if 4 < gnr.y() < 16 and gnr.frame() < 2:
                gnr_x = gnr.x()
                if intersects(gnr_x, TILE_WIDTH, vugo_x, MONCHITO_WIDTH):
                    return True

        return False

    def animar_paisaje(self):
        for f in self.fondos.values():
            fy = f.y()
            if (fy > 0):
                f.set_y(fy-1)
            else:
                f.set_y(DAMERO_ROWS * (TILE_HEIGHT-1))

        for gnr in self.grass_n_rocks:
            gy = gnr.y()
            if (gy > 0):
                gnr.set_y(gy-1)
            else:
                gnr.set_y(DAMERO_ROWS * (TILE_HEIGHT-1))
                gnr.set_x(COLS_CENTERS[randrange(3)] - TILE_WIDTH // 2)
                gnr.set_frame(randrange(2))

        for bush in self.bushes:
            by = bush.y()
            if (by > 0):
                bush.set_y(by-1)
            else:
                bush.set_y(DAMERO_ROWS * (TILE_HEIGHT-1))


    def step(self):

        # mf = (self.animation_frames // 3) % 6
        # self.mario.set_frame(mf)

        if director.was_pressed(director.JOY_RIGHT):
            self.walking_towards = COLS_CENTERS[0]

        if director.was_pressed(director.BUTTON_A):
            self.walking_towards = COLS_CENTERS[1]

        if director.was_pressed(director.JOY_LEFT):
            self.walking_towards = COLS_CENTERS[2]

        if self.running:
            self.running_frame += 1
            pf = (self.running_frame // 4) % 4
            self.monchito.set_frame(pf)
            self.animar_paisaje()

        self.monchito_pos = self.monchito_pos - (self.monchito_pos - self.walking_towards) // 4
        self.monchito.set_x(self.monchito_pos - MONCHITO_DISPLAY_SHIFT)

        self.nube_pos += 1
        self.nube.set_x(self.nube_pos // 8)

        if self.is_monchito_chocado():
            self.running = False
        else:
            self.running = True
            # FIXME

        if director.was_pressed(director.BUTTON_D): # or director.timedout:
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()
