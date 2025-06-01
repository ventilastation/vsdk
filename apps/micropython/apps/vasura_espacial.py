from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

from apps.vasura_scripts.managers.balas_manager import *
from apps.vasura_scripts.managers.enemigos_manager import *
from apps.vasura_scripts.managers.gameplay_manager import *

from apps.vasura_scripts.entities.nave import Nave
from apps.vasura_scripts.entities.planeta import Planeta



class VasuraEspacial(Scene):
    stripes_rom = "vasura_espacial"

    def on_enter(self):
        super(VasuraEspacial, self).on_enter()

        self.balas = BalasManager(self)
        self.enemigos = EnemigosManager(self)

        self.nave = Nave(self, self.balas)

        self.planet = Planeta(self)

        self.gameplay_manager = GameplayManager(self.nave)

        self.planet.al_ser_golpeado = self.gameplay_manager.on_planet_hit
        
        self.gameplay_manager.suscribir_perder_vida(self.planet.al_perder_vida)
        self.gameplay_manager.suscribir_perder_vida(lambda _: self.enemigos.get())

        self.gameplay_manager.suscribir_game_over(self.finished)

        self.enemigos.al_morir_enemigo = self.gameplay_manager.al_morir_enemigo

        self.enemigos.get()


    def step(self):
        self.nave.ArtificialStep()
        self.enemigos.step()
        self.balas.step()
        self.gameplay_manager.step()

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()

    
    def muerte(self):
        director.music_play("vasura_espacial/game_over")
        #self.finished()


    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return VasuraEspacial()
