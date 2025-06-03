from apps.vasura_scripts.entities.enemigos.enemigo import *
from apps.vasura_scripts.managers.enemigos_manager import TIPOS_DE_ENEMIGO, EnemigosManager

from utime import ticks_ms, ticks_diff, ticks_add
from urandom import randint, seed, choice
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


    def spawnear_enemigo(self):
        tipo = choice(TIPOS_DE_ENEMIGO)
        
        if tipo == Chiller:
            enemigos = []
            for _ in range(3):
                e = self.manager.get_enemigo(Chiller)
                if not e:
                    return
                
                enemigos.append(e)
        else:
            e = self.manager.get_enemigo(tipo)
            if not e:
                return

            enemigos = [e]

        pos = randint(0, 255)
        for e in enemigos:
            e.reset()
            e.set_position(pos, 0)
            pos = (pos + 256 // 3) % 256

        self.tiempo_siguiente_spawn = ticks_add(ticks_ms(), floor(INTERVALO_DE_SPAWN * 1000))
