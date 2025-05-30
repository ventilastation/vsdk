from apps.vasura_scripts.entities.bala import *

LIMITE_BALAS : int = 20

class BalasManager():

    balas_libres : List[Bala] = list()
    balas_usadas : List[Bala] = list()

    def __init__(self):
        self.balas_libres = [
            Bala(self) 
            for _ in range(LIMITE_BALAS)
        ]

        self.balas_usadas = []
    
    def step(self):
        [bala.step() for bala in self.balas_usadas]

    def get_bala_libre(self):
        if not self.balas_libres:
            return None

        bala = self.balas_libres.pop()
        self.balas_usadas.append(bala)

        return bala

    def get_bala_colisionando(self, entidad : Entidad, liberar : bool = False):
        balas_sprites = [x for x in self.balas_usadas]
        
        bala = entidad.collision(balas_sprites)
        
        if bala:
            if (liberar):
                self.liberar_bala(bala)
                
            return bala

    def liberar_bala(self, bala):
        bala.disable()
        self.balas_usadas.remove(bala)
        self.balas_libres.append(bala)