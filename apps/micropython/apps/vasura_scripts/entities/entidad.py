from ventilastation.sprites import Sprite

class Entidad(Sprite):

    def __init__(self, strip):
        super().__init__()

        self.set_strip(strip)

        self.set_frame(0)