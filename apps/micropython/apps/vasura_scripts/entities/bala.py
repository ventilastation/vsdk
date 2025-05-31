from apps.vasura_scripts.entities.entidad import *
from apps.vasura_scripts.managers.balas_manager import *

from ventilastation.director import stripes, director

from time import time

TIEMPO_VIDA_BALAS = 20
VELOCIDAD_BALAS = 5

class Bala(Entidad):
    tiempo_disparo : float = -1

    def __init__(self, scene):
        super().__init__(scene, stripes["bala.png"])

        self.set_perspective(1)
        
        self.set_y(self.height())

        self.disable()


    def step(self):
        self.set_x(self.x() + VELOCIDAD_BALAS * self.direccion)

        if time() >= self.tiempo_disparo + TIEMPO_VIDA_BALAS:
            self.al_morir(self)


    def reset(self):
        self.tiempo_disparo = time()
        self.set_frame(0)
        director.sound_play("vasura_espacial/disparo")


    def morir(self):
        self.tiempo_disparo = -1

        super().morir()

    #TODO cleanup
    def setDirection(self, direction):
        pass
