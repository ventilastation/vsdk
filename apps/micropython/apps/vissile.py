from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

MIRA_VELOCIDAD_HORIZONTAL = 4
MIRA_VELOCIDAD_VERTICAL = 3
ANCHO_MIRA = 6

class Mira:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["mira.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(1)
        self.reiniciar()

    def reiniciar(self):
        self.sprite.set_x(128 - ANCHO_MIRA//2)
        self.sprite.set_y(60)

    def mover_izq(self):
        self.x_actual = max(self.sprite.x(), 85 - ANCHO_MIRA//2)  # Bound izquierdo
        self.sprite.set_x( self.x_actual - MIRA_VELOCIDAD_HORIZONTAL)

    def mover_der(self):
        self.x_actual = min(self.sprite.x(), 170 - ANCHO_MIRA//2)  # Bound derecho
        self.sprite.set_x( self.x_actual + MIRA_VELOCIDAD_HORIZONTAL)

    def subir(self):
        self.y_actual = max(self.sprite.y(), 30)   # Bound superior
        self.sprite.set_y( self.y_actual - MIRA_VELOCIDAD_VERTICAL)

    def bajar(self):
        self.y_actual = min(self.sprite.y(), 100)  # Bound inferior
        self.sprite.set_y( self.y_actual + MIRA_VELOCIDAD_VERTICAL)



class Misil:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["misil.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(1)
        self.sprite.set_x(randrange(90,160))
        self.sprite.set_y(30)

    def mover(self):
        self.y_actual = self.sprite.y()
        self.sprite.set_y(self.y_actual + 1)

class Vissile(Scene):
    stripes_rom = "vissile"

    def on_enter(self):
        super(Vissile, self).on_enter()

        self.mira = Mira()
        self.misiles = []

    def step(self):
        # if director.was_pressed(director.BUTTON_A):
        #     nub_x = self.nubareda.x
        #     nub_finx = self.nubareda.x + self.nubareda.width + 16
        #     if nub_x < self.bola.x() < nub_finx:
        #         director.sound_play(b"vyruss/shoot1")
        #         self.nubareda.reiniciar()
        #     else:
        #         director.sound_play(b"vyruss/explosion3")
        #         director.music_play("vyruss/vy-gameover")
        #         self.finished()
           
        if director.is_pressed(director.JOY_LEFT):
            self.mira.mover_izq()

        if director.is_pressed(director.JOY_RIGHT):
            self.mira.mover_der()

        if director.is_pressed(director.JOY_UP):
            self.mira.subir()

        if director.is_pressed(director.JOY_DOWN):
            self.mira.bajar()

        if director.was_pressed(director.BUTTON_A):
            self.misiles.append(Misil())

        for m in self.misiles:
            m.mover()

        #for i in range(len(misiles), -1, -1):
        #   if misiles[i] ... :
        #       del misiles[i]


        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Vissile()