from apps.vasura_scripts.entities.enemigos.enemigo import *
from apps.vasura_scripts.managers.enemigos_manager import *

from utime import ticks_ms, ticks_diff, ticks_add
from urandom import randint, seed
from math import floor

INTERVALO_DE_SPAWN : float = 4

class SpawnerEnemigos():
    def __init__(self, manager:EnemigosManager):
        self.manager : EnemigosManager = manager
        self.tiempo_siguiente_spawn : int = -1
        
        seed(ticks_ms())

    def step(self):
        if self.tiempo_siguiente_spawn == -1:
            return
        
        if ticks_diff(self.tiempo_siguiente_spawn, ticks_ms()) <= 0:
            self.spawnear_enemigo()

    #TODO soporte para distintos tipos de enemigos
    def spawnear_enemigo(self):
        e = self.manager.get_enemigo()

        if not e:
            return

        e.reset()

        e.set_position(randint(0, 254), 0)

        self.tiempo_siguiente_spawn = ticks_add(ticks_ms(), floor(INTERVALO_DE_SPAWN * 1000))