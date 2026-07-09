from ventilastation.director import stripes
from ventilastation.sprites import Sprite

MIRA_VELOCIDAD_HORIZONTAL = 2
ANCHO_MIRA = 8

# Mira que controla el jugador
class Mira:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["mira.png"])
        self.sprite.set_perspective(2)
        self.reiniciar()
        self.desactivar()

    def desactivar(self):
        self.sprite.disable()

    def reiniciar(self):
        self.sprite.set_x(127 - ANCHO_MIRA//2)
        self.sprite.set_y(23)
        self.sprite.set_frame(0)

    # No llega hasta el plano horizontal porque no van a venir misiles por el piso XD
    def mover_izq(self):
        self.x_actual = max(self.sprite.x(), 80 - ANCHO_MIRA//2)  # Bound izquierdo
        self.sprite.set_x( self.x_actual - MIRA_VELOCIDAD_HORIZONTAL)

    def mover_der(self):
        self.x_actual = min(self.sprite.x(), 175 - ANCHO_MIRA//2)  # Bound derecho
        self.sprite.set_x( self.x_actual + MIRA_VELOCIDAD_HORIZONTAL)

    # Sube y baja escalonadamente
    def subir(self):
        self.sprite.set_y( max(self.sprite.y() - 10, 13) )

    def bajar(self):
        self.sprite.set_y( min(self.sprite.y() + 10, 33))