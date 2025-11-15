from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

STARTING_LIVES = 3

class ScoreVidas():

    def __init__(self, score=0, vidas=STARTING_LIVES):
        self.score = score
        self.vidas = vidas

        self.crear_cartel()
        self.actualizar()

    def puntuar(self):
        self.score += 1
        self.actualizar()

    def perder(self):
        self.vidas -= 1
        self.actualizar()
        return (self.vidas <= 0)

    def actualizar(self):
        # Score    
        for n, l in enumerate("%05d" % self.score):
            v = ord(l) - 0x30
            self.chars[n].set_frame(v)

        # Vidas
        for n in range(STARTING_LIVES):
            self.chars[6+n].set_frame(10 + int(self.vidas > n))
    
    def crear_cartel(self):
        self.chars = []
        for n in range(9):
            s = Sprite()
            s.set_strip(stripes["numerals.png"])
            s.set_x(110 + n * 4)
            s.set_y(0)
            s.set_frame(10)
            s.set_perspective(2)
            self.chars.append(s)