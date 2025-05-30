from apps.vasura_scripts.entities.entidad import *
from apps.vasura_scripts.entities.bala import *

from ventilastation.director import stripes, director

from apps.vasura_scripts.estado import *

class Nave(Entidad):

    def __init__(self, scene):
        super().__init__(stripes["ship-sprite-asym-sheet.png"])

        self.scene = scene
        
        self.set_perspective(1)
        
        self.set_x(0)
        self.set_y(self.height())
    
        self.estado = Vulnerable(self)

    def ArtificialStep(self):
        self.estado.step()
        
        target = [0, 0]
        
        if director.is_pressed(director.JOY_LEFT):
            target[0] += 1
        if director.is_pressed(director.JOY_RIGHT):
            target[0] += -1
        if director.is_pressed(director.JOY_DOWN):
            target[1] += -1
        if director.is_pressed(director.JOY_UP):
            target[1] += 1
        
        self.Move(*target)
        
        if director.was_pressed(director.BUTTON_A):
            self.disparar()


    def Move(self, x, y):
        self.set_x(self.x() + x)
        self.set_y(max(min(self.y() + y, 128-25), self.height()))

    
    def disparar(self):
        bala = self.scene.get_bala_libre()
        if not bala:
            return

        bala.reset()

        # TODO: aplicar orientación de la nave
        print(f"Bala: {bala.width()}x{bala.height()}")
        x = self.x() + bala.width() + 1
        y = self.y() - self.height() // 2 + bala.height() // 2
        bala.setPos(x, y)
        bala.setDirection(1)
