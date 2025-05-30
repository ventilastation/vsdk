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