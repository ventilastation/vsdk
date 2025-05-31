from apps.vasura_scripts.entities.entidad import *
from ventilastation.director import stripes

class Planeta(Entidad):
    alturas = [115, 130, 140]

    def __init__(self, scene):
        super().__init__(scene, stripes["game-center0.png"])

        self.vidas = 3
        self.index = 3 - self.vidas

        self.set_perspective(0)
        self.set_y(170)
        self.set_frame(self.index)


    def hit(self):
        self.vidas -= 1
        self.index = 3 - self.vidas

        if self.vidas == 0:
            self.scene.muerte()
            return 
        
        print(f"game-center{self.index}.png")
        self.set_strip(stripes[f"game-center{self.index}.png"])
        self.set_frame(0)


    def get_borde_y(self):
        return self.alturas[self.index]
