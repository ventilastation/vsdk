from utime import ticks_ms, ticks_diff, ticks_add

from apps.vasura_scripts.entities.entidad import *

from ventilastation.director import stripes, director

TIEMPO_VIDA_BALAS = 20

class Bala(Entidad):
    tiempo_de_muerte : int = -1

    def __init__(self, scene):
        super().__init__(scene, stripes["bala.png"])

        self.velocidad_x = 4.5
        self.set_perspective(1)
        self.set_y(self.height())
        self.disable()


    def step(self):
        self.mover(self.velocidad_x * self.direccion, 0)

        if ticks_diff(self.tiempo_de_muerte, ticks_ms()) <= 0:
            self.morir()


    def reset(self):
        self.tiempo_de_muerte = ticks_add(ticks_ms(), TIEMPO_VIDA_BALAS * 1000)
        self.set_frame(0)
        director.sound_play("vasura_espacial/disparo")

    def morir(self):
        self.tiempo_de_muerte = -1
        self.disable()
        
        self.al_morir.disparar(self)
