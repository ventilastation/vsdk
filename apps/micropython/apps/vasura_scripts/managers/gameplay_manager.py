from utime import ticks_ms, ticks_diff, ticks_add

from apps.vasura_scripts.entities.nave import Nave
from apps.vasura_scripts.entities.enemigos.enemigo import *

VIDAS_INICIALES : int = 3

TIEMPO_DE_RESPAWN : float = 3


class GameplayManager():
    #Dependencias
    nave : Nave = None
    
    #Estado
    tiempo_respawn : float = -1
    vidas_restantes : int = VIDAS_INICIALES
    puntaje_actual : int = 0

    def __init__(self, nave:Nave):
        #Eventos
        self.al_perder_vida : List[callable] = []
        self.al_perder : List[callable] = []

        self.nave = nave
        nave.suscribir_muerte(self.al_morir_nave)
    
    def step(self):
        if self.tiempo_respawn != -1 and ticks_diff(self.tiempo_respawn, ticks_ms()) <= 0:
            self.respawnear_nave()

    def al_morir_nave(self, _):
        self.tiempo_respawn = ticks_add(ticks_ms(), TIEMPO_DE_RESPAWN * 1000)
    
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
        self.tiempo_respawn = -1
        self.nave.respawn()