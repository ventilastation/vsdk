from apps.vasura_scripts.entities.entidad import *
from ventilastation.director import stripes

class Planeta(Entidad):

    def __init__(self):
        super().__init__(stripes["game-center.png"])

        self.set_perspective(0)
        self.set_y(160)
