from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

class HitExplosion:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["nuke.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(2)
        self.sprite.disable()
        self.delete = True
        self.animation_delay = 1  # Contador que se usa para ralentizar la animación

    def activar(self, center_x):
        self.sprite.set_x(center_x - self.sprite.width()//2)
        self.sprite.set_y(36)
        self.delete = False
        self.sprite.set_frame(0)

    def desactivar(self):
        self.sprite.disable()

    def animar(self):
        current_frame = self.sprite.frame()
        if current_frame < 2:
            if self.animation_delay % 4 == 0:
                self.sprite.set_frame(current_frame+1)
            self.animation_delay = self.animation_delay + 1
        else:
            self.delete = True