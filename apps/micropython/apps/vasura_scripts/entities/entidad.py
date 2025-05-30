from ventilastation.sprites import Sprite

class Entidad(Sprite):

    def __init__(self, strip : int, x : int = 0, y : int = 0):
        super().__init__()

        self.set_strip(strip)

        self.set_frame(0)

        self.set_x(x)
        self.set_y(y)
    
    def step(self):
        pass

    def mover(self, x, y):
        self.set_x(self.x() + x)

        #TODO screen wrapping opcional?
        self.set_y(max(min(self.y() + y, 128-25), self.height()))