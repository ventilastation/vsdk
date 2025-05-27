from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

from apps.vasura_scripts.nave import Nave
from apps.vasura_scripts.enemigo import *


class VasuraEspacial(Scene):
    stripes_rom = "vasura_espacial"

    def on_enter(self):
        super(VasuraEspacial, self).on_enter()

        self.nave = Nave(stripes["ship-sprite-asym.png"])

        self.planet = Sprite()
        self.planet.set_strip(stripes["game-center.png"])
        self.planet.set_perspective(0)
        self.planet.set_frame(0)
        self.planet.set_y(160)

        self.enemigo = Driller(self, 50, 0)


    def step(self):
        self.nave.ArtificialStep()
        self.enemigo.step()


    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return VasuraEspacial()
