from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

class Pieza(Sprite):
    def __init__(self, numpieza, rotation):
        super().__init__()
        self.numpieza = numpieza
        self.rotation = rotation
        self.set_strip(stripes["vortris.png"])

    def show(self):
        self.set_frame(self.numpieza * 4 + self.rotation)

    def rotate(self):
        self.rotation = (self.rotation + 1) % 4
        self.show()

class Vortris(Scene):
    stripes_rom = "vortris"

    def on_enter(self):
        super().on_enter()
        self.piezas = []

        for y in range(20):
            pieza = Pieza(randrange(7), randrange(4))
            pieza.set_frame(randrange(28))
            pieza.set_x(randrange(32) * 8)
            pieza.set_y(y * 8)
            pieza.show()
            self.piezas.append(pieza)


    def step(self):

        pieza = self.piezas[randrange(len(self.piezas))]
        pieza.rotate()
        
        for p in self.piezas:
            new_y = p.y() + 1
            if new_y > 160:
                new_y = 0
            p.set_y(new_y)

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Vortris()