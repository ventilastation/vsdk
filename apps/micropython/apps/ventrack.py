from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
import time

PISTAS = 16

def time_ms():
    return time.time_ns() // 1_000_000

def posRayita (step_ts, intervalo):
    now = time_ms()
    return (PISTAS * (now - step_ts)) // intervalo 
    

class Paso:
    def __init__(self, i):
        self.sprite = Sprite()
        s = self.sprite
        s.set_strip(stripes["tira_02.png"])
        s.set_x(i*16)
        s.set_perspective(2)
        s.set_y(0)
        s.set_frame(0)

        
    def sel(self,i):
        s = self.sprite
        s.set_frame(8-i)
   
class Cursor:
    gridx =1
    gridy =0
    
    def __init__(self):
        self.sprite = Sprite()
        s = self.sprite
        s.set_strip(stripes["c_04.png"])
        s.set_x(16)
        s.set_y(1)
        s.set_perspective(2)
        s.set_frame(0)

    def movX(self,dire):
       s=self.sprite
       #dire es +1 o -1
       self.gridx+=dire;
     
       if self.gridx < 0:
        self.gridx=15
       if self.gridx > 15:
        self.gridx = 0
       pos = self.gridx*16
       s.set_x(pos)
       print(pos)

    def movY(self,dire):
       s=self.sprite
       #dire es +1 o -1
       self.gridy+=dire;
     
       if self.gridy < 0:
        self.gridy=7
       if self.gridy > 7:
        self.gridy = 0
       pos = self.gridy*5
       s.set_y(pos)
       print(pos)

class Ventrack(Scene):
    stripes_rom = "ventrack"

    def on_enter(self):
        super().on_enter()

        
        self.raya = Sprite()
        self.raya.set_x(0)
        self.raya.set_y(27)
        self.raya.set_strip(stripes["laraya_02.png"])
        self.raya.set_frame(0)
        self.raya.set_perspective(2)
        
        self.sono = False
        self.contador_sonido = 0
        self.bpm = 15 
        ##un beat es una negra y lo dividimos en semicorcheas
        self.intervalo = 60000 // (self.bpm * 4) 
        self.step_actual = 0
        self.step_ts = time_ms() 
        self.call_later(self.intervalo, self.sonidito)
        
        self.cursor = Cursor()
        self.pasos = [Paso(i) for i in range(16)]

    def step(self):
        pos_rayita = posRayita(self.step_ts,self.intervalo)
        self.raya.set_x(self.step_actual *16 + pos_rayita)
        #print(self.step_actual*16, pos_rayita)
        
        if director.was_pressed(director.JOY_UP):
            self.cursor.movY(1)              
        if director.was_pressed(director.JOY_DOWN):
            self.cursor.movY(-1)
        if director.was_pressed(director.JOY_LEFT):
            self.cursor.movX(1)              
        if director.was_pressed(director.JOY_RIGHT):
            self.cursor.movX(-1)     
        if director.was_pressed(director.BUTTON_A):
            self.pasos[self.cursor.gridx].sel(self.cursor.gridy)
            

    def sonidito(self):
       ## director.sound_play(b"vyruss/shoot1")
        if self.contador_sonido < 4:
            director.sound_play(b"ventrack/1")
            self.contador_sonido +=1
        elif self.contador_sonido >= 4 and self.contador_sonido <8:
            director.sound_play(b"ventrack/1")
            director.sound_play(b"ventrack/2")
            self.contador_sonido +=1
        elif self.contador_sonido >= 8 and self.contador_sonido <12:
            director.sound_play(b"ventrack/1")
            director.sound_play(b"ventrack/2")
            director.sound_play(b"ventrack/3")
            self.contador_sonido +=1
        elif self.contador_sonido >= 12 and self.contador_sonido <16:
            director.sound_play(b"ventrack/1")
            director.sound_play(b"ventrack/2")
            director.sound_play(b"ventrack/3")
            director.sound_play(b"ventrack/4")
            self.contador_sonido +=1
        elif self.contador_sonido >= 16 and self.contador_sonido <20:
            director.sound_play(b"ventrack/1")
            director.sound_play(b"ventrack/2")
            director.sound_play(b"ventrack/3")
            director.sound_play(b"ventrack/4")
            director.sound_play(b"ventrack/5")
            self.contador_sonido +=1
        elif self.contador_sonido >= 20 and self.contador_sonido <24:
            director.sound_play(b"ventrack/1")
            director.sound_play(b"ventrack/2")
            director.sound_play(b"ventrack/3")
            director.sound_play(b"ventrack/4")
            director.sound_play(b"ventrack/5")
            director.sound_play(b"ventrack/6")
            self.contador_sonido +=1
        if self.contador_sonido >= 24:
            self.contador_sonido = 0
 
        self.step_ts = time_ms()
        print(self.step_actual)
        self.step_actual +=1 
        if self.step_actual>=16 : 
            self.step_actual = 0 

        self.sono = False
        self.call_later(1000,self.sonidito)


            
    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Ventrack()
