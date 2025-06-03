from apps.vasura_scripts.entities.entidad import *

from apps.vasura_scripts.estado import *

from ventilastation.director import stripes

class Enemigo(Entidad):
    
    puntaje : int = 0
    
    estado_inicial : Estado = None
    strip : str

    def __init__(self, scene):
        super().__init__(scene, stripes[self.strip])
        
        self.al_colisionar_con_bala : Evento = Evento()

        self.set_perspective(1)

        self.set_estado(Deshabilitado)


    def reset(self):
        self.set_strip(stripes[self.strip])
        self.set_estado(self.estado_inicial)


    def step(self):
        nuevo_estado = self.estado.step()
        if nuevo_estado:
            self.set_estado(nuevo_estado)


    def hit(self):
        self.al_colisionar_con_bala.disparar(self)
        
        self.set_estado(Explotando)
            

    def morir(self):
        self.set_estado(Deshabilitado)

        self.al_morir.disparar(self)


    def limpiar_eventos(self):
        self.al_colisionar_con_bala.limpiar()

        super().limpiar_eventos()



class Driller(Enemigo):
    estado_inicial = Bajando

    def __init__(self, scene):
        self.velocidad_y = 0.5

        self.strip = "driller-sheet.png"
        self.puntaje = 50

        super().__init__(scene)


class Chiller(Enemigo):
    estado_inicial = Bajando

    def __init__(self, scene):
        self.velocidad_y = 0.5

        self.strip = "chiller-sheet.png"
        self.puntaje = 50

        super().__init__(scene)


class Bully(Enemigo):
    estado_inicial = Persiguiendo

    def __init__(self, scene):
        self.velocidad_x = 1.5
        self.velocidad_y = 1

        self.strip = "bully-sheet.png"
        self.puntaje = 50

        super().__init__(scene)
