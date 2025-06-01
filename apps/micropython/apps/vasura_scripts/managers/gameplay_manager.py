from utime import ticks_ms, ticks_diff, ticks_add

from apps.vasura_scripts.entities.nave import Nave
from apps.vasura_scripts.entities.enemigos.enemigo import *

VIDAS_INICIALES : int = 3

TIEMPO_DE_RESPAWN : float = 3


class GameplayManager():    
    def __init__(self, nave:Nave):
        #Dependencias
        self.nave : Nave = nave

        #Estado
        self.tiempo_respawn : float = -1
        self.vidas_restantes : int = VIDAS_INICIALES
        self.puntaje_actual : int = 0

        #Eventos
        self.al_perder_vida : Evento = Evento()
        self.game_over : Evento = Evento()

        nave.al_morir.suscribir(self.programar_respawn_nave)
    
    def step(self):
        if self.tiempo_respawn != -1 and ticks_diff(self.tiempo_respawn, ticks_ms()) <= 0:
            self.respawnear_nave()

    def programar_respawn_nave(self, _):
        self.tiempo_respawn = ticks_add(ticks_ms(), TIEMPO_DE_RESPAWN * 1000)
    
    def on_planet_hit(self):
        self.vidas_restantes -= 1

        if self.vidas_restantes == 0:
            self.game_over.disparar()
        else:
            self.al_perder_vida.disparar(self.vidas_restantes)

    def al_morir_enemigo(self, e:Enemigo):
        self.puntaje_actual += e.puntaje

        print("Puntaje actualizado: " + str(self.puntaje_actual))

    def respawnear_nave(self):
        self.tiempo_respawn = -1
        self.nave.respawn()
    
    def limpiar(self):
        self.al_perder_vida.limpiar()
        self.game_over.limpiar()