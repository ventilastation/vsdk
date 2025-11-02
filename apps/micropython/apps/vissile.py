from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

MIRA_VELOCIDAD_HORIZONTAL = 4
EXPLOSION_FRAMES = 5
# MIRA_ANCHO = 9
# MIRA_ALTO = 9

class Mira:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["mira.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(1)
        self.reiniciar()

    def reiniciar(self):
        self.sprite.set_x(127 - self.sprite.width()//2)
        self.sprite.set_y(65)

    # No llega hasta el plano horizontal porque no van a venir misiles por el piso XD
    def mover_izq(self):
        self.x_actual = max(self.sprite.x(), 80 - self.sprite.width()//2)  # Bound izquierdo
        self.sprite.set_x( self.x_actual - MIRA_VELOCIDAD_HORIZONTAL)

    def mover_der(self):
        self.x_actual = min(self.sprite.x(), 175 - self.sprite.width()//2)  # Bound derecho
        self.sprite.set_x( self.x_actual + MIRA_VELOCIDAD_HORIZONTAL)

    # Sube y baja escalonadamente
    def subir(self):
        self.sprite.set_y( max(self.sprite.y() - 25, 40) )

    def bajar(self):
        self.sprite.set_y( min(self.sprite.y() + 25, 90))

class Misil:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["misil.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(1)
        self.sprite.disable()

    def activar(self):
        self.sprite.set_x(randrange(90,165))  # Tiene que estar dentro del área que puede cubrir la mira (x > 80 && x < 175)
        self.sprite.set_y(30)
        self.sprite.set_frame(0)
        # self.sprite.disable = False
        
    def desactivar(self):
        self.sprite.disable()

    def mover(self):
        self.y_actual = self.sprite.y()
        self.sprite.set_y(self.y_actual + 1)

# class Cascote:
#     def __init__(self, torreta, target_center_x):
#         self.sprite = Sprite()
#         self.sprite.set_strip(stripes["cascote.png"])
#         self.sprite.set_frame(0)
#         self.sprite.set_perspective(1)
#         self.target_center_x = target_center_x  # valor del **centro** del objetivo
#         self.torreta = torreta
#         self.delete = False

#         # Torretas isquierdas, de izquierda a derecha
#         if torreta == 1:
#             self.sprite.set_x(64 - self.sprite.width())
#             self.sprite.set_y(40)
#         elif torreta == 2:
#             self.sprite.set_x(64 - self.sprite.width())
#             self.sprite.set_y(65)
#         elif torreta == 3:
#             self.sprite.set_x(64 - self.sprite.width())
#             self.sprite.set_y(90)
#         # Torretas derechas, de izquierda a derecha
#         elif torreta == 4:
#             self.sprite.set_x(192 - self.sprite.width())
#             self.sprite.set_y(90 + 4)
#             self.sprite.set_frame(1)
#         elif torreta == 5:
#             self.sprite.set_x(192 - self.sprite.width())
#             self.sprite.set_y(65 + 4)
#             self.sprite.set_frame(1)
#         elif torreta == 6:
#             self.sprite.set_x(192 - self.sprite.width())
#             self.sprite.set_y(40 + 4)
#             self.sprite.set_frame(1)
    
#     def mover(self):
        
#         self.x_actual = self.sprite.x()
#         self.x_centro = self.x_actual + (self.sprite.width() // 2)

#         if self.torreta == 1 or self.torreta == 2 or self.torreta == 3 :
#             if self.x_centro + 2 < self.target_center_x:
#                 self.sprite.set_x(self.x_actual + 1)
#             else:
#                 self.delete = True
#         else:
#             if self.x_centro + 2 > self.target_center_x:
#                 self.sprite.set_x(self.x_actual - 1)
#             else:
#                 self.delete = True
            
            

# class Explosion:
#     def __init__(self, center_x, center_y):
#         self.sprite = Sprite()
#         self.sprite.set_strip(stripes["explosion.png"])
#         self.sprite.set_frame(0)
#         self.sprite.set_perspective(1)
#         self.sprite.set_x(center_x - (self.sprite.width()// 5) // 2)
#         self.sprite.set_y(center_y - 10)
#         self.delete = False
#         self.animation_delay = 15  # Contador que se usa para ralentizar la animación

#     def animar(self):
#         current_frame = self.sprite.frame()
#         if current_frame < EXPLOSION_FRAMES - 2:
#             if self.animation_delay % 6 == 0:
#                 self.sprite.set_frame(current_frame+1)
#             self.animation_delay = self.animation_delay + 1
#         else:
#             self.delete = True



class Vissile(Scene):
    stripes_rom = "vissile"

    

    def on_enter(self):
        super(Vissile, self).on_enter()

        self.mira = Mira()
        # self.explosiones = []
        # self.cascotes = []
        
        self.misiles_reserva = [Misil(), Misil(), Misil(), Misil()]
        self.misiles_activos = []

        # cielo = Sprite()
        # cielo.set_strip(stripes["cielo.png"])
        # cielo.set_x(0)
        # cielo.set_y(0)
        # cielo.set_frame(0)
        # cielo.set_perspective(1)
    

    def step(self):

        # Movimiento de la mira
        if director.is_pressed(director.JOY_LEFT):
            self.mira.mover_izq()

        if director.is_pressed(director.JOY_RIGHT):
            self.mira.mover_der()

        if director.was_pressed(director.JOY_UP):
            self.mira.subir()

        if director.was_pressed(director.JOY_DOWN):
            self.mira.bajar()

        # Disparar cascote
        if director.was_pressed(director.BUTTON_A):

            # Temporalmente también usar el clic para crear misiles
            if len(self.misiles_reserva)  > 0:
                m = self.misiles_reserva.pop()  # Obtengo misil de reserva
                m.activar()  # Lo reinicializo
                self.misiles_activos.append(m)  # Lo agrego a los misiles activos

            # target_x_center = self.mira.sprite.x() - (self.mira.sprite.width() // 2)
            # if self.mira.sprite.x() < 128 - self.mira.sprite.width() // 2:
            #     if self.mira.sprite.y() == 40:
            #         self.cascotes.append(Cascote(1, target_x_center - self.mira.sprite.width()//2))
            #     elif self.mira.sprite.y() == 65:
            #         self.cascotes.append(Cascote(2, target_x_center - self.mira.sprite.width()//2))
            #     elif self.mira.sprite.y() == 90:
            #         self.cascotes.append(Cascote(3, target_x_center - self.mira.sprite.width()//2))
            # else:
            #     if self.mira.sprite.y() == 40:
            #         self.cascotes.append(Cascote(6, target_x_center + self.mira.sprite.width()//2))
            #     elif self.mira.sprite.y() == 65:
            #         self.cascotes.append(Cascote(5, target_x_center + self.mira.sprite.width()//2))
            #     elif self.mira.sprite.y() == 90:
            #         self.cascotes.append(Cascote(4, target_x_center + self.mira.sprite.width()//2))
            

        # Actualizar misiles
        for m in self.misiles_activos:
            if m.sprite.y() > 120:
                m.desactivar()
                self.misiles_activos.remove(m)
                self.misiles_reserva.append(m)
                # TODO Take damage!
            else:
                m.mover()
        
        # Actualizar explosiones
        # for e in self.explosiones:
        #     e.animar()
        #     if e.delete:
        #         e.sprite.disable()
        #         self.explosiones.remove(e)
        
        # for c in self.cascotes:
        #     if c.delete:
        #         center_x = c.sprite.x() + (c.sprite.width() // 2)
        #         center_y = c.sprite.y() - (c.sprite.height() // 2)
        #         e = Explosion(center_x, center_y)
        #         # TODO: Sólo permitir una cantidad determinada de explosiones al mismo tiempo para evitar flooding
        #         c.sprite.disable()
        #         self.cascotes.remove(c)
        #         self.explosiones.append(e)
        #     else:
        #         c.mover()

        # Salir
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Vissile()