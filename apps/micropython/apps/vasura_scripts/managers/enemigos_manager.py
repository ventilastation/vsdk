from apps.vasura_scripts.entities.enemigos.enemigo import *
from urandom import randint

LIMITE_ENEMIGOS = 21
TIPOS_DE_ENEMIGO = [Driller, Chiller, Bully]

class EnemigosManager():
    def __init__(self, scene):
        self.enemigos_libres : ContainerEnemigos = ContainerEnemigos()
        self.enemigos_spawneados : ContainerEnemigos = ContainerEnemigos()

        self.al_morir_enemigo : Evento = Evento()

        for _ in range(LIMITE_ENEMIGOS // len(TIPOS_DE_ENEMIGO)):
            for i in range(len(TIPOS_DE_ENEMIGO)):
                tipo = TIPOS_DE_ENEMIGO[i]
                e = tipo(scene)
                e.al_morir.suscribir(self.reciclar_enemigo)
                e.al_colisionar_con_bala.suscribir(self.al_morir_enemigo.disparar)
                self.enemigos_libres.append(e)

    def step(self):
        for tipo_enemigo in TIPOS_DE_ENEMIGO:
            [e.step() for e in self.enemigos_spawneados.get_all_of_type(tipo_enemigo)]

    
    def get_enemigo(self, tipo):
        if not self.enemigos_libres.has_of_type(tipo):
            return None

        e : Enemigo = self.enemigos_libres.pop(tipo)
        self.enemigos_spawneados.append(e)

        return e

    def reciclar_enemigo(self, e:Enemigo):
        if not self.enemigos_spawneados.has(e):
            return

        self.enemigos_spawneados.remove(e)
        self.enemigos_libres.append(e)
    
    def limpiar(self):
        [e.limpiar_eventos() for e in self.enemigos_libres]
        [e.limpiar_eventos() for e in self.enemigos_spawneados]

        self.enemigos_libres = None
        self.enemigos_spawneados = None

    
class ContainerEnemigos:
    def __init__(self):
        self.enemigos = {}

        for t in TIPOS_DE_ENEMIGO:
            self.enemigos[t] = []

    def append(self, enemigo):
        self.enemigos[type(enemigo)].append(enemigo)

    def remove(self, enemigo):
        self.enemigos[type(enemigo)].remove(enemigo)

    def pop(self, tipo):
        return self.enemigos[tipo].pop()

    def has_of_type(self, tipo):
        if self.enemigos[tipo]:
            return True
        
        return False

    def has(self, enemigo):
        return enemigo in self.enemigos[type(enemigo)]

    def get_all_of_type(self, tipo):
        return self.enemigos[tipo]