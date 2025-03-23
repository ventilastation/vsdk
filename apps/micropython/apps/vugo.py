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

class VugoGame(Scene):

    def on_enter(self):
        self.monchito = Sprite()
        self.monchito.set_x(-32)
        self.monchito.set_y(0)
        self.monchito.set_strip(strips.vugo.monchito_runs)
        self.monchito.set_frame(0)
        self.monchito.set_perspective(2)
        self.animation_frames = 0

        self.mario = Sprite()
        self.mario.set_x(15)
        self.mario.set_y(0)
        self.mario.set_strip(strips.vugo.mario_runs)
        self.mario.set_frame(0)
        self.mario.set_perspective(2)

        fondos = {}
        for x in range(3):
            for y in range(7):
                sf = Sprite()
                fondos[(x,y)] = sf 
                sf.set_strip(strips.vugo.moregrass)
                sf.set_x(30 * x - 45)
                sf.set_y(y * 30)
                sf.set_perspective(1)
                sf.set_frame(randrange(4))

        # self.fondo = make_me_a_planet(strips.vyruss.tierra)
        # self.fondo.set_y(255)
        # self.fondo.set_frame(0)
        director.music_play(b"other/piostart")

    def step(self):
        self.animation_frames += 1
        pf = (self.animation_frames // 4) % 4
        self.monchito.set_frame(pf)

        mf = (self.animation_frames // 3) % 6
        self.mario.set_frame(mf)

        if director.was_pressed(director.BUTTON_D): # or director.timedout:
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()
