from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

MIRA_VELOCIDAD_HORIZONTAL = 4
MIRA_VELOCIDAD_VERTICAL = 3
ANCHO_MIRA = 6
EXPLOSION_FRAMES = 5

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
        self.x_actual = max(self.sprite.x(), 80 - ANCHO_MIRA//2)  # Bound izquierdo
        self.sprite.set_x( self.x_actual - MIRA_VELOCIDAD_HORIZONTAL)

    def mover_der(self):
        self.x_actual = min(self.sprite.x(), 175 - ANCHO_MIRA//2)  # Bound derecho
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

class Cascote:
    def __init__(self, torreta):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["cascote.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(1)
        if torreta == 1:
            self.sprite.set_x(64)
            self.sprite.set_y(85)
        elif torreta == 2:
            self.sprite.set_x(64)
            self.sprite.set_y(170)
        elif torreta == 3:
            self.sprite.set_x(192)
            self.sprite.set_y(170)
        elif torreta == 4:
            self.sprite.set_x(192)
            self.sprite.set_y(85)

class Explosion:
    def __init__(self, x, y):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["explosion.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(1)
        self.sprite.set_x(x)
        self.sprite.set_y(y)
        self.delete = False
        self.animation_delay = 15  # Used to animate the sprite slower

    def animar(self):
        current_frame = self.sprite.frame()
        if current_frame < EXPLOSION_FRAMES - 2:
            if self.animation_delay % 5 == 0:
                self.sprite.set_frame(current_frame+1)
            self.animation_delay = self.animation_delay + 1
        else:
            self.delete = True

class Vissile(Scene):
    stripes_rom = "vissile"

    def on_enter(self):
        super(Vissile, self).on_enter()

        self.mira = Mira()
        self.misiles = []
        self.explosiones = []

    def step(self):

        # Movimiento de la mira
        if director.is_pressed(director.JOY_LEFT):
            self.mira.mover_izq()

        if director.is_pressed(director.JOY_RIGHT):
            self.mira.mover_der()

        if director.is_pressed(director.JOY_UP):
            self.mira.subir()

        if director.is_pressed(director.JOY_DOWN):
            self.mira.bajar()

        # Disparar misil
        if director.was_pressed(director.BUTTON_A):
            Cascote(1)
            e = Explosion(self.mira.sprite.x() - 10, self.mira.sprite.y() - 10)
            # TODO: Sólo permitir una cantidad determinada de explosiones al mismo tiempo para evitar flooding
            self.explosiones.append(e)

        # Actualizar misiles
        for m in self.misiles:
            m.mover()
            if m.sprite.y() > 120:
                m.sprite.disable()
                self.misiles.remove(m)  # funciona?
                # TODO Take damage!
        
        # Actualizar explosiones
        for e in self.explosiones:
            e.animar()
            if (e.delete):
                e.sprite.disable()
                self.explosiones.remove(e)  # funciona?
        
        # Salir
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Vissile()