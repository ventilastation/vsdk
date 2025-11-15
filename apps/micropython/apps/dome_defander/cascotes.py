from urandom import randrange
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

from .target import Target

# Proyectiles que dispara el jugador
class Cascote:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["cascote.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(2)
        self.sprite.disable()
        self.delete = True

        self.target = Target()
        self.target_counter = 0

    def activar(self, torreta, target_center_x):
        self.torreta = torreta
        self.target_center_x = target_center_x  # valor del **centro** del objetivo
        self.delete = False
        self.sprite.set_frame(0)
        
        # Torretas isquierdas, de izquierda a derecha
        if torreta == 1:
            self.sprite.set_x(64 - self.sprite.width())
            self.sprite.set_y(13 + 2)
            self.target.activar(self.target_center_x, 13+4)
        elif torreta == 2:
            self.sprite.set_x(64 - self.sprite.width())
            self.sprite.set_y(23 + 2)
            self.target.activar(self.target_center_x, 23+4)
        elif torreta == 3:
            self.sprite.set_x(64 - self.sprite.width())
            self.sprite.set_y(33 + 2)
            self.target.activar(self.target_center_x, 33+4)
        # Torretas derechas, de izquierda a derecha
        elif torreta == 4:
            self.sprite.set_x(192 - self.sprite.width())
            self.sprite.set_y(33 + 2)
            self.target.activar(self.target_center_x, 33+4)
        elif torreta == 5:
            self.sprite.set_x(192 - self.sprite.width())
            self.sprite.set_y(23 + 2)
            self.target.activar(self.target_center_x, 23+4)
        elif torreta == 6:
            self.sprite.set_x(192 - self.sprite.width())
            self.sprite.set_y(13 + 2)
            self.target.activar(self.target_center_x, 13+4)
    
    def desactivar(self):
        self.sprite.disable()
        self.target_counter = 0
        self.target.desactivar()

    def mover(self):    
        x_actual = self.sprite.x()
        centrer_x = x_actual + (self.sprite.width() // 2)

        if self.target_counter % 2:
            self.target.mostrar()
        else:
            self.target.ocultar()
        self.target_counter = self.target_counter + 1

        if self.torreta == 1 or self.torreta == 2 or self.torreta == 3 :
            if centrer_x <= self.target_center_x:
                self.sprite.set_x(x_actual + 2)
            else:
                self.delete = True
                self.target.desactivar()
        else:
            if centrer_x >= self.target_center_x:
                self.sprite.set_x(x_actual - 2)
            else:
                self.delete = True
                self.target.desactivar()