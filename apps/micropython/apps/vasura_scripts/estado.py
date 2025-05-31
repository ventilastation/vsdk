from ventilastation.director import director, stripes
from apps.vasura_scripts.entities.entidad import *

class Estado:
    strip : int = None
    entidad : Entidad

    def __init__(self, entidad : Entidad):
        self.entidad = entidad


    def on_enter(self):
        #self.entidad.set_strip(stripes[self.strip])
        self.entidad.set_frame(0)


    def step(self):
        pass


    def on_exit(self):
        pass



class Deshabilitado(Estado):
    def on_enter(self):
        self.entidad.disable()



class Explotando(Estado):  # Anarquía

    def __init__(self, entidad):
        super().__init__(entidad)

        # clase = self.entidad.__class__.__name__.lower()
        # self.strip = f"{clase}_explotando.png"
        self.strip = "ship-sprite-sym.png"


    def on_enter(self):
        super().on_enter()
        director.sound_play("vasura_espacial/explosion_enemigo")
        self.frames_left = 90


    def step(self):
        self.frames_left -= 1

        # Muerte
        if self.frames_left == 0:
            return Deshabilitado

        # Blink de ejemplo
        if (self.frames_left // 10) % 2:
            self.entidad.disable()
        else:
            self.entidad.set_frame(0)



class Vulnerable(Estado):
    #TODO mover esto a un lugar donde nos ahorremos el chequeo de tipos
    def step(self):
        es_nave = self.entidad.__class__.__name__ == "Nave"
        if not es_nave:
            if self.entidad.collision([self.entidad.scene.nave]):

                self.entidad.scene.muerte()
                
                return Explotando

        bala : Bala = self.entidad.scene.balas.get_bala_colisionando(self.entidad, True)
        if bala:

            if es_nave:
                self.entidad.scene.muerte()

            return Explotando



class Bajando(Vulnerable):

    def step(self):
        cambio = super().step()
        if cambio:
            return cambio

        self.entidad.mover(0, 1)

        if self.entidad.y() + self.entidad.height() >= self.entidad.scene.planet.get_borde_y():
            self.entidad.scene.planet.hit()
            return Explotando

