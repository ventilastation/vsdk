from apps.vasura_scripts.entities.entidad import *
from apps.vasura_scripts.entities.bala import *
from apps.vasura_scripts.managers.balas_manager import *

from ventilastation.director import stripes, director

from apps.vasura_scripts.estado import *

class Nave(Entidad):
    balas : BalasManager = None

    def __init__(self, scene, balas_manager:BalasManager):
        super().__init__(scene, stripes["ship-sprite-asym-sheet.png"])

        self.scene = scene
        self.balas = balas_manager

        self.set_perspective(1)
        
        self.velocidad_x = 1.5
        self.velocidad_y = 1.5

        self.set_estado(NaveSana)
        self.set_position(0, 50)

    def ArtificialStep(self):
        nuevo_estado = self.estado.step()
        if nuevo_estado:
            self.set_estado(nuevo_estado)
    
    def hit(self):
        self.morir()
    
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
    
    def morir(self, por_bala : bool = False):
        self.set_estado(Deshabilitado)
        self.al_morir.disparar(self)

    def respawn(self):
        self.set_estado(NaveSana)
        self.set_position(0, 50)

class NaveSana(Vulnerable):
    def on_enter(self):
        self.entidad.set_frame(0)

    def step(self):
        super().step()
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
            self.entidad.set_direccion(direccion)

        target[0] *= self.entidad.velocidad_x
        target[1] *= self.entidad.velocidad_y
        
        self.entidad.mover(*target)
        
        if director.was_pressed(director.BUTTON_A):
            self.entidad.disparar()