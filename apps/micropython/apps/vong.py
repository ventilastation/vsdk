from random import choice, randrange, seed
import utime
import gc

from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite, reset_sprites
from ventilastation.imagenes import strips

#    """
#       128
#    96↖ ↑ ↗ 160
#    64←    → 192
#    32↙ ↓ ↘ 224
#        0
#    """
class Barra:
    def __init__(self,x,y):
        self.sprite = Sprite()
        self.sprite.set_x(x)
        self.sprite.set_y(y)
        self.sprite.set_perspective(1)
        self.sprite.set_strip(stripes["barra.png"])
        self.sprite.set_frame(0)
        

class Pelota:
    def __init__(self,x,y,speed):
        self.sprite = Sprite()
        self.sprite.set_x(x)
        self.sprite.set_y(y)
        self.sprite.set_perspective(1)
        self.sprite.set_strip(stripes["ball.png"])
        self.sprite.set_frame(0) 

        self.speed = speed
        self.speed_y = 0
        self.drag = 0.85
        self.techo_rebote = 1

        self.dir = 0
    def step(self):
        self.sprite.set_x(self.sprite.x() + self.speed*self.dir)
        self.sprite.set_y(self.sprite.y() + int(self.speed_y) * self.techo_rebote)
        if self.sprite.y() <= 10:
            self.techo_rebote = self.techo_rebote * -1
            self.sprite.set_y(31)
        if self.sprite.y() >= 100:
            self.techo_rebote = self.techo_rebote * -1
            self.sprite.set_y(99)

        if self.speed_y > 0 or self.speed_y < 0:
            if self.speed_y > 0:
                self.speed_y *= self.drag
            elif self.speed_y < 0:
                self.speed_y *= self.drag
            
        
        

class BarraPunto:
    def __init__(self,x,y):
        self.sprite = Sprite()
        self.sprite.set_x(x)
        self.sprite.set_y(y)
        self.sprite.set_perspective(1)
        self.sprite.set_strip(stripes["barra_punto.png"])
        self.sprite.set_frame(0) 

class VongGame(Scene):
    stripes_rom = "vong"

    def __init__(self):
        super(VongGame, self).__init__()
        seed(utime.ticks_ms())
        self.puntos = [0, 0]

    def on_enter(self):
        super(VongGame, self).on_enter()
        self.pelota = Pelota(30,30,3)
        self.player1 = Barra(254,20)
        self.player2 = Barra(126,20)
        self.barra_punto = BarraPunto(192, 0,)
        
    def step(self):
        self.pelota.step()
        self.process_input()
        rebote = self.pelota.sprite.collision([self.player1.sprite,self.player2.sprite])
        if rebote:
            self.rebote_y(rebote)
            self.pelota.dir = self.pelota.dir * -1
        accion_punto = self.pelota.sprite.collision([self.barra_punto.sprite])
        if accion_punto:
            self.barra_punto.sprite.set_x(self.barra_punto.sprite.x()+128)
            if self.pelota.dir == 1:
                self.puntos[0] += 1
            else:
                self.puntos[1] += 1         
            # print(self.puntos)       
            

    def process_input(self):
        speed = 3
        
        #Player 1
        player1_up = director.is_pressed(director.JOY_LEFT)
        player1_down = director.is_pressed(director.JOY_DOWN)

        if(player1_up and self.player1.sprite.y() > 10):
            self.player1.sprite.set_y(self.player1.sprite.y()-speed)
        elif(player1_down and self.player1.sprite.y() < 80):
            self.player1.sprite.set_y(self.player1.sprite.y()+speed)
            
        #Player 2
        player2_up = director.is_pressed(director.JOY_UP)
        player2_down = director.is_pressed(director.JOY_RIGHT)

        if(player2_up and self.player2.sprite.y() < 80):
            self.player2.sprite.set_y(self.player2.sprite.y()+speed)
        elif(player2_down and self.player2.sprite.y() > 10):
            self.player2.sprite.set_y(self.player2.sprite.y()-speed)

        if self.pelota.dir == 0:
            if player1_down and player2_up:
                self.pelota.dir = 1

        if director.was_pressed(director.BUTTON_D) or director.timedout:
            director.pop()
            raise StopIteration()


    def rebote_y(self, barra):
        if barra == self.player1.sprite:
            diferencia = (barra.y() - self.pelota.sprite.y() + 4) * -1
        if barra == self.player2.sprite:
            diferencia = (barra.y() - self.pelota.sprite.y() + 4) * -1
        # print(diferencia)
        self.pelota.speed_y += diferencia / 2


def main():
    return VongGame()