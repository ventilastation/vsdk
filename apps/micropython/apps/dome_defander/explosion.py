from ventilastation.director import stripes
from ventilastation.sprites import Sprite

EXPLOSION_FRAMES = 4

class Explosion:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["explosion2.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(2)
        self.sprite.disable()
        self.delete = True
        self.animation_delay = 1  # Contador que se usa para ralentizar la animación

    def activar(self, center_x, center_y):
        self.sprite.set_x(center_x - self.sprite.width()//2)
        self.sprite.set_y(center_y - 5)
        self.delete = False
        self.sprite.set_frame(0)

    def desactivar(self):
        self.sprite.disable()

    def colisiones(self, targets):
        def intersects(x1, w1, x2, w2):
            delta = min(x1, x2)
            x1 = (x1 - delta + 128) % 256
            x2 = (x2 - delta + 128) % 256
            return x1 < x2 + w2 and x1 + w1 > x2
        self.collisions = []

        for target in targets:
            other = target
            if (intersects(self.sprite.x(), self.sprite.width(), other.sprite.x(), other.sprite.width()) and
                intersects(self.sprite.y(), self.sprite.height(), other.sprite.y(), other.sprite.height())):
                self.collisions.append(target)
            
        return self.collisions

    def animar(self):
        current_frame = self.sprite.frame()
        if current_frame < EXPLOSION_FRAMES:
            if self.animation_delay % 3 == 0:
                self.sprite.set_frame(current_frame+1)
            self.animation_delay = self.animation_delay + 1
        else:
            self.delete = True