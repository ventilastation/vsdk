from apps.vasura_scripts.entities.entidad import *
from apps.vasura_scripts.managers.gameplay_manager import *
from ventilastation.director import stripes

class Planeta(Entidad):
    def __init__(self, scene):
        super().__init__(scene, stripes["game-center0.png"])
        self.animando = False
        
        self.alturas = [115, 130, 140]
        self.index : int = 0

        self.al_ser_golpeado : Evento = Evento()

        self.set_perspective(0)
        self.set_y(170)
        self.set_frame(self.index)


    def hit(self):
        return
        self.al_ser_golpeado.disparar()

    def animar(self):
        if not self.animando:
            self.disable()
            return
        
        self.frames -= 1
        if self.frames == 0 and self.animando:
            self.fase_animacion += 1
            self.set_strip(stripes[f"explosion-grande{self.fase_animacion}.png"])
            self.frames = self.steps_por_frame

        if self.fase_animacion == self.largo_animacion - 1:
            self.animando = False

    def morir(self):
        self.largo_animacion = 8
        self.steps_por_frame = 5
        self.frames = self.steps_por_frame
        self.animando = True
        
    def limpiar_eventos(self):
        self.al_ser_golpeado.limpiar()
        
        super().limpiar_eventos()

    def al_perder_vida(self, vidas_restantes:int):
        if vidas_restantes < 0:
            return

        self.index = VIDAS_INICIALES - vidas_restantes

        self.set_strip(stripes[f"game-center{self.index}.png"])
        self.set_frame(0)

    def get_borde_y(self):
        return self.alturas[self.index]
