from ventilastation.director import director, PIXELS, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from urandom import choice, randrange, seed

from apps.tincho_vrunner.tincho_level import make_me_a_planet, HUD_MODE, INFO_CONTROLES
from apps.tincho_vrunner.nivel_01 import Nivel01
from apps.tincho_vrunner.nivel_02 import Nivel02

Nivel01.siguiente = Nivel02

class Principal(Scene):
    stripes_rom = "tincho_vrunner"

    def on_enter(self):
        super(Principal, self).on_enter()


class Título(Scene):
    stripes_rom = "tincho_vrunner"
    ya_mostrado = False

    def on_enter(self):
        super(Título, self).on_enter()
        self.info = Sprite()
        self.info.set_strip(stripes["info.png"])
        self.info.set_x(128 - (self.info.width() // 2))
        self.info.set_y(5)
        self.info.set_frame(INFO_CONTROLES)
        self.info.set_perspective(HUD_MODE)

        director.music_off()
        make_me_a_planet("tincho_pescando.png")
        if not self.ya_mostrado:
            director.sound_play("tincho_vrunner/tincho_carpincho")
        self.ya_mostrado = True

        # self.call_later(5000, self.arrancar)

    def arrancar(self):
        director.push(Nivel01())

    def step(self):
        x_axis = director.is_pressed(director.JOY_LEFT) - director.is_pressed(director.JOY_RIGHT)
        if x_axis:
            new_x = self.info.x() + x_axis
            self.info.set_x(new_x)

        if director.was_pressed(director.BUTTON_A):
            self.arrancar()

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()
