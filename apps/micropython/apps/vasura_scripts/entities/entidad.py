from math import floor
from ventilastation.sprites import Sprite
from apps.vasura_scripts.estado import *
from apps.vasura_scripts.common.evento import *

class Entidad(Sprite):
    estado : Estado = None

    velocidad_x : float = 0
    velocidad_y : float = 0

    min_y : int = 0
    largo_animacion = 1
    steps_por_frame = 4

    def __init__(self, scene, strip : int, x : int = 0, y : int = 0):
        super().__init__()
        #Eventos/callbacks
        self.al_morir : Evento = Evento()

        self.scene = scene
        self.set_strip(strip)

        self.fase_animacion = 0
        self.frames = self.steps_por_frame
        # self.set_direccion(1)


        self.x_interno = x
        self.y_interno = y

        self.set_x(x)
        self.set_y(y)

    
    def step(self):
        pass


    def animar(self):
        if self.largo_animacion == 1:
            return
        
        self.frames -= 1
        if self.frames == 0:
            self.fase_animacion = (self.fase_animacion + 1) % self.largo_animacion
            self.set_direccion(self.direccion)
            self.frames = self.steps_por_frame


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
        self.y_interno = max(min(self.y_interno, self.scene.planet.get_borde_y() - self.height()), self.min_y)
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
            self.set_frame(self.fase_animacion)
        elif direccion == -1:
            self.set_frame(self.fase_animacion + self.largo_animacion)

    def hit(self):
        pass

    def morir(self):
        pass

    def limpiar_eventos(self):
        self.al_morir.limpiar()
