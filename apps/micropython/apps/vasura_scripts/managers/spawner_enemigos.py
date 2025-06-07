from apps.vasura_scripts.entities.enemigos.enemigo import *
from apps.vasura_scripts.managers.enemigos_manager import TIPOS_DE_ENEMIGO, EnemigosManager
from apps.vasura_scripts.managers.tablas import comportamiento_test

from utime import ticks_ms, ticks_diff, ticks_add
from urandom import randint, seed, choice
from math import floor


class SpawnerEnemigos():
    def __init__(self, manager: EnemigosManager):
        self.manager : EnemigosManager = manager
        #TODO Agregar comportamiento que tire waves random de entre las mas dificiles (y capaz algunas no tan dificiles para ir intercalando) y usarlo como fallback
        self.comportamiento_fallback : ComportamientoSpawn = SpawnRandomIncremental(**comportamiento_test)

        #TODO construir esto desde un archivo de texto por el amor de dios kenoexiste
        #Tipo, cantidad, tiempo entre spawn
        #Tener en cuenta la cantidad de sprites que hay pooleados para cada enemigo
        waves = [
            WaveEnemigos([
                (Driller,  2, 3),
                (Driller,  1, 5),
                (Driller,  2, 0),
            ]),

            WaveEnemigos([
                (Driller,  5, 1)
            ], 3),

            WaveEnemigos([
                (Spiraler, 3, 2.5),
                (Spiraler, 1, 1.75),
                (Spiraler, 1, 3),
                (Spiraler, 2, 0)
            ]),

            WaveEnemigos([
                (Spiraler, 4, 1.5)
            ], 3),

            WaveEnemigos([
                (Driller,  1, 2),
                (Spiraler, 1, 2),
                (Driller,  1, 1),
                (Spiraler, 1, 4),
                (Spiraler, 3, 2),
                (Driller,  3, 2),
            ], 1),

            WaveEnemigos([
                (Bully,  1, 0)
            ], 1),

            WaveEnemigos([
                (Driller,  3, 3),
                (Bully,    2, 6),
                (Driller,  1, 0),
                (Bully,    1, 4),
                (Bully,    1, 0),
                (Driller,  4, 3),
                (Bully,    1, 5),
                (Bully,    4, 1.75),
            ], 2),

            WaveEnemigos([
                (Bully,     1, 2),
                (Spiraler,  3, 2),
            ], 3),

            WaveEnemigos([
                (Chiller,  1, 0),
            ], 3),

            WaveEnemigos([
                (Driller,  3, 3),
                (Chiller,  1, 7),
                (Driller,  3, 3),
            ], 3),
        ]

        self.comportamiento : ComportamientoSpawn = SpawnPorWaves(waves, manager.enemigos_spawneados.is_empty, delay=2)
                
        seed(ticks_ms())


    def step(self):
        if self.comportamiento.deberia_spawnear():
            self.spawnear_enemigo()


    def spawnear_enemigo(self):
        tipo = self.comportamiento.get_siguiente_enemigo()
        
        if not tipo:
            if self.comportamiento.terminado:
                self.comportamiento = self.comportamiento_fallback

                tipo = self.comportamiento.get_siguiente_enemigo()
            else: 
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
            e.set_position(pos, e.min_y)
            pos = (pos + 256 // 3) % 256

        
class ComportamientoSpawn:
    def __init__(self):
        self.terminado = False
    
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
        return not self.terminado and ticks_diff(self.tiempo_siguiente_spawn, ticks_ms()) <= 0


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
                return entrada[0]

        return None

    def deberia_spawnear(self):
        return not self.terminado and ticks_diff(self.tiempo_siguiente_spawn, ticks_ms()) <= 0

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


class WaveEnemigos:
    def __init__(self, pasos:List[(Enemigo, int, float)], delay:float = 0):
        self.id = id

        self.delay = delay * 1000
        self.pasos = []
        self.terminada : bool = False

        pasos.reverse()
        for tipo_enemigo, cantidad, intervalo_spawn in pasos:
            t = floor(intervalo_spawn * 1000)

            self.pasos.append((tipo_enemigo, cantidad, t))

    def get_siguiente_paso(self):
        if self.terminada:
            return

        p = self.pasos.pop()

        if not self.pasos:
            self.terminada = True
        
        return p

#TODO Que el tiempo de espera de una wave sea para el final y no el delay con el que empieza
class SpawnPorWaves(ComportamientoSpawn):
    def __init__(self, waves:List[WaveEnemigos], no_quedan_enemigos_vivos:callable, delay : float = 0):
        super().__init__()
        self.waves : List[WaveEnemigos] = waves
        self.waves.reverse()

        self.wave_actual : WaveEnemigos = self.waves.pop()
        
        self.tiempo_siguiente_spawn : int = ticks_add(ticks_ms(), floor(delay + self.wave_actual.delay))

        self.tipo_enemigo_actual = None
        self.enemigos_restantes_paso : int = 0
        self.intervalo_spawn_actual : int = -1

        self.no_quedan_enemigos_vivos : callable = no_quedan_enemigos_vivos

    def get_siguiente_enemigo(self):
        if self.wave_actual.terminada and self.enemigos_restantes_paso == 0:
            if not self.waves:
                self.terminado = True
                
                return None
            
            self.wave_actual = self.waves.pop()
            self.tiempo_siguiente_spawn = ticks_add(ticks_ms(), floor(self.wave_actual.delay))

            return None
        
        if self.enemigos_restantes_paso == 0:
            self.tipo_enemigo_actual, self.enemigos_restantes_paso, self.intervalo_spawn_actual = self.wave_actual.get_siguiente_paso()
        
        self.enemigos_restantes_paso -= 1
        self.tiempo_siguiente_spawn = ticks_add(ticks_ms(), self.intervalo_spawn_actual)

        return self.tipo_enemigo_actual


    def deberia_spawnear(self):
        spawn_timeout = ticks_diff(self.tiempo_siguiente_spawn, ticks_ms()) <= 0

        return not self.terminado and (self.no_quedan_enemigos_vivos() if (self.wave_actual.terminada and self.enemigos_restantes_paso == 0) else spawn_timeout)
        
