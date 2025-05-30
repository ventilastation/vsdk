from ventilastation.sprites import Sprite
from ventilastation.director import director

from apps.vasura_scripts.estado import *

class Nave():

    def __init__(self, scene, strip):
        self.scene = scene
        self.sprite = Sprite()
        self.sprite.set_strip(strip)
        self.sprite.set_x(0)
        self.sprite.set_y(self.sprite.height())
        self.sprite.set_frame(0)
        self.sprite.set_perspective(1)
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
        self.sprite.set_x(self.sprite.x() + x)
        self.sprite.set_y(max(min(self.sprite.y() + y, 128-25), self.sprite.height()))

    def X(self):
        return self.sprite.x()

    def Y(self):
        return self.sprite.y()

    
    def disparar(self):
        bala = self.scene.get_bala_libre()
        if not bala:
            return

        bala.reset()

        # TODO: aplicar orientación de la nave
        print(f"Bala: {bala.sprite.width()}x{bala.sprite.height()}")
        x = self.X() + bala.sprite.width() + 1
        y = self.Y() - self.sprite.height() // 2 + bala.sprite.height() // 2
        bala.setPos(x, y)
        bala.setDirection(1)



class Bala():
    def __init__(self, scene, strip):
        self.scene = scene
        self.sprite = Sprite()
        self.sprite.set_strip(strip)
        self.sprite.set_x(0)
        self.sprite.set_y(self.sprite.height())
        self.sprite.set_perspective(1)
        self.sprite.set_frame(0)
        self.sprite.disable()


    def step(self):
        self.sprite.set_x(self.sprite.x() + 5)


    def reset(self):
        self.sprite.set_frame(0)
        director.sound_play("vasura_espacial/disparo")


    def setPos(self, x,y):
        self.sprite.set_x(x)
        self.sprite.set_y(y)


    def setDirection(self, direction):
        pass
