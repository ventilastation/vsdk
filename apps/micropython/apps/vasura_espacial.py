from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

from apps.vasura_scripts.managers.balas_manager import *
from apps.vasura_scripts.managers.enemigos_manager import *

from apps.vasura_scripts.entities.nave import Nave
from apps.vasura_scripts.entities.planeta import Planeta



class VasuraEspacial(Scene):
    stripes_rom = "vasura_espacial"

    def on_enter(self):
        super(VasuraEspacial, self).on_enter()

        #Inicializar managers
        self.balas = BalasManager(self)
        self.enemigos = EnemigosManager(self)

        self.nave = Nave(self, self.balas)

        self.planet = Planeta(self)
        self.planet.al_morir = self.muerte

        self.enemigos.get()
        


    def step(self):
        self.nave.ArtificialStep()
        self.enemigos.step()
        self.balas.step()

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()

    
    def muerte(self):
        self.nave.disable()
        director.music_play("vasura_espacial/game_over")
        self.finished()


    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return VasuraEspacial()
