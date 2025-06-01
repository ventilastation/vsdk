from time import time

from apps.vasura_scripts.entities.nave import Nave
from apps.vasura_scripts.entities.enemigo import *

VIDAS_INICIALES : int = 3

TIEMPO_DE_RESPAWN : float = 5


class GameplayManager():
    #Dependencias
    nave : Nave = None
    
    #Estado
    tiempo_de_muerte : float = -1
    vidas_restantes : int = VIDAS_INICIALES
    puntaje_actual : int = 0

    #Eventos
    al_perder_vida : List[callable] = list()
    al_perder : List[callable] = list()

    def __init__(self, nave:Nave):
        self.nave = nave
        nave.al_morir = self.al_morir_nave
    
    def step(self):
        #BUG creo que tarda mas tiempo del configurado pero nidea
        if self.tiempo_de_muerte != -1 and time() >= self.tiempo_de_muerte + TIEMPO_DE_RESPAWN:
            self.respawnear_nave()

    def al_morir_nave(self, _):
        self.tiempo_de_muerte = time()
    
    def on_planet_hit(self):
        self.vidas_restantes -= 1

        if self.vidas_restantes == 0:
            for i in range(len(self.al_perder)):
                self.al_perder[i]()
        else:
            for i in range(len(self.al_perder_vida)):
                self.al_perder_vida[i](self.vidas_restantes)

    def al_morir_enemigo(self, e:Enemigo):
        self.puntaje_actual += e.puntaje

        print("Puntaje actualizado: " + str(self.puntaje_actual))

    def suscribir_perder_vida(self, callback:callable):
        self.al_perder_vida.append(callback)

    def suscribir_game_over(self, callback:callable):
        self.al_perder.append(callback)

    def respawnear_nave(self):
        self.tiempo_de_muerte = -1
        self.nave.respawn()