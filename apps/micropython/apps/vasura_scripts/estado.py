from ventilastation.director import director, stripes

class Estado:
    strip = None

    def __init__(self, entidad):
        self.entidad = entidad


    def on_enter(self):
        self.entidad.sprite.set_strip(stripes[self.strip])
        self.entidad.sprite.set_frame(0)


    def step(self):
        pass


    def on_exit(self):
        pass



class Deshabilitado(Estado):
    def on_enter(self):
        self.entidad.sprite.disable()



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
            self.entidad.sprite.disable()
        else:
            self.entidad.sprite.set_frame(0)



class Vulnerable(Estado):
    def step(self):
        es_nave = self.entidad.__class__.__name__ == "Nave"
        if not es_nave:
            if self.entidad.sprite.collision([self.entidad.scene.nave.sprite]):
                self.entidad.scene.muerte()
                return Explotando

        bala = self.entidad.scene.get_colision_bala(self.entidad.sprite)
        if bala:
            print("Bala impacta")
            print(bala)
            self.entidad.scene.liberar_bala(bala)
            if es_nave:
                self.entidad.scene.muerte()
            return Explotando



class Bajando(Vulnerable):
    strip = "ship-sprite-sym.png"

    def step(self):
        cambio = super().step()
        if cambio:
            return cambio

        self.entidad.sprite.set_y(self.entidad.sprite.y() + 1)

        if self.entidad.sprite.y() >= 128-25:
            return Explotando

