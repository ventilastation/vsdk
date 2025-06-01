from apps.vasura_scripts.entities.enemigos.enemigo import *
from apps.vasura_scripts.managers.enemigos_manager import *

import random
from time import time_ns
from time import time

INTERVALO_DE_SPAWN : float = 4.0

class SpawnerEnemigos():
    manager : EnemigosManager = None
    
    tiempo_siguiente_spawn : float = -1

    def __init__(self, manager:EnemigosManager):
        self.manager = manager
        random.seed(time_ns())

    def step(self):
        if self.tiempo_siguiente_spawn == -1:
            return
        
        if time() > self.tiempo_siguiente_spawn:
            self.spawnear_enemigo()

    #TODO soporte para distintos tipos de enemigos
    def spawnear_enemigo(self):
        e = self.manager.get_enemigo()

        e.reset()

        e.set_position(random.randint(0, 254), 0)

        self.tiempo_siguiente_spawn = time() + INTERVALO_DE_SPAWN