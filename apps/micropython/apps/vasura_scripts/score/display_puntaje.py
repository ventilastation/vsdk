from ventilastation.sprites import Sprite
from ventilastation.director import stripes

class DisplayPuntaje:
    def __init__(self):
        self.chars = []
        for n in range(9):
            s = Sprite()
            s.set_strip(stripes["numerals.png"])
            s.set_x(118 + n * 4)
            s.set_y(5)
            s.set_frame(10)
            s.set_perspective(2)
            self.chars.append(s)

        self.medal : Sprite = Sprite()
        self.medal.set_strip(stripes["numerals.png"])
        self.medal.set_y(5)
        self.medal.set_x(114)
        self.medal.set_perspective(2)
        self.medal.disable()

        self.actualizar(0)

    def actualizar(self, value:int):
        #HACK. Ver GameplayManager.restar_puntos().
        if value == -1:
            value = 0
        
        for n, l in enumerate("%05d" % value):
            v = ord(l) - 0x30
            self.chars[n].set_frame(v)

    def mostrar_medalla(self):
        self.medal.set_frame(11)