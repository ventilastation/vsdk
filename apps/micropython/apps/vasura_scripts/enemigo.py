from apps.vasura_scripts.estado import *
from apps.vasura_scripts.nave import Nave

from ventilastation.sprites import Sprite
from ventilastation.director import director, stripes

class Enemigo():
    estado_inicial = None

    # PENSAR: hay que pasar la posición acá?
    def __init__(self, scene, x, y):
        self.scene = scene

        strip = self.estado_inicial.strip
        self.sprite = Sprite()
        self.sprite.set_strip(stripes[strip])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(1)
        self.sprite.set_x(x)
        self.sprite.set_y(y)

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
