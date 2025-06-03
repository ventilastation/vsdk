from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
import time
import json
from itertools import zip_longest

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

class Instrument:
    sound_bank: str
    kind: str # L, B, D 
    patterns: list[list[int]]
    
    def __init__(self, sound_bank, kind, patterns=None):
        self.sound_bank = sound_bank
        self.kind = kind
        self.patterns = patterns if patterns else [ [0]*16 ] * 16
    
    def __iter__(self):
        for pattern in self.patterns:
            for note in pattern:
                if note:
                    yield f"{self.sound_bank}{self.kind}{note:02d}"
                    # x ej: AL09
                else:
                    # do not play anything for note 0
                    yield ""
    

class Sonidito:
    instruments: list[Instrument]
    interval: int   # between steps, in milliseconds
    n_step: int = 0     # step number for the rayita.
    step_ts: int    # Timestamp of the last step, in ms from the epoch
    
    def __init__(self, scene, interval, n_step=0):
        self.scene = scene
        self.interval = interval
        self.n_step = n_step

        self.instruments = [] # There must be at least one instrument
        self.sounds_iterable = self.loop()
        
        self.callback()
    
    def loop(self):
        while True:
            for step in zip_longest(*self.instruments, [None]):
                self.n_step = (self.n_step + 1) % 16
                for sound in step: #step will be a list of sounds
                    if sound:
                        director.sound_play("ventrack/"+sound)
                yield
    
    def callback(self):
        self.scene.call_later(self.interval, self.callback)
        self.step_ts = time_ms()
        
        next(self.sounds_iterable) #makes sound for this step
    
    def to_json(self):
        """
        {
            "interval": 150
            "patterns": [
                [ 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3, 4],
                # 0 o null es silencio
                [ … ]
            ],
            "instruments": [
                {
                    "sound_bank": "A",
                    "kind": "L" #lead
                    "patterns": [ 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0 ],
                },
                {
                    "sound_bank": "A",
                    "kind": "B", #bass
                    "pattern": [ 0, None, 0, None, 0, None, 0, None, 0, None, 0, None, 0, None, 0, None, ],
                },
                {
                    "sound_bank": "A",
                    "kind": "D", #drums
                    "pattern": [ 1, 1, 1, 1, None, None, instrument…]
                }
            ]
        }
        """
        out_interval = self.interval
        
        out_patterns = {tuple(pattern) for instrument in self.instruments for pattern in instrument.patterns}
        out_patterns = list(out_patterns)
        
        out_instruments = [
            {
                'sound_bank': instrument.sound_bank,
                'kind': instrument.kind,
                'patterns': list(out_patterns.index(tuple(pattern)) for pattern in instrument.patterns)
            }
            for instrument in self.instruments
        ]
        
        return json.dumps({
                "interval": out_interval,
                "patterns": out_patterns,
                "instruments": out_instruments
        })
    

class MockDirector:
    sound_play = print
class MockScene:
    def call_later(self, *args, **kwargs):
        print(args, kwargs)
        #call callback manually later :P


def main():
    return Ventrack()
