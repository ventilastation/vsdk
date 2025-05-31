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
        
    
        self.set_estado(NaveSana)

    def ArtificialStep(self):
        nuevo_estado = self.estado.step()
        if nuevo_estado:
            self.set_estado(nuevo_estado)
        
    
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


    def hit(self):
        self.set_estado(NaveExplotando)

    def respawn(self):
        self.set_position(0, 60)

class NaveSana(Vulnerable):
    #TODO mover velocidad a la clase de la nave
    velocidad :float = 1.5

    def on_enter(self):
        self.entidad.respawn()

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

        target[0] *= self.velocidad
        target[1] *= self.velocidad
        
        self.entidad.mover(*target)
        
        if director.was_pressed(director.BUTTON_A):
            self.entidad.disparar()

class NaveExplotando(Explotando):
    def step(self):
        cambio = super().step()
        if cambio:
            return NaveSana
