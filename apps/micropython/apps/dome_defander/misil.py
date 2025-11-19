from urandom import randrange
from ventilastation.director import stripes
from ventilastation.sprites import Sprite

# Misiles enemigos
class Misil:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["misil.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(2)
        self.sprite.disable()
        self.movement_delay = 0  # Usado para ralentizar el avance de los misiles

        self.humo_reserva = [Humo(), Humo(), Humo(), Humo(), Humo(), Humo(), Humo(), Humo(), Humo(), Humo(), Humo(), Humo()]
        self.humo_activos = []

    def activar(self):
        self.sprite.set_x(randrange(90,165))  # Tiene que estar dentro del área que puede cubrir la mira (x > 80 && x < 175)
        self.sprite.set_y(0)
        self.sprite.set_frame(0)
        
    def desactivar(self):
        self.sprite.disable()
        if len(self.humo_activos) > 0:
            for h in self.humo_activos:
                h.desactivar()
                self.humo_activos.remove(h)
                self.humo_reserva.append(h)

    def animar(self):
        # Animar misil
        self.x_actual = self.sprite.x()
        self.y_actual = self.sprite.y()
        self.movement_delay = self.movement_delay + 1
        step = randrange(3,6)
        if self.movement_delay % step == 0:
            self.sprite.set_y(self.y_actual + 1)
        
        # Crear humo
        if self.y_actual > 5 and self.movement_delay % 4:
            if len(self.humo_reserva) > 0:
                h = self.humo_reserva.pop()
                h.activar(self.x_actual + self.sprite.width() // 2, self.y_actual + self.sprite.height() // 2 - 4)
                self.humo_activos.append(h)
        
        # Animar humo
        if len(self.humo_activos) > 0:
            for h in self.humo_activos:
                if h.delete:
                    self.humo_activos.remove(h)
                    self.humo_reserva.append(h)
                else:
                    h.animar()


class Humo:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["humo.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(2)
        self.sprite.disable()
        self.animation_delay = 0  # Usado para ralentizar el avance de los misiles
        self.delete = True
        
    def activar(self, x_center, y_center):
        self.sprite.set_x(x_center - self.sprite.width() // 2)  # Tiene que estar dentro del área que puede cubrir la mira (x > 80 && x < 175)
        self.sprite.set_y(y_center - self.sprite.height() // 2)
        self.sprite.set_frame(0)
        self.delete = False
        
    def desactivar(self):
        self.sprite.disable()
        self.delete = True

    def animar(self):
        self.animation_delay = self.animation_delay + 1
        if self.animation_delay % 5 == 0:
            current_frame = self.sprite.frame()
            if current_frame < 2:
                self.sprite.set_frame(current_frame + 1)
            else:
                self.desactivar()