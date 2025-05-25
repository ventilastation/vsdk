from ventilastation.sprites import Sprite
from ventilastation.director import director

class Nave():

    def __init__(self, strip):
        self.nave_sprite = Sprite()
        self.nave_sprite.set_x(0)
        self.nave_sprite.set_y(0)
        self.nave_sprite.set_strip(strip)
        self.nave_sprite.set_frame(0)
        self.nave_sprite.set_perspective(2)
        pass

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
        self.nave_sprite.set_x(self.nave_sprite.x() + x)
        self.nave_sprite.set_y(max(min(self.nave_sprite.y() + y, 36), 0))

    def X(self):
        return self.nave_sprite.x()
