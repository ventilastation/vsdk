from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

class Ventilatris(Scene):
    stripes_rom = "ventilatris"

    def on_enter(self):
        super().on_enter()
        self.piezas = []

        for i in range(0, 20, 2):
            for j in range(0, 20, 2):
                pieza = Sprite()
                pieza.set_x(i * 8)
                pieza.set_y(16 + j * 8)
                pieza.set_strip(stripes["ventilatris.png"])
                pieza.set_frame(randrange(28))
                self.piezas.append(pieza)

    def step(self):      
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Ventilatris()