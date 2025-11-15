# By: Martín Vukovic
# https://martinvukovic.com
#
# Music by: JuanElHongo
# https://juanelhongo.itch.io/
#
# Menu image by: manuq
# https://github.com/manuq

from urandom import randrange

from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

from .mira import Mira
from .misil import Misil
from .cascotes import Cascote
from .explosion import Explosion
from .hit_explosion import HitExplosion
from .nuke import Nuke
from .score_vidas import *
from .dome import Dome

def main():
    return DomeDefander()


class DomeDefander(Scene):
    stripes_rom = "dome_defander"

    def play_music_loop(self):
        print("Playing")
        # director.music_off()
        director.music_play("dome_defander/play1")
        self.call_later(451*100, self.play_music_loop)

    def on_enter(self):
        super(DomeDefander, self).on_enter()
        
        # self.lives = STARTING_LIVES
        self.sc = ScoreVidas(0, STARTING_LIVES)
        
        self.play_music_loop()
        # director.music_play("dome_defander/play1")

        self.state = "start"
        
        self.mira = Mira()

        self.explosiones_reserva = [Explosion(), Explosion(), Explosion(), Explosion()]
        self.explosiones_activas = []

        self.hit_explosiones_reserva = [HitExplosion(), HitExplosion(), HitExplosion(), HitExplosion()]
        self.hit_explosiones_activas = []

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

        self.dome = Dome()

        craters = Sprite()
        craters.set_strip(stripes["craters.png"])
        craters.set_x(0)
        craters.set_y(255)
        craters.set_perspective(0)
        craters.set_frame(0)

        marte = Sprite()
        marte.set_strip(stripes["marte.png"])
        marte.set_x(0)
        marte.set_y(255)
        marte.set_perspective(0)
        marte.set_frame(0)

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
                    
                        director.sound_play(b"dome_defander/cascote1")
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
                                # Fin
                                director.sound_play(b"dome_defander/fin")
                                self.nuke.reset()
                                self.end_counter = 0
                                self.dome.hit()
                                self.state = "lose"
                                break                                
                            else:
                                # Hit
                                director.sound_play(b"dome_defander/hit1")
                                m.desactivar()
                                self.misiles_activos.remove(m)
                                self.misiles_reserva.append(m)
                                self.dome.hit()

                                he = self.hit_explosiones_reserva.pop()
                                he.activar(m.sprite.x() - m.sprite.width() // 2)
                                self.hit_explosiones_activas.append(he)
                            
                        else:
                            m.animar()

                # Generar nuevos misiles
                if len(self.misiles_activos) < 3 and self.state == "playing":
                        director.sound_play(b"dome_defander/misil1")
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

                # Actualizar explosiones en el domo
                if len(self.hit_explosiones_activas) > 0 and self.state == "playing":
                    for he in self.hit_explosiones_activas:
                        if he.delete:
                            he.desactivar()
                            self.hit_explosiones_activas.remove(he)
                            self.hit_explosiones_reserva.append(he)
                        else:
                            he.animar()
            
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
                                director.sound_play(b"dome_defander/explosion1")
                                e = self.explosiones_reserva.pop()
                                e.activar(center_x, center_y)
                                self.explosiones_activas.append(e)
                        else:
                            c.mover()


        if self.state == "lose":
            self.nuke.animar()
            self.failed.set_frame(0)
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

            if self.end_counter > 90:

                self.pushtostart.set_frame(0)
                
                if director.was_pressed(director.BUTTON_A):
                    self.dome.reset()
                    self.end_counter = 0
                    self.failed.disable()
                    self.pushtostart.disable()
                    self.nuke.desactivar()
                    self.mira.reiniciar()
                    self.sc.score = 0
                    self.sc.vidas = STARTING_LIVES
                    self.sc.actualizar()
                    self.state = "playing"
                    return
            else:
                self.end_counter = self.end_counter + 1

        # Salir
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()
