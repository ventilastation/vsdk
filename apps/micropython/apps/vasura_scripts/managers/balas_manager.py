from apps.vasura_scripts.entities.bala import *

LIMITE_BALAS : int = 20

class BalasManager():

    balas_libres : List[Bala] = list()
    balas_usadas : List[Bala] = list()

    def __init__(self, scene):
        
        for _ in range(LIMITE_BALAS):
            b = Bala(scene)
            b.al_morir = self.liberar_bala
            self.balas_libres.append(b)

        self.balas_usadas = []
    
    def step(self):
        [bala.step() for bala in self.balas_usadas]

    def get_bala_libre(self):
        if not self.balas_libres:
            return None

        #TODO kepasa si no quedan balas
        bala = self.balas_libres.pop()
        self.balas_usadas.append(bala)

        return bala

    def get_bala_colisionando(self, entidad : Entidad, liberar : bool = False):
        bala = entidad.collision(self.balas_usadas)
        
        if bala:
            if (liberar):
                bala.morir()
                
            return bala

    def liberar_bala(self, bala):
        bala.disable()
        self.balas_usadas.remove(bala)
        self.balas_libres.append(bala)
