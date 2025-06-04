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
        self.set_frame(0)
        self.set_direccion(1)


    def step(self):
        nuevo_estado = self.estado.step()
        if nuevo_estado:
            self.set_estado(nuevo_estado)


    def hit(self, from_x : int = 0):
        self.al_colisionar_con_bala.disparar(self)
        
        self.set_estado(Explotando)

        return True
            

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
    estado_inicial = ChillerBajando

    def __init__(self, scene):
        self.velocidad_x = 1.15
        self.velocidad_y = 0.5

        self.strip = "chiller-sheet.png"
        self.puntaje = 50

        super().__init__(scene)


class Bully(Enemigo):
    estado_inicial = Persiguiendo

    def __init__(self, scene):
        self.velocidad_x = 1
        self.velocidad_y = 0.75

        self.velocidad_y_original = self.velocidad_y

        self.strip = "bully-sheet.png"
        self.puntaje = 50

        super().__init__(scene)
    
    def morir(self):
        self.scene.nave.al_morir.desuscribir(self.al_morir_nave)
        self.scene.nave.al_respawnear.desuscribir(self.al_respawnear_nave)

        super().morir()
    
    def reset(self):
        self.scene.nave.al_morir.suscribir(self.al_morir_nave)
        self.scene.nave.al_respawnear.suscribir(self.al_respawnear_nave)

        super().reset()

    def al_morir_nave(self, _):
        self.velocidad_y = 0
        self.set_estado(YendoDerecho)

    def al_respawnear_nave(self):
        self.velocidad_y = self.velocidad_y_original
        self.set_estado(Persiguiendo)


class Spiraler(Enemigo):
    estado_inicial = BajandoEnEspiral

    def __init__(self, scene):
        self.velocidad_x = 0.7
        self.velocidad_y = 0.2

        self.strip = "05_bluebee.png"
        self.puntaje = 50

        super().__init__(scene)

        self.set_frame(0)

    def hit(self, from_x : int = 0):
        if from_x > self.x() and self.direccion == 1 or from_x < self.x() and self.direccion == -1:
            return False

        return super().hit()
