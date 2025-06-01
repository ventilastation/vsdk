from apps.vasura_scripts.entities.entidad import *
from apps.vasura_scripts.managers.balas_manager import *

from ventilastation.director import stripes, director

from time import time

TIEMPO_VIDA_BALAS = 20

class Bala(Entidad):
    tiempo_disparo : float = -1

    def __init__(self, scene):
        super().__init__(scene, stripes["bala.png"])

        self.velocidad_x = 5

        self.set_perspective(1)
        
        self.set_y(self.height())

        self.disable()


    def step(self):
        
        self.mover(self.velocidad_x * self.direccion, 0)

        if time() >= self.tiempo_disparo + TIEMPO_VIDA_BALAS:
            self.al_morir(self)


    def reset(self):
        self.tiempo_disparo = time()
        self.set_frame(0)
        director.sound_play("vasura_espacial/disparo")


    def morir(self):
        self.tiempo_disparo = -1

        super().morir()
