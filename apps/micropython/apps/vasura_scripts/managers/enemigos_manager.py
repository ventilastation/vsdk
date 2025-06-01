from apps.vasura_scripts.entities.enemigo import *

LIMITE_ENEMIGOS = 20

class EnemigosManager():

    enemigos_inactivos : List[Enemigo] = list()
    enemigos_activos : List[Enemigo] = list()

    def __init__(self, scene):
        for _ in range(LIMITE_ENEMIGOS):
            e = Driller(scene)
            e.al_morir = self.reciclar_enemigo

            self.enemigos_inactivos.append(e)

    #TODO ver cómo manejar enemigos de distinto tipo
    def get(self):
        e : Enemigo = self.enemigos_inactivos.pop()
        
        #TODO kepasa si no quedan enemigos

        e.reset()

        #TODO deshardcodear. Mover a una clase que se encargue del spawn?
        e.set_position(50, 0)

        self.enemigos_activos.append(e)

        return e

    def reciclar_enemigo(self, e:Enemigo):
        e.set_estado(Deshabilitado)

        self.enemigos_activos.remove(e)
        self.enemigos_inactivos.append(e)

    def step(self):
        [e.step() for e in self.enemigos_activos]