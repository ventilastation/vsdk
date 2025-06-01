from apps.vasura_scripts.entities.enemigos.enemigo import *

LIMITE_ENEMIGOS = 20

class EnemigosManager():

    enemigos_inactivos : List[Enemigo] = list()
    enemigos_activos : List[Enemigo] = list()


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
        #BUG este metodo se llama cuando una bala le pega a la nave y nidea porkhe
        if not e in self.enemigos_activos:
            print("Remover enemigo: " + str(type(e)))
            return

        self.enemigos_activos.remove(e)
        self.enemigos_inactivos.append(e)

        if self.al_morir_enemigo:
            self.al_morir_enemigo(e)

    