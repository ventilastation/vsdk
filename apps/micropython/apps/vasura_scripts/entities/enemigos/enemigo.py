from apps.vasura_scripts.entities.entidad import *

from apps.vasura_scripts.estado import *

from ventilastation.director import stripes

class Enemigo(Entidad):
    
    puntaje : int = 0
    
    estado_inicial : Estado = None
    strip : str

    def __init__(self, scene):
        super().__init__(scene, stripes[self.strip])
        
        self.set_perspective(1)

        self.set_estado(Deshabilitado)


    def reset(self):
        self.set_estado(self.estado_inicial)


    def step(self):
        nuevo_estado = self.estado.step()
        if nuevo_estado:
            self.set_estado(nuevo_estado)

    def morir(self):
        self.set_estado(Deshabilitado)

        self.al_morir.disparar(self)


class Driller(Enemigo):
    estado_inicial = Bajando

    def __init__(self, scene):
        self.velocidad_y = 0.5

        self.strip = "ship-sprite-sym.png"
        self.puntaje = 50

        super().__init__(scene)
