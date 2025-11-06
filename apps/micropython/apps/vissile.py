from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

MIRA_VELOCIDAD_HORIZONTAL = 2
EXPLOSION_FRAMES = 4
ANCHO_MIRA = 8
ALTO_MIRA = 8
STARTING_LIVES = 3

class Mira:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["mira.png"])
        self.sprite.set_perspective(2)
        self.reiniciar()
        self.desactivar()

    def desactivar(self):
        self.sprite.disable()

    def reiniciar(self):
        self.sprite.set_x(127 - ANCHO_MIRA//2)
        self.sprite.set_y(23)
        self.sprite.set_frame(0)

    # No llega hasta el plano horizontal porque no van a venir misiles por el piso XD
    def mover_izq(self):
        self.x_actual = max(self.sprite.x(), 80 - ANCHO_MIRA//2)  # Bound izquierdo
        self.sprite.set_x( self.x_actual - MIRA_VELOCIDAD_HORIZONTAL)

    def mover_der(self):
        self.x_actual = min(self.sprite.x(), 175 - ANCHO_MIRA//2)  # Bound derecho
        self.sprite.set_x( self.x_actual + MIRA_VELOCIDAD_HORIZONTAL)

    # Sube y baja escalonadamente
    def subir(self):
        self.sprite.set_y( max(self.sprite.y() - 10, 13) )

    def bajar(self):
        self.sprite.set_y( min(self.sprite.y() + 10, 33))

class Misil:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["misil.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(2)
        self.sprite.disable()
        self.movement_delay = 0  # Usado para ralentizar el avance de los misiles

    def activar(self):
        self.sprite.set_x(randrange(90,165))  # Tiene que estar dentro del área que puede cubrir la mira (x > 80 && x < 175)
        self.sprite.set_y(0)
        self.sprite.set_frame(0)
        
    def desactivar(self):
        self.sprite.disable()

    def mover(self):
        self.y_actual = self.sprite.y()
        self.movement_delay = self.movement_delay + 1
        step = randrange(3,6)
        if self.movement_delay % step == 0:
            self.sprite.set_y(self.y_actual + 1)

class Cascote:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["cascote.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(2)
        self.sprite.disable()
        self.delete = True

    def activar(self, torreta, target_center_x):
        self.torreta = torreta
        self.target_center_x = target_center_x  # valor del **centro** del objetivo
        self.delete = False
        self.sprite.set_frame(0)
        
        # Torretas isquierdas, de izquierda a derecha
        if torreta == 1:
            self.sprite.set_x(64 - self.sprite.width())
            self.sprite.set_y(13 + 2)
        elif torreta == 2:
            self.sprite.set_x(64 - self.sprite.width())
            self.sprite.set_y(23 + 2)
        elif torreta == 3:
            self.sprite.set_x(64 - self.sprite.width())
            self.sprite.set_y(33 + 2)
        # Torretas derechas, de izquierda a derecha
        elif torreta == 4:
            self.sprite.set_x(192 - self.sprite.width())
            self.sprite.set_y(33 + 2)
        elif torreta == 5:
            self.sprite.set_x(192 - self.sprite.width())
            self.sprite.set_y(23 + 2)
        elif torreta == 6:
            self.sprite.set_x(192 - self.sprite.width())
            self.sprite.set_y(13 + 2)        
    
    def desactivar(self):
        self.sprite.disable()

    def mover(self):    
        x_actual = self.sprite.x()
        centrer_x = x_actual + (self.sprite.width() // 2)

        if self.torreta == 1 or self.torreta == 2 or self.torreta == 3 :
            if centrer_x <= self.target_center_x:
                self.sprite.set_x(x_actual + 2)
            else:
                self.delete = True
        else:
            if centrer_x >= self.target_center_x:
                self.sprite.set_x(x_actual - 2)
            else:
                self.delete = True
            
            

class Explosion:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["explosion2.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(2)
        self.sprite.disable()
        self.delete = True
        self.animation_delay = 1  # Contador que se usa para ralentizar la animación

    def activar(self, center_x, center_y):
        self.sprite.set_x(center_x - self.sprite.width()//2)
        self.sprite.set_y(center_y - 5)
        self.delete = False
        self.sprite.set_frame(0)

    def desactivar(self):
        self.sprite.disable()

    def colisiones(self, targets):
        def intersects(x1, w1, x2, w2):
            delta = min(x1, x2)
            x1 = (x1 - delta + 128) % 256
            x2 = (x2 - delta + 128) % 256
            return x1 < x2 + w2 and x1 + w1 > x2
        self.collisions = []

        for target in targets:
            other = target
            if (intersects(self.sprite.x(), self.sprite.width(), other.sprite.x(), other.sprite.width()) and
                intersects(self.sprite.y(), self.sprite.height(), other.sprite.y(), other.sprite.height())):
                self.collisions.append(target)
            
        return self.collisions

    def animar(self):
        current_frame = self.sprite.frame()
        if current_frame < EXPLOSION_FRAMES:
            if self.animation_delay % 3 == 0:
                self.sprite.set_frame(current_frame+1)
            self.animation_delay = self.animation_delay + 1
        else:
            self.delete = True

class Nuke:
    def __init__(self):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes["nuke.png"])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(2)
        self.sprite.set_x(128 - self.sprite.width()//2)
        self.sprite.set_y(36)
        self.sprite.disable()
        self.animation_delay = 1  # Contador que se usa para ralentizar la animación

    def reset(self):
        self.animation_delay = 1 
        self.sprite.set_frame(0)

    def desactivar(self):
        self.sprite.disable()

    def animar(self):
        current_frame = self.sprite.frame()

        if current_frame < EXPLOSION_FRAMES:
            if self.animation_delay % 8 == 0:
                self.sprite.set_frame(current_frame+1)
            
        else:
            if self.animation_delay % 8 == 0:
                self.sprite.set_frame(current_frame-1)

        self.animation_delay = self.animation_delay + 1

class ScoreVidas():

    def __init__(self, score=0, vidas=STARTING_LIVES):
        self.score = score
        self.vidas = vidas

        self.crear_cartel()
        self.actualizar()

    def puntuar(self):
        self.score += 1
        self.actualizar()

    def perder(self):
        self.vidas -= 1
        self.actualizar()
        return (self.vidas <= 0)

    def actualizar(self):
        print(f"Score: {self.score} - Vidas: {self.vidas}")

        # Score    
        for n, l in enumerate("%05d" % self.score):
            v = ord(l) - 0x30
            self.chars[n].set_frame(v)

        # Vidas
        for n in range(STARTING_LIVES):
            self.chars[6+n].set_frame(10 + int(self.vidas > n))
    
    def crear_cartel(self):
        print("crear_cartel")
        self.chars = []
        for n in range(9):
            s = Sprite()
            s.set_strip(stripes["numerals.png"])
            s.set_x(110 + n * 4)
            s.set_y(0)
            s.set_frame(10)
            s.set_perspective(2)
            self.chars.append(s)


class Vissile(Scene):
    stripes_rom = "vissile"

    def on_enter(self):
        super(Vissile, self).on_enter()
        
        # self.lives = STARTING_LIVES
        self.sc = ScoreVidas(0, STARTING_LIVES)
        
        director.music_play(b"vissile/play1")

        self.state = "start"
        
        self.mira = Mira()

        self.explosiones_reserva = [Explosion(), Explosion(), Explosion(), Explosion()]
        self.explosiones_activas = []

        self.cascotes_reserva = [Cascote(), Cascote(), Cascote()]
        self.cascotes_activos = []
        
        self.misiles_reserva = [Misil(), Misil(), Misil(), Misil()]
        self.misiles_activos = []
        
        self.pushtostart = Sprite()
        self.pushtostart.set_strip(stripes["pushtostart.png"])
        self.pushtostart.set_x(255 - self.pushtostart.width()//2)
        self.pushtostart.set_y(5)
        self.pushtostart.set_frame(0)
        self.pushtostart.set_perspective(2)

        self.failed = Sprite()
        self.failed.set_strip(stripes["failed.png"])
        self.failed.set_x(255 - self.failed.width()//2)
        self.failed.set_y(20)
        self.failed.set_frame(0)
        self.failed.set_perspective(2)
        self.failed.disable()

        self.nuke = Nuke()

        tierra = Sprite()
        tierra.set_strip(stripes["tierra.png"])
        tierra.set_x(192)
        tierra.set_y(0)
        tierra.set_frame(0)
        tierra.set_perspective(2)

        cielo = Sprite()
        cielo.set_strip(stripes["cielo.png"])
        cielo.set_x(64)
        cielo.set_y(0)
        cielo.set_frame(0)
        cielo.set_perspective(2)


    def step(self):

        if self.state == "start":
            self.pushtostart.set_frame(0)

            if director.was_pressed(director.BUTTON_A):
                self.state = "playing"
                self.mira.reiniciar()
                self.pushtostart.disable()
                return
            
        if self.state == "playing":

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

                if self.sc.vidas > 0:

                    if len(self.cascotes_reserva) > 0:
                    
                        director.sound_play(b"vissile/cascote1")
                        c = self.cascotes_reserva.pop()
                        
                        mira_center_x = self.mira.sprite.x() + (self.mira.sprite.width() // 2)
                        if mira_center_x < 128 :
                            if self.mira.sprite.y() == 13:
                                c.activar(1, mira_center_x)
                                self.cascotes_activos.append(c)
                            elif self.mira.sprite.y() == 23:
                                c.activar(2, mira_center_x)
                                self.cascotes_activos.append(c)
                            elif self.mira.sprite.y() == 33:
                                c.activar(3, mira_center_x)
                                self.cascotes_activos.append(c)
                        else:
                            if self.mira.sprite.y() == 13:
                                c.activar(6, mira_center_x)
                                self.cascotes_activos.append(c)
                            elif self.mira.sprite.y() == 23:
                                c.activar(5, mira_center_x)
                                self.cascotes_activos.append(c)
                            elif self.mira.sprite.y() == 33:
                                c.activar(4, mira_center_x)
                                self.cascotes_activos.append(c)

            if self.sc.vidas > 0 and self.state == "playing":

                # Actualizar misiles
                if len(self.misiles_activos) > 0 and self.state == "playing":
                    for m in self.misiles_activos:
                        if m.sprite.y() > 48:  # Misil llega al domo
                            self.sc.perder()
                            if self.sc.vidas == 0:
                                director.sound_play(b"vissile/fin")
                                self.nuke.reset()
                                self.state = "lose"
                                break
                                # Fin
                                
                            else:
                                # Hit
                                director.sound_play(b"vissile/hit1")
                                m.desactivar()
                                self.misiles_activos.remove(m)
                                self.misiles_reserva.append(m)
                            
                        else:
                            m.mover()

                # Generar nuevos misiles
                if len(self.misiles_activos) < 3 and self.state == "playing":
                        director.sound_play(b"vissile/misil1")
                        m = self.misiles_reserva.pop()
                        m.activar()
                        self.misiles_activos.append(m)

                # Actualizar explosiones
                if len(self.explosiones_activas) > 0 and self.state == "playing":
                    for e in self.explosiones_activas:
                        if e.delete:
                            e.desactivar()
                            self.explosiones_activas.remove(e)
                            self.explosiones_reserva.append(e)
                        else:
                            for i in range(4):
                                lm = e.colisiones(self.misiles_activos)
                                for m in lm:
                                    m.desactivar()
                                    self.sc.puntuar()
                                    self.misiles_activos.remove(m)
                                    self.misiles_reserva.append(m)
                            e.animar()
            
                # Actualizar cascotes
                if len(self.cascotes_activos) > 0 and self.state == "playing":
                    for c in self.cascotes_activos:
                        if c.delete:
                            c.desactivar()
                            self.cascotes_activos.remove(c)
                            self.cascotes_reserva.append(c)
                            
                            center_x = c.sprite.x() + (c.sprite.width() // 2)
                            center_y = c.sprite.y() - (c.sprite.height() // 2)
                            if len(self.explosiones_reserva) > 0:
                                director.sound_play(b"vissile/explosion1")
                                e = self.explosiones_reserva.pop()
                                e.activar(center_x, center_y)
                                self.explosiones_activas.append(e)
                        else:
                            c.mover()


        if self.state == "lose":

            self.nuke.animar()
            self.failed.set_frame(0)
            self.pushtostart.set_frame(0)
            self.mira.desactivar()

            if len(self.misiles_activos) > 0:
                for m in self.misiles_activos:
                    m.desactivar()
                    self.misiles_activos.remove(m)
                    self.misiles_reserva.append(m)
                
            if len(self.explosiones_activas) > 0:
                for e in self.explosiones_activas:
                    e.desactivar()
                    self.explosiones_activas.remove(e)
                    self.explosiones_reserva.append(e)

            if len(self.cascotes_activos) > 0:
                for c in self.cascotes_activos:
                    c.desactivar()
                    self.cascotes_activos.remove(c)
                    self.cascotes_reserva.append(c)

            self.mira.desactivar()

            if director.was_pressed(director.BUTTON_A):
                self.failed.disable()
                self.pushtostart.disable()
                self.nuke.desactivar()
                self.mira.reiniciar()
                self.sc.score = 0
                self.sc.vidas = STARTING_LIVES
                self.sc.actualizar()
                self.state = "playing"
                return

        # Salir
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Vissile()