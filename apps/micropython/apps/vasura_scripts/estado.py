from ventilastation.director import director, stripes
from apps.vasura_scripts.entities.entidad import *

from math import sqrt
from urandom import randint

class Estado:
    strip : int = None
    entidad : Entidad

    def __init__(self, entidad : Entidad):
        self.entidad = entidad


    def on_enter(self):
        self.entidad.set_frame(0)


    def step(self):
        pass


    def on_exit(self):
        pass



class Deshabilitado(Estado):
    def on_enter(self):
        self.entidad.disable()



class Explotando(Estado):  # Anarquía
    def __init__(self, entidad):
        super().__init__(entidad)
        self.strip = "explosion.png"
        self.total_frames = 6

    def on_enter(self):
        super().on_enter()
        director.sound_play("vasura_espacial/explosion_enemigo")
        
        self.entidad.disable()

        center_x = self.entidad.x() + self.entidad.width() // 2
        center_y = self.entidad.y() + self.entidad.height() // 2
        
        self.entidad.set_strip(stripes[self.strip])

        new_x = center_x - self.entidad.width() // 2
        new_y = center_y - self.entidad.height() // 2

        self.entidad.set_position(new_x, new_y)

        self.entidad.set_frame(0)

    def step(self):
        self.entidad.set_frame(self.entidad.frame() + 1)

        if self.entidad.frame() == self.total_frames:
            self.entidad.morir()



class Vulnerable(Estado):
    #TODO mover esto a un lugar donde nos ahorremos el chequeo de tipos
    def step(self):
        es_nave = self.entidad.__class__.__name__ == "Nave"

        if not es_nave:
            nave = self.entidad.scene.nave
            
            if not isinstance(nave.estado, Deshabilitado) and \
                self.entidad.collision([nave]):
                nave.hit(0)
                
                return Explotando

        bala : Bala = self.entidad.scene.manager_balas.get_bala_colisionando(self.entidad)
        if bala and self.entidad.hit(bala.x()):
            return Explotando



class Bajando(Vulnerable):
    def step(self):
        cambio = super().step()
        if cambio:
            return cambio

        self.entidad.mover(0, self.entidad.velocidad_y)

        if self.entidad.y() + self.entidad.height() >= self.entidad.scene.planet.get_borde_y():
            self.entidad.scene.planet.hit()
            
            return Explotando


class ChillerBajando(Bajando):
    def on_enter(self):
        super().on_enter()
        self.frames_left = 30
        self.entidad.set_direccion(-self.entidad.direccion)

    def step(self):
        cambio = super().step()
        if cambio:
            return cambio
        
        self.frames_left -= 1
        if self.frames_left == 0:
            return Orbitando


class Orbitando(Vulnerable):
    def on_enter(self):
        super().on_enter()
        self.frames_left = 128

    def step(self):
        cambio = super().step()
        if cambio:
            return cambio

        self.frames_left -= 1
        if self.frames_left == 0:
            return ChillerBajando

        e = self.entidad
        self.entidad.mover(e.velocidad_x * e.direccion, 0)


class Persiguiendo(Vulnerable):
    def step(self):
        cambio = super().step()
        if cambio:
            return cambio

        nave = self.entidad.scene.nave
        nave_x, nave_y = nave.get_position()

        e = self.entidad
        x, y = e.get_position()
        delta_x = nave_x - x
        delta_x = delta_x if abs(delta_x) < 128 else -delta_x
        delta_y = nave_y - y
        mag = sqrt(delta_x ** 2 + delta_y ** 2)

        delta_x *= e.velocidad_x / mag
        delta_y *= e.velocidad_y / mag
        e.mover(delta_x, delta_y)

class YendoDerecho(Vulnerable):
    def step(self):
        cambio = super().step()
        if cambio:
            return cambio

        self.entidad.mover(self.entidad.velocidad_x * self.entidad.direccion, 0)
        

class BajandoEnEspiral(Bajando):
    def on_enter(self):
        self.frames_cambio_direccion : int = 160
        self.probabilidad_cambio_direccion : int = 25
        self.frames_left = self.frames_cambio_direccion

        roll = randint(0, 100)
        self.entidad.set_direccion(1 if roll < 50 else -1)

    def step(self):
        cambio = super().step()
        if cambio:
            return cambio
        
        self.frames_left -= 1

        self.entidad.mover(self.entidad.velocidad_x * self.entidad.direccion, 0)

        if self.frames_left == 0:
            self.frames_left = self.frames_cambio_direccion
            
            if randint(0, 100) < self.probabilidad_cambio_direccion:
                self.entidad.set_direccion(self.entidad.direccion * -1)