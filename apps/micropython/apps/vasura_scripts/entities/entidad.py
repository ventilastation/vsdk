from math import floor
from ventilastation.sprites import Sprite
from apps.vasura_scripts.estado import *
from apps.vasura_scripts.common.evento import *

class Entidad(Sprite):
    estado : Estado = None

    velocidad_x : float = 0
    velocidad_y : float = 0

    def __init__(self, scene, strip : int, x : int = 0, y : int = 0):
        super().__init__()
        #Eventos/callbacks
        self.al_morir : Evento = Evento()

        self.scene = scene
        self.set_direccion(1)

        self.set_strip(strip)

        self.set_frame(0)

        self.x_interno = x
        self.y_interno = y

        self.set_x(x)
        self.set_y(y)

    
    def step(self):
        pass


    def get_position(self):
        return self.x_interno, self.y_interno


    def round_position(self):
        self.set_x(floor(self.x_interno))
        self.set_y(floor(self.y_interno))


    def set_position(self, x, y):
        self.x_interno = x
        self.y_interno = y
        self.round_position()


    def mover(self, x, y):
        self.x_interno += x 
        self.x_interno %= 256

        self.y_interno += y
        self.y_interno = max(min(self.y_interno, self.scene.planet.get_borde_y() - self.height()), self.height())
        self.round_position()


    def set_estado(self, estado):
        if isinstance(self.estado, estado):
            return
        
        if self.estado:
            self.estado.on_exit()

        self.estado = estado(entidad=self)
        self.estado.on_enter()


    def set_direccion(self, direccion: int):
        self.direccion = direccion

        # Sentido horario
        if direccion == 1:
            self.set_frame(0)
        elif direccion == -1:
            self.set_frame(1)

    def hit(self):
        pass

    def morir(self):
        pass

    def limpiar_eventos(self):
        self.al_morir.limpiar()
