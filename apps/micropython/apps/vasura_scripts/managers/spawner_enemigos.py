from apps.vasura_scripts.entities.enemigos.enemigo import *
from apps.vasura_scripts.managers.enemigos_manager import TIPOS_DE_ENEMIGO, EnemigosManager

from utime import ticks_ms, ticks_diff, ticks_add
from urandom import randint, seed, choice
from math import floor

class SpawnerEnemigos():
    def __init__(self, manager:EnemigosManager):
        self.manager : EnemigosManager = manager

        tabla_spawn = [
            (0, 60),
            (1, 10),
            (2, 30)
        ]

        self.comportamiento : ComportamientoSpawn = SpawnRandomIncremental(2.5, 0.5, 6, 0.75, 0.05, 0.1, tabla_spawn)
                
        seed(ticks_ms())


    def step(self):
        if self.comportamiento.deberia_spawnear():
            self.spawnear_enemigo()


    def spawnear_enemigo(self):
        tipo = self.comportamiento.get_siguiente_enemigo()
        
        if not tipo:
            return

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
    

class SpawnRandomIntervaloFijo(ComportamientoSpawn):
    def __init__(self, tiempo:float):
        super().__init__()

        self.intervalo_spawn : float = tiempo
        self.tiempo_siguiente_spawn : int = -1

    def get_siguiente_enemigo(self):
        self.tiempo_siguiente_spawn = ticks_add(ticks_ms(), floor(self.intervalo_spawn * 1000))

        return choice(TIPOS_DE_ENEMIGO)

    def deberia_spawnear(self):
        return self.prendido and ticks_diff(self.tiempo_siguiente_spawn, ticks_ms()) <= 0


class SpawnRandomIncremental(ComportamientoSpawn):
    #Formato tabla de porcentajes: (ID en TIPOS_DE_ENEMIGOS, porcentaje)

    def __init__(self, piso_inicial:float, piso_minimo:float, techo_inicial:float, techo_minimo:float, step_piso:float, step_techo:float, tabla_porcentajes):
        super().__init__()

        self.validar_tabla(tabla_porcentajes)
        
        self.tabla_porcentajes = sorted(tabla_porcentajes, key=lambda tup: tup[1])
        
        self.piso_tiempo : int = floor(piso_inicial * 1000)
        self.techo_tiempo : int = floor(techo_inicial * 1000)

        self.piso_minimo : int = floor(piso_minimo * 1000)
        self.techo_minimo : int = floor(techo_minimo * 1000)

        self.step_piso : int = floor(step_piso * 1000)
        self.step_techo : int = floor(step_techo * 1000)

        self.tiempo_siguiente_spawn : int = -1
    
    def get_siguiente_enemigo(self):
        self.piso_tiempo -= self.step_piso

        if self.piso_tiempo < self.piso_minimo:
            self.piso_tiempo = self.piso_minimo

        
        self.techo_tiempo -= self.step_piso

        if self.techo_tiempo < self.techo_minimo:
            self.techo_tiempo = self.techo_minimo

        
        intervalo = randint(self.piso_tiempo, self.techo_tiempo)

        self.tiempo_siguiente_spawn = ticks_add(ticks_ms(), intervalo)
        
        roll = randint(0, 100)

        porcentaje_acumulado = 0

        for entrada in self.tabla_porcentajes:
            porcentaje_acumulado += entrada[1]

            if roll < porcentaje_acumulado:
                return TIPOS_DE_ENEMIGO[entrada[0]]

        return None

    def deberia_spawnear(self):
        return self.prendido and ticks_diff(self.tiempo_siguiente_spawn, ticks_ms()) <= 0

    def validar_tabla(self, tabla):
        suma = 0

        for entrada in tabla:
            suma += entrada[1]

            if suma > 100:
                raise Exception("Los porcentajes de la tabla suman más de 100")

        for e1 in tabla:
            encontrado = False
            for e2 in tabla:
                if e1[0] == e2[0]:
                    if encontrado:
                        raise Exception("La tabla tiene un tipo de enemigo repetido")
                    else:
                        encontrado = True


class SpawnPorWaves(ComportamientoSpawn):
    """""""""
    - Los enemigos spawnean en waves configuradas a mano (level design)
    - Cada wave tiene un spawn rate de enemigos
    - Las waves se ejecutan secuencialmente
    - Hasta que no matás a todos los enemigos de una wave no empieza la siguiente
    - Cuando las teriminás todas las waves que haya, el juego entra en "modo infinito" con alguna de las otras dos opciones.
    """""""""

    def __init__(self):
        super().__init__()
    
    def get_siguiente_enemigo(self):
        pass

    def deberia_spawnear(self):
        pass
