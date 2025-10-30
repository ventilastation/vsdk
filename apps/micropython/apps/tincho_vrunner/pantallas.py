from ventilastation.director import director, PIXELS, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from urandom import choice, randrange, seed

from apps.tincho_vrunner.niveles import Nivel01, make_me_a_planet

class Título(Scene):
    stripes_rom = "tincho_vrunner"

    def on_enter(self):
        super(Título, self).on_enter()

        make_me_a_planet("tincho_pescando.png")
        director.sound_play("tincho_vrunner/tincho_carpincho")

        self.call_later(5000, self.arrancar)

    def arrancar(self):
        director.pop()
        director.push(Nivel01())
        raise StopIteration()

    def step(self):
        if director.was_pressed(director.BUTTON_A):
            self.arrancar()

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()
