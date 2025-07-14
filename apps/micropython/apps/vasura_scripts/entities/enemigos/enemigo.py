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

        self.set_frame(0)
        self.set_direccion(1)

        self.set_estado(self.estado_inicial)
        


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
        self.velocidad_y = 0.52

        self.strip = "driller-sheet.png"
        self.largo_animacion = 7
        self.puntaje = 75

        super().__init__(scene)


class Chiller(Enemigo):
    estado_inicial = ChillerBajando

    def __init__(self, scene):
        self.velocidad_x = 1.25
        self.velocidad_y = 0.6

        self.strip = "chiller-sheet.png"
        self.largo_animacion = 6
        self.puntaje = 150

        super().__init__(scene)


class Bully(Enemigo):
    estado_inicial = Persiguiendo

    def __init__(self, scene):
        self.velocidad_x = 1.3
        self.velocidad_y = 0.87

        self.velocidad_y_original = self.velocidad_y

        self.strip = "bully-sheet.png"
        self.largo_animacion = 5
        self.puntaje = 200

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
        if isinstance(self.estado, Explotando):
            return
        
        self.velocidad_y = 0
        self.set_estado(YendoDerecho)

    def al_respawnear_nave(self):
        if isinstance(self.estado, Explotando):
            return
        
        self.velocidad_y = self.velocidad_y_original
        self.set_estado(Persiguiendo)


class Spiraler(Enemigo):
    estado_inicial = BajandoEnEspiral

    def __init__(self, scene):
        self.velocidad_x = 0.7
        self.velocidad_y = 0.25

        self.strip = "spiraler-sheet.png"
        self.largo_animacion = 8
        self.puntaje = 125

        super().__init__(scene)


    def hit(self, from_x : int = 0):
        delta = min(self.x(), from_x)
        x_spiraler_wrappeado = (self.x() - delta + 128) % 256
        from_x_wrappeado = (from_x - delta + 128) % 256

        if from_x_wrappeado > x_spiraler_wrappeado and self.direccion == 1 or from_x_wrappeado < x_spiraler_wrappeado and self.direccion == -1:
            director.sound_play("vasura_espacial/escudo_spiraler")
            return False

        return super().hit()
