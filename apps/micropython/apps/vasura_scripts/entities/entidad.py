from math import floor
from ventilastation.sprites import Sprite

class Entidad(Sprite):

    estado : Estado = None

    def __init__(self, scene, strip : int, x : int = 0, y : int = 0):
        super().__init__()
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


    def syncPos(self):
        self.set_x(floor(self.x_interno))
        self.set_y(floor(self.y_interno))


    def setPos(self, x, y):
        self.x_interno = x
        self.y_interno = y
        self.syncPos()


    def mover(self, x, y):
        self.x_interno += x 
        self.x_interno %= 256

        self.y_interno += y
        self.y_interno = max(min(self.y_interno, self.scene.planet.get_borde_y() - self.height()), self.height())
        self.syncPos()


    def set_estado(self, estado):
        #TODO no transicionar al mismo estado en el que estas
        
        if self.estado:
            self.estado.on_exit()

        self.estado = estado(entidad=self)
        self.estado.on_enter()


    def set_direccion(self, direccion: int):
        print("direccion", direccion)
        self.direccion = direccion

        # Sentido horario
        if direccion == 1:
            self.set_frame(0)
        elif direccion == -1:
            self.set_frame(1)
