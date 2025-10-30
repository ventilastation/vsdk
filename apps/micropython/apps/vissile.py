from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

MIRA_VELOCIDAD_HORIZONTAL = 4
MIRA_STEP_VERTICAL = 3
ANCHO_MIRA = 9
EXPLOSION_FRAMES = 5

class Mira:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["mira.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(1)
        self.reiniciar()

    def reiniciar(self):
        self.sprite.set_x(127 - ANCHO_MIRA//2)
        self.sprite.set_y(65)

    # No llega hasta el plano horizontal porque no van a venir misiles por el piso XD
    def mover_izq(self):
        self.x_actual = max(self.sprite.x(), 80 - ANCHO_MIRA//2)  # Bound izquierdo
        self.sprite.set_x( self.x_actual - MIRA_VELOCIDAD_HORIZONTAL)

    def mover_der(self):
        self.x_actual = min(self.sprite.x(), 175 - ANCHO_MIRA//2)  # Bound derecho
        self.sprite.set_x( self.x_actual + MIRA_VELOCIDAD_HORIZONTAL)

    # Sube y baja escalonadamente
    def subir(self):
        self.sprite.set_y( max(self.sprite.y() - 25, 40) )

    def bajar(self):
        self.sprite.set_y( min(self.sprite.y() + 25, 90))

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
    def __init__(self, torreta, derecha, target_x):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["cascote.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(1)
        self.derecha = derecha
        self.target_x = target_x
        self.delete = False

        # Torretas isquierdas, de izquierda a derecha
        if torreta == 1:
            self.sprite.set_x(64 - 2)
            self.sprite.set_y(40)
        elif torreta == 2:
            self.sprite.set_x(64 - 2)
            self.sprite.set_y(65)
        elif torreta == 3:
            self.sprite.set_x(64 - 2)
            self.sprite.set_y(90)
        # Torretas derechas, de izquierda a derecha
        elif torreta == 4:
            self.sprite.set_x(192 - 2)
            self.sprite.set_y(90)
            self.sprite.set_frame(1)
        elif torreta == 5:
            self.sprite.set_x(192 - 2)
            self.sprite.set_y(65)
            self.sprite.set_frame(1)
        elif torreta == 6:
            self.sprite.set_x(192 - 2)
            self.sprite.set_y(40)
            self.sprite.set_frame(1)
    
    def mover(self):
        if self.derecha:
            self.x_actual = self.sprite.x()
            if self.x_actual < self.target_x:
                self.sprite.set_x(self.x_actual + 1)
            else:
                self.delete = True
        else:
            self.x_actual = self.sprite.x()
            if self.x_actual > self.target_x:
                self.sprite.set_x(self.x_actual - 1)
            else:
                self.delete = True

class Explosion:
    def __init__(self, x, y):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["explosion.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(1)
        self.sprite.set_x(x)
        self.sprite.set_y(y)
        self.delete = False
        self.animation_delay = 15  # Contador que se usa para ralentizar la animación

    def animar(self):
        current_frame = self.sprite.frame()
        if current_frame < EXPLOSION_FRAMES - 2:
            if self.animation_delay % 6 == 0:
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
        self.cascotes = []

    def step(self):

        # Movimiento de la mira
        if director.is_pressed(director.JOY_LEFT):
            self.mira.mover_izq()

        if director.is_pressed(director.JOY_RIGHT):
            self.mira.mover_der()

        if director.was_pressed(director.JOY_UP):
            self.mira.subir()

        if director.was_pressed(director.JOY_DOWN):
            self.mira.bajar()

        # Disparar cascote
        if director.was_pressed(director.BUTTON_A):

            # Temporalmente también usar el clic para crear misiles
            self.misiles.append(Misil())

            target_x = self.mira.sprite.x()
            if self.mira.sprite.x() < 128 - ANCHO_MIRA // 2:
                if self.mira.sprite.y() == 40:
                    self.cascotes.append(Cascote(1, True, target_x - ANCHO_MIRA//2))
                elif self.mira.sprite.y() == 65:
                    self.cascotes.append(Cascote(2, True, target_x - ANCHO_MIRA//2))
                elif self.mira.sprite.y() == 90:
                    self.cascotes.append(Cascote(3, True, target_x - ANCHO_MIRA//2))
            else:
                if self.mira.sprite.y() == 40:
                    self.cascotes.append(Cascote(6, False, target_x - ANCHO_MIRA//2))
                elif self.mira.sprite.y() == 65:
                    self.cascotes.append(Cascote(5, False, target_x - ANCHO_MIRA//2))
                elif self.mira.sprite.y() == 90:
                    self.cascotes.append(Cascote(4, False, target_x - ANCHO_MIRA//2))
            

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
        
        for c in self.cascotes:
            c.mover()
            if (c.delete):
                c.sprite.disable()
                e = Explosion(c.sprite.x() - 10, c.sprite.y() - 10)
                # TODO: Sólo permitir una cantidad determinada de explosiones al mismo tiempo para evitar flooding
                self.cascotes.remove(c)
                self.explosiones.append(e)

        # Salir
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Vissile()