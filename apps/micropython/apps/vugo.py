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

COLS_CENTERS = [int(TILE_WIDTH * (c - DAMERO_COLS/2 + 0.5) ) for c in range(DAMERO_COLS)]
MONCHITO_DISPLAY_SHIFT = int(MONCHITO_HALFWIDTH)

class VugoGame(Scene):

    def on_enter(self):
        self.monchito = Sprite()
        self.monchito.set_x(-32)
        self.monchito.set_y(0)
        self.monchito.set_strip(strips.vugo.monchito_runs)
        self.monchito.set_frame(0)
        self.monchito.set_perspective(2)
        self.animation_frames = 0

        # self.mario = Sprite()
        # self.mario.set_x(15)
        # self.mario.set_y(0)
        # self.mario.set_strip(strips.vugo.mario_runs)
        # self.mario.set_frame(0)
        # self.mario.set_perspective(2)

        self.fondos = {}
        for x in range(DAMERO_COLS):
            for y in range(DAMERO_ROWS):
                sf = Sprite()
                self.fondos[(x,y)] = sf 
                sf.set_strip(strips.vugo.moregrass)
                sf.set_x(COLS_CENTERS[x] - TILE_WIDTH // 2)
                sf.set_y(y * (TILE_HEIGHT-1))
                sf.set_perspective(1)
                sf.set_frame(randrange(4))

        # self.fondo = make_me_a_planet(strips.vyruss.tierra)
        # self.fondo.set_y(255)
        # self.fondo.set_frame(0)
        director.music_play(b"other/piostart")
        self.walking_towards = 0
        self.monchito_pos = self.walking_towards

    def step(self):
        self.animation_frames += 1
        pf = (self.animation_frames // 4) % 4
        self.monchito.set_frame(pf)

        # mf = (self.animation_frames // 3) % 6
        # self.mario.set_frame(mf)

        for f in self.fondos.values():
            fy = f.y()
            if (fy > 0):
                f.set_y(fy-1)
            else:
                f.set_y(DAMERO_ROWS * (TILE_HEIGHT-1))


        if director.was_pressed(director.JOY_RIGHT):
            self.walking_towards = COLS_CENTERS[0]

        if director.was_pressed(director.BUTTON_A):
            self.walking_towards = COLS_CENTERS[1]

        if director.was_pressed(director.JOY_LEFT):
            self.walking_towards = COLS_CENTERS[2]

        self.monchito_pos = self.monchito_pos - (self.monchito_pos - self.walking_towards) // 4
        self.monchito.set_x(self.monchito_pos - MONCHITO_DISPLAY_SHIFT)

        if director.was_pressed(director.BUTTON_D): # or director.timedout:
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()
