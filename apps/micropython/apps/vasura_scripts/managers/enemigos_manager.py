from apps.vasura_scripts.entities.enemigos.enemigo import *

LIMITE_ENEMIGOS = 20

class EnemigosManager():
    def __init__(self, scene):
        self.enemigos_libres : List[Enemigo] = []
        self.enemigos_spawneados : List[Enemigo] = []

        self.al_morir_enemigo : Evento = Evento()

        for _ in range(LIMITE_ENEMIGOS):
            e = Driller(scene)
            e.al_morir.suscribir(self.reciclar_enemigo)
            e.al_colisionar_con_bala.suscribir(self.al_morir_enemigo.disparar)

            self.enemigos_libres.append(e)

    def step(self):
        [e.step() for e in self.enemigos_spawneados]

    #TODO ver cómo manejar enemigos de distinto tipo
    def get_enemigo(self):
        if not self.enemigos_libres:
            return None

        e : Enemigo = self.enemigos_libres.pop()
        self.enemigos_spawneados.append(e)

        return e

    def reciclar_enemigo(self, e:Enemigo):
        if not e in self.enemigos_spawneados:
            return

        self.enemigos_spawneados.remove(e)
        self.enemigos_libres.append(e)
    
    def limpiar(self):
        [e.limpiar_eventos() for e in self.enemigos_libres]
        [e.limpiar_eventos() for e in self.enemigos_spawneados]

        self.enemigos_libres = []
        self.enemigos_spawneados = []

    