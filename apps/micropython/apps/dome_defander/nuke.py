from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

from .explosion import *

class Nuke:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["nuke.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(2)
        self.sprite.set_x(128 - self.sprite.width()//2)
        self.sprite.set_y(36)
        self.sprite.disable()
        self.animation_delay = 1  # Contador que se usa para ralentizar la animación

    def reset(self):
        self.animation_delay = 1 
        self.sprite.set_frame(0)

    def desactivar(self):
        self.sprite.disable()

    def animar(self):
        current_frame = self.sprite.frame()

        if current_frame < EXPLOSION_FRAMES:
            if self.animation_delay % 8 == 0:
                self.sprite.set_frame(current_frame+1)
            
        else:
            if self.animation_delay % 8 == 0:
                self.sprite.set_frame(current_frame-1)

        self.animation_delay = self.animation_delay + 1