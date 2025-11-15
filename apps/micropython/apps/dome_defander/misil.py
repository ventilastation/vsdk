from urandom import randrange
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

# Misiles enemigos
class Misil:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["misil.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(2)
        self.sprite.disable()
        self.movement_delay = 0  # Usado para ralentizar el avance de los misiles

    def activar(self):
        self.sprite.set_x(randrange(90,165))  # Tiene que estar dentro del área que puede cubrir la mira (x > 80 && x < 175)
        self.sprite.set_y(0)
        self.sprite.set_frame(0)
        
    def desactivar(self):
        self.sprite.disable()

    def animar(self):
        self.y_actual = self.sprite.y()
        self.movement_delay = self.movement_delay + 1
        step = randrange(3,6)
        if self.movement_delay % step == 0:
            self.sprite.set_y(self.y_actual + 1)