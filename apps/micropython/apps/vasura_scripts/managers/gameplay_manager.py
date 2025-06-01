from time import time

from apps.vasura_scripts.entities.nave import Nave

TIEMPO_DE_RESPAWN = 5

class GameplayManager():
    nave : Nave = None
    tiempo_de_muerte : float = -1

    def __init__(self, nave:Nave):
        self.nave = nave
        nave.al_morir = self.al_morir_nave
    
    def step(self):
        #BUG creo que tarda mas tiempo del configurado pero nidea
        if self.tiempo_de_muerte != -1 and time() >= self.tiempo_de_muerte + TIEMPO_DE_RESPAWN:
            self.respawnear_nave()

    def al_morir_nave(self, _):
        self.tiempo_de_muerte = time()

    def respawnear_nave(self):
        self.tiempo_de_muerte = -1
        self.nave.respawn()