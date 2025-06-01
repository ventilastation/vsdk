from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

from apps.vasura_scripts.managers.balas_manager import *
from apps.vasura_scripts.managers.enemigos_manager import *
from apps.vasura_scripts.managers.gameplay_manager import *

from apps.vasura_scripts.managers.spawner_enemigos import *

from apps.vasura_scripts.entities.nave import Nave
from apps.vasura_scripts.entities.planeta import Planeta



class VasuraEspacial(Scene):
    stripes_rom = "vasura_espacial"

    def on_enter(self):
        super(VasuraEspacial, self).on_enter()

        self.balas = BalasManager(self)
        self.enemigos = EnemigosManager(self)
        self.spawner = SpawnerEnemigos(self.enemigos)

        self.nave = Nave(self, self.balas)

        self.planet = Planeta(self)

        self.gameplay_manager = GameplayManager(self.nave)

        self.planet.al_ser_golpeado.suscribir(self.gameplay_manager.on_planet_hit)
        
        self.gameplay_manager.al_perder_vida.suscribir(self.planet.al_perder_vida)

        self.gameplay_manager.game_over.suscribir(self.muerte)

        self.enemigos.al_morir_enemigo.suscribir(self.gameplay_manager.al_morir_enemigo)

        self.spawner.spawnear_enemigo()


    def step(self):
        self.nave.ArtificialStep()
        self.enemigos.step()
        self.balas.step()
        self.gameplay_manager.step()
        self.spawner.step()

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        #BUG hacer cleanup porque no se puede volver a entrar al juego
        director.pop()
        raise StopIteration()

    
    def muerte(self):
        director.music_play("vasura_espacial/game_over")
        self.finished()


    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return VasuraEspacial()
