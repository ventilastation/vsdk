from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

from apps.vasura_scripts.nave import Nave, Bala
from apps.vasura_scripts.enemigo import *

LIMITE_BALAS = 20

class VasuraEspacial(Scene):
    stripes_rom = "vasura_espacial"

    def on_enter(self):
        super(VasuraEspacial, self).on_enter()

        self.nave = Nave(self, stripes["ship-sprite-asym.png"])

        self.planet = Sprite()
        self.planet.set_strip(stripes["game-center.png"])
        self.planet.set_perspective(0)
        self.planet.set_frame(0)
        self.planet.set_y(160)

        self.enemigo = Driller(self, 50, 0)

        self.balas_libres = [
            Bala(self, stripes["bala.png"]) 
            for _ in range(LIMITE_BALAS)
        ]

        self.balas_usadas = []


    def step(self):
        self.nave.ArtificialStep()
        self.enemigo.step()
        [bala.step() for bala in self.balas_usadas]

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()

    def get_bala_libre(self):
        if not self.balas_libres:
            return None

        bala = self.balas_libres.pop()
        self.balas_usadas.append(bala)

        return bala


    def get_colision_bala(self, sprite):
        balas_sprites = [x.sprite for x in self.balas_usadas]
        bala = sprite.collision(balas_sprites)
        if bala:
            return self.balas_usadas[balas_sprites.index(bala)]

    def liberar_bala(self, bala):
        bala.sprite.disable()
        self.balas_usadas.remove(bala)
        self.balas_libres.append(bala)

    
    def muerte(self):
        self.nave.sprite.disable()
        director.music_play("vasura_espacial/game_over")
        self.finished()


    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return VasuraEspacial()
