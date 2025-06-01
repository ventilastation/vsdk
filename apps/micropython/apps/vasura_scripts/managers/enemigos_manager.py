from apps.vasura_scripts.entities.enemigos.enemigo import *

LIMITE_ENEMIGOS = 20

class EnemigosManager():

    enemigos_inactivos : List[Enemigo] = []
    enemigos_activos : List[Enemigo] = []

    def __init__(self, scene):
        self.al_morir_enemigo : callable = None

        for _ in range(LIMITE_ENEMIGOS):
            e = Driller(scene)
            e.suscribir_muerte(self.reciclar_enemigo)

            self.enemigos_inactivos.append(e)

    def step(self):
        [e.step() for e in self.enemigos_activos]

    #TODO ver cómo manejar enemigos de distinto tipo
    def get_enemigo(self):
        e : Enemigo = self.enemigos_inactivos.pop()
        
        #TODO kepasa si no quedan enemigos
        self.enemigos_activos.append(e)

        return e

    def reciclar_enemigo(self, e:Enemigo):
        if not e in self.enemigos_activos:
            return

        self.enemigos_activos.remove(e)
        self.enemigos_inactivos.append(e)

        if self.al_morir_enemigo:
            self.al_morir_enemigo(e)

    