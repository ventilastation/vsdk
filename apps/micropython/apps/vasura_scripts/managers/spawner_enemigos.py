from apps.vasura_scripts.entities.enemigos.enemigo import *
from apps.vasura_scripts.managers.enemigos_manager import *

import random
from time import time_ns

class SpawnerEnemigos():
    manager : EnemigosManager = None

    def __init__(self, manager:EnemigosManager):
        self.manager = manager
        random.seed(time_ns())

    #TODO soporte para distintos tipos de enemigos
    def spawnear_enemigo(self):
        e = self.manager.get_enemigo()

        e.reset()

        e.set_position(random.randint(0, 254), 0)