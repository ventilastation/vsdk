from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

#
#  TODO (como terminar el juego)
# ===============================
# - Dificultades x numero de barras 1 al 9, sube cada 13 segundos
#   - [Bonus] Luego sube la velocidad (espaciado efecto warp?)
# - Score por tiempo
# - Modo fixed_seed testeadas & random_seed
# - Musica con mix gradual por nivel
# - Sonido por colisión y pasar de nivel cada 9 segundos
#

NUM_BARRAS = 9

class MySprite(Sprite):
    pass

def gen_sprite(name, x=0):
    s = MySprite()
    s.set_strip(stripes[name])
    s.set_frame(0)
    s.og_x = x
    s.set_x(x)
    s.set_y(10)
    s.acc_x = randrange (0,9)-5
    return s

class AAA(Scene):
    stripes_rom = "aaa"

    def on_enter(self):
        super(AAA, self).on_enter()
        self.barras = []
        for a in range(0,NUM_BARRAS):
            self.barras.append(gen_sprite("barra.png", x=randrange(1,200)))
        self.y_step = 10
        self.x_center = 0
        self.punto = gen_sprite("punto.png")
        self.punto.set_x(250)
        self.punto.set_y(10)

    def step(self):

        if director.is_pressed(director.JOY_LEFT):
            self.x_center -= 4
        if director.is_pressed(director.JOY_RIGHT):
            self.x_center += 4

        self.y_step -= 4

        if self.y_step < 0:
            self.y_step = 250

        for a in range(0, NUM_BARRAS):
            ty = (self.y_step + a * 24)
            ty = ty % 255
            if ty > 240:
                self.barras[a].og_x = randrange(0,240)
            self.barras[a].set_y(ty)
            self.barras[a].set_x(self.barras[a].og_x + self.x_center)

        if self.punto.collision(self.barras):
            self.finished()

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return AAA()
