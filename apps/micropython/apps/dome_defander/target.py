from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

# Indica dónde va a explotar el cascote de defensa
class Target:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["target.png"])
        self.sprite.set_perspective(2)
        self.sprite.set_frame(0)
        self.desactivar()


    def activar(self, center_x, center_y):
        self.sprite.set_x(center_x - self.sprite.width()//2)
        self.sprite.set_y(center_y - self.sprite.height()//2)
        self.delete = False

    def desactivar(self):
        self.sprite.disable()
        self.delete = True

    def mostrar(self):
        self.sprite.set_frame(0)

    def ocultar(self):
        self.sprite.disable()