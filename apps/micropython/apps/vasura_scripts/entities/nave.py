from apps.vasura_scripts.entities.entidad import *
from apps.vasura_scripts.entities.bala import *
from apps.vasura_scripts.managers.balas_manager import *

from ventilastation.director import stripes, director

from apps.vasura_scripts.estado import *

class Nave(Entidad):

    def __init__(self, scene, balas_manager: BalasManager):
        super().__init__(scene, stripes["ship-sprite-asym-sheet.png"])

        self.scene = scene
        self.balas : BalasManager = balas_manager

        self.set_perspective(1)
        
        self.velocidad_x = 1.5
        self.velocidad_y = 1.5

        self.set_estado(NaveSana)
        self.set_position(0, 50)

    def step(self):
        nuevo_estado = self.estado.step()
        if nuevo_estado:
            self.set_estado(nuevo_estado)
    
    def hit(self):
        if self.vulnerable():
            self.set_estado(Explotando)

    def vulnerable(self):
        return issubclass(type(self.estado), Vulnerable)
    
    def disparar(self):
        bala = self.balas.get()
        
        if not bala:
            return

        bala.reset()
        bala.set_direccion(self.direccion)

        if self.direccion == 1:
            x = self.x() + self.width()
        elif self.direccion == -1:
            x = self.x() - bala.width()

        y = self.y() + self.height() // 2 - bala.height() // 2
        
        bala.set_position(x, y)
    
    def morir(self):
        self.al_morir.disparar(self)
        self.set_estado(NaveExplotando)

    def respawn(self):
        self.set_direccion(1)
        self.set_estado(Invencible)
        self.set_position(0, 50)
   
    def procesar_input(self):
        target = [0, 0]
        
        if director.is_pressed(director.JOY_LEFT):
            target[0] += 1
        if director.is_pressed(director.JOY_RIGHT):
            target[0] += -1
        if director.is_pressed(director.JOY_DOWN):
            target[1] += -1
        if director.is_pressed(director.JOY_UP):
            target[1] += 1

        direccion = target[0]
        if direccion != 0:
            self.set_direccion(direccion)

        target[0] *= self.velocidad_x
        target[1] *= self.velocidad_y
        
        self.mover(*target)
        
        if director.was_pressed(director.BUTTON_A):
            self.disparar()


class NaveSana(Vulnerable):
    def on_enter(self):
        self.entidad.set_strip(stripes["ship-sprite-asym-sheet.png"])
        self.entidad.set_frame(0)

    def step(self):
        super().step()
        self.entidad.procesar_input()


class NaveExplotando(Explotando):
    def step(self):
        self.entidad.set_frame(self.entidad.frame() + 1)

        if self.entidad.frame() == self.total_frames:
            return Respawneando


class Respawneando(Deshabilitado):

    def on_enter(self):
        self.entidad.set_strip(stripes["ship-sprite-gray.png"])
        self.entidad.set_frame(0)
        self.frames = 0
        self.blink_rate = 6

    def step(self):
        self.frames += 1
        if (self.frames // self.blink_rate) % 2 == 0:
            self.entidad.set_frame(0)
        else:
            self.entidad.disable()


class Invencible(Estado):
    def on_enter(self):
        self.entidad.set_strip(stripes["ship-sprite-asym-sheet.png"])
        self.entidad.set_frame(0)
        self.frames_left = 60
        self.blink_rate = 4

    def step(self):
        super().step()
        self.entidad.procesar_input()

        self.frames_left -= 1
        if self.frames_left == 0:
            return NaveSana

        if (self.frames_left // self.blink_rate) % 2 == 0:
            self.entidad.set_direccion(self.entidad.direccion)
        else:
            self.entidad.disable()
