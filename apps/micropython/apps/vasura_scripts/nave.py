from ventilastation.sprites import Sprite
from ventilastation.director import director

class Nave():

    def __init__(self, strip):
        self.sprite = Sprite()
        self.sprite.set_strip(strip)
        self.sprite.set_x(0)
        self.sprite.set_y(self.sprite.height())
        self.sprite.set_frame(0)
        self.sprite.set_perspective(1)

    def ArtificialStep(self):
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

    def Move(self, x, y):
        self.sprite.set_x(self.sprite.x() + x)
        self.sprite.set_y(max(min(self.sprite.y() + y, 128-25), 0))

    def X(self):
        return self.sprite.x()

    def Y(self):
        return self.sprite.y()
