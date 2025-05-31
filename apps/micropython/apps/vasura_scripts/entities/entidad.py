from ventilastation.sprites import Sprite

class Entidad(Sprite):

    estado : Estado = None

    def __init__(self, scene, strip : int, x : int = 0, y : int = 0):
        super().__init__()
        self.scene = scene

        self.set_strip(strip)

        self.set_frame(0)

        self.set_x(x)
        self.set_y(y)
    
    def step(self):
        pass

    def mover(self, x, y):
        self.set_x(self.x() + x)

        #TODO screen wrapping opcional?
        #TODO el 25 ese es el radio de colisión del planeta. Moverlo a algún lado menos mocho.
        self.set_y(max(min(self.y() + y, self.scene.planet.get_borde_y() - self.height()), self.height()))
        self.set_y(self.y() + y)
        print(self.__class__.__name__, self.y() + self.height())

    def set_estado(self, estado):
        #TODO no transicionar al mismo estado en el que estas
        
        if self.estado:
            self.estado.on_exit()

        self.estado = estado(entidad=self)
        self.estado.on_enter()
