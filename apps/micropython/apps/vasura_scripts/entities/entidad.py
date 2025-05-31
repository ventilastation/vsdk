from ventilastation.sprites import Sprite

class Entidad(Sprite):

    estado : Estado = None

    def __init__(self, scene, strip : int, x : int = 0, y : int = 0):
        super().__init__()
        self.scene = scene
        self.set_direccion(1)

        self.set_strip(strip)

        self.set_frame(0)

        self.set_x(x)
        self.set_y(y)
    
    def step(self):
        pass

    def mover(self, x, y):
        self.set_x(self.x() + x)

        #TODO screen wrapping opcional?
        self.set_y(max(min(self.y() + y, self.scene.planet.get_borde_y() - self.height()), self.height()))
        self.set_y(self.y() + y)
        print(self.__class__.__name__, self.y() + self.height())

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
