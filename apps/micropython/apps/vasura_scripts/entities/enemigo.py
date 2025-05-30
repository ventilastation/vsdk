from apps.vasura_scripts.entities.entidad import *

from apps.vasura_scripts.estado import *

from ventilastation.sprites import Sprite
from ventilastation.director import stripes

class Enemigo(Entidad):
    
    estado_inicial : Estado = None
    strip : str


    # PENSAR: hay que pasar la posición acá?
    def __init__(self, scene, x, y):
        super().__init__(stripes[self.strip], x, y)
        
        self.scene = scene
        
        
        self.set_perspective(1)
        self.set_x(x)
        self.set_y(y)

        self.estado = None
        self.reset()

    
    def set_estado(self, estado):
        if self.estado:
            self.estado.on_exit()

        print("Set Estado", estado.__name__)
        self.estado = estado(entidad=self)
        self.estado.on_enter()


    def reset(self):
        self.set_estado(self.estado_inicial)
        
        # TODO: Spawn


    def step(self):
        nuevo_estado = self.estado.step()
        if nuevo_estado:
            self.set_estado(nuevo_estado)



class Driller(Enemigo):
    estado_inicial = Bajando

    def __init__(self, scene, x, y):
        self.strip = "ship-sprite-sym.png"

        super().__init__(scene, x, y)
