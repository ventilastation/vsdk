from apps.vasura_scripts.entities.entidad import *

from ventilastation.director import stripes, director

class Bala(Entidad):
    
    def __init__(self, scene):
        super().__init__(stripes["bala.png"])

        self.scene = scene
        
        self.set_perspective(1)
        
        self.set_y(self.height())

        self.disable()


    def step(self):
        self.set_x(self.x() + 5)


    def reset(self):
        self.set_frame(0)
        director.sound_play("vasura_espacial/disparo")


    def setPos(self, x,y):
        self.set_x(x)
        self.set_y(y)


    def setDirection(self, direction):
        pass