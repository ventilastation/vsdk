from apps.vasura_scripts.entities.entidad import *
from apps.vasura_scripts.managers.gameplay_manager import *
from ventilastation.director import stripes

class Planeta(Entidad):
    alturas = [115, 130, 140]

    al_ser_golpeado : callable = None
    index : int = 0

    def __init__(self, scene):
        super().__init__(scene, stripes["game-center0.png"])
        self.set_perspective(0)
        self.set_y(170)
        self.set_frame(self.index)


    def hit(self):
        if self.al_ser_golpeado:
            self.al_ser_golpeado()
        

    def al_perder_vida(self, vidas_restantes:int):
        self.index = VIDAS_INICIALES - vidas_restantes

        self.set_strip(stripes[f"game-center{self.index}.png"])
        self.set_frame(0)

    def get_borde_y(self):
        return self.alturas[self.index]
