from apps.vasura_scripts.entities.entidad import *
from apps.vasura_scripts.managers.gameplay_manager import *
from ventilastation.director import stripes

class Planeta(Entidad):
    def __init__(self, scene):
        super().__init__(scene, stripes["game-center0.png"])
        
        self.alturas = [115, 130, 140]
        self.index : int = 0

        self.al_ser_golpeado : Evento = Evento()

        self.set_perspective(0)
        self.set_y(170)
        self.set_frame(self.index)


    def hit(self):
        self.al_ser_golpeado.disparar()
        
    def limpiar_eventos(self):
        self.al_ser_golpeado.limpiar()
        
        super().limpiar_eventos()

    def al_perder_vida(self, vidas_restantes:int):
        self.index = VIDAS_INICIALES - vidas_restantes

        self.set_strip(stripes[f"game-center{self.index}.png"])
        self.set_frame(0)

    def get_borde_y(self):
        return self.alturas[self.index]
