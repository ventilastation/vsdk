from apps.vasura_scripts.entities.enemigos.enemigo import *
from apps.vasura_scripts.managers.enemigos_manager import TIPOS_DE_ENEMIGO, EnemigosManager

from utime import ticks_ms, ticks_diff, ticks_add
from urandom import randint, seed, choice
from math import floor

class SpawnerEnemigos():
    def __init__(self, manager:EnemigosManager):
        self.manager : EnemigosManager = manager
        self.comportamiento : ComportamientoSpawn = RandomSpawnIntervaloFijo(4)
                
        seed(ticks_ms())


    def step(self):
        if self.comportamiento.deberia_spawnear():
            self.spawnear_enemigo()


    def spawnear_enemigo(self):
        tipo = self.comportamiento.get_siguiente_enemigo()
        
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

        


class ComportamientoSpawn:
    def __init__(self):
        self.prendido = True
    
    def step(self):
        pass

    def deberia_spawnear(self):
        return False
    
    def get_siguiente_enemigo(self):
        return None
    

class RandomSpawnIntervaloFijo(ComportamientoSpawn):
    def __init__(self, tiempo:float):
        super().__init__()

        self.intervalo_spawn : float = tiempo
        self.tiempo_siguiente_spawn : int = -1

    def get_siguiente_enemigo(self):
        self.tiempo_siguiente_spawn = ticks_add(ticks_ms(), floor(self.intervalo_spawn * 1000))

        return choice(TIPOS_DE_ENEMIGO)

    def deberia_spawnear(self):
        return self.prendido and ticks_diff(self.tiempo_siguiente_spawn, ticks_ms()) <= 0

