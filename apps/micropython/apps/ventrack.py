from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
import time
import json

#frop itertools
def repeat(object, times=None):
    # repeat(10, 3) → 10 10 10
    if times is None:
        while True:
            yield object
    else:
        for i in range(times):
            yield object
#from itertools
def zip_longest(*iterables, fillvalue=None):
    # zip_longest('ABCD', 'xy', fillvalue='-') → Ax By C- D-
    print("hola")
    iterators = list(map(iter, iterables))
    num_active = len(iterators)
    if not num_active:
        return

    while True:
        values = []
        for i, iterator in enumerate(iterators):
            try:
                value = next(iterator)
            except StopIteration:
                num_active -= 1
                if not num_active:
                    return
                iterators[i] = repeat(fillvalue)
                value = fillvalue
            values.append(value)
        yield tuple(values)

# constantes
PISTAS = 16

# globales
instrumento = 2
posicion = 0
posx = 0
bpm = 110
current_pattern = [ 0 ] * 17
idUtilizadas = [[0]*5 for _ in range(3)]
Idxinstrumento = [0]*3

def time_ms():
    return time.time_ns() // 1_000_000

def posRayita (step_ts, interval):
    now = time_ms()
    return (PISTAS * (now - step_ts)) // interval 
    
class Instrucciones:
    def __init__ (self, escena):
        self.sprite = Sprite()
        texto = self.sprite
        if escena == "main":
            texto.set_strip(stripes["menu.png"])
            texto.set_y(25)
            texto.set_x(171)
        if escena == "instrumento":
            texto.set_strip(stripes["menuInstrumento.png"])
            texto.set_y(40)
            texto.set_x(30)

        
        texto.set_perspective(2)
        texto.set_frame(0)

            
        
    
class PasoMain:
    def __init__(self, i, y, id=0):
       
        self.sprite = Sprite()
        s = self.sprite
       
        if y == 0:
            s.set_strip(stripes["pr_10.png"])
        elif y == 1:
            s.set_strip(stripes["pr_13.png"])
        elif y == 2:
            s.set_strip(stripes["pr_15.png"])

        s.set_x(i*16)
        s.set_perspective(2)
        s.set_y(5+y*5)
        s.set_frame(0)
        
    def sel(self,i):
        s = self.sprite
        s.set_frame(i)
        
class Paso:
    def __init__(self, i, note=0):
        global instrumento
        self.sprite = Sprite()
        s = self.sprite
        s.set_strip(stripes[f"tiles_0{instrumento+1}.png"])

        s.set_x(i*16)
        s.set_perspective(2)
        s.set_y(0)
        self.sel(note)

    def sel(self,note):
        if note == 0:
            frame = 0
        else:
            frame = 9-note
        self.note = note
        self.sprite.set_frame(frame)
       

       
class Cursor:
    gridx =1
    gridy =0
    
    def __init__(self):
        global instrumento
        self.sprite = Sprite()
        s = self.sprite
        s.set_strip(stripes["selector_05.png"])
        s.set_x(16)
        s.set_y(1)
        s.set_perspective(2)
        s.set_frame(instrumento)

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
       print(self.gridx)

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
       print(self.gridy)
       
class CursorMain:
    gridx =1
    gridy =0
    
    def __init__(self):
        global instrumento
        self.sprite = Sprite()
        s = self.sprite
        s.set_strip(stripes["selector_05.png"])
        s.set_x(16)
        s.set_y(5)
        s.set_perspective(2)
        s.set_frame(self.gridy)

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
     #  print(pos)

    def movY(self,dire):
       s=self.sprite
       #dire es +1 o -1
       self.gridy+=dire;
     
       if self.gridy < 0:
        self.gridy=2
       if self.gridy > 2:
        self.gridy = 0
       pos = 5+self.gridy*5
       s.set_frame(self.gridy)

       s.set_y(pos)
    #  print(pos)

class VentrackInstru(Scene):
    
    def on_enter(self):
        super().on_enter()

        global instrumento
        global bpm
        global current_pattern
        
        drums = Instrument("A", "K")
        
        if instrumento == 0:
            kind = "L"
        if instrumento == 1:
            kind = "B"
        if instrumento == 2:
            kind = "D"
        self.patronoriginal = current_pattern.copy()    
        ins = Instrument("A", kind, [current_pattern])
        self.sonidito = Sonidito(self, bpm, [ins])
        self.sonidito.start()
        self.raya = Sprite()
        self.raya.set_x(0)
        self.raya.set_y(0)
        self.raya.set_strip(stripes["laraya_02.png"])
        self.raya.set_frame(0)
        self.raya.set_perspective(2)
        
        self.cursor = Cursor()
        self.pasos = [Paso(i, step) for i, step in enumerate(current_pattern)]
        
        self.instrucciones = Instrucciones("instrumento")

    def step(self):
        global current_pattern
        global Idxinstrumento  
        
        pos_rayita = posRayita(self.sonidito.step_ts, self.sonidito.interval)
        self.raya.set_x(self.sonidito.n_step * 16 + pos_rayita)
        
        if director.was_pressed(director.JOY_UP):
            self.cursor.movY(1)              
        if director.was_pressed(director.JOY_DOWN):
            self.cursor.movY(-1)
        if director.was_pressed(director.JOY_LEFT):
            self.cursor.movX(1)              
        if director.was_pressed(director.JOY_RIGHT):
            self.cursor.movX(-1)     
        if director.was_pressed(director.BUTTON_A):
            note = self.cursor.gridy + 1
            if self.pasos[self.cursor.gridx].note == note:
                note = 0
            
            self.pasos[self.cursor.gridx].sel(note)
            current_pattern[self.cursor.gridx] = note
            
        if director.was_pressed(director.BUTTON_D):
            if current_pattern != self.patronoriginal:
                if Idxinstrumento[instrumento] < 5:  
                    print("nuevo patron creado")
                    Idxinstrumento[instrumento] += 1
                else:
                    Idxinstrumento[instrumento] = 1
                current_pattern[16] = Idxinstrumento[instrumento]
            director.pop()

    def finished(self):
        director.pop()
        raise StopIteration()

class Ventrack(Scene):
    stripes_rom = "ventrack"
    sonidito = None
    def on_enter(self):
        super().on_enter()
    
        print(current_pattern)
    
        self.raya = Sprite()
        self.raya.set_x(0)
        self.raya.set_y(0)
        self.raya.set_strip(stripes["laraya_02.png"])
        self.raya.set_frame(0)
        self.raya.set_perspective(2)
    
        if self.sonidito is None:
            self.sonidito = Sonidito(self, bpm)
            lead = Instrument("A", "L", [[0]*17 for _ in range(16)])
            bass = Instrument("A", "B", [[0]*17 for _ in range(16)])
            drums = Instrument("A", "D", [[0]*17 for _ in range(16)])
            self.sonidito.instruments = [lead, bass, drums]
            
        else:
            print(self.sonidito.instruments)
            
        self.sonidito.instruments[instrumento].patterns[posicion] = current_pattern
        self.sonidito.start()
        self.cursor = CursorMain()
        self.pasos = [PasoMain(i, j) for i in range(16) for j in range(3)]
        

        for i in range(16):
            for j in range(3):
                self.pasos[3*i + j].sel(self.sonidito.instruments[j].patterns[i][16])
    
        self.instrucciones = Instrucciones("main")


    def step(self):
        global instrumento
        global posicion
        global current_pattern
        
        pos_rayita = posRayita(self.sonidito.step_ts,self.sonidito.interval * 16)
        self.raya.set_x(self.sonidito.n_step + pos_rayita)
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
            instrumento = self.cursor.gridy
            posicion = self.cursor.gridx
            print(f"Intrumento: {instrumento}")
            print(f"pattern: {posicion}")
            current_pattern = self.sonidito.instruments[instrumento].patterns[posicion]
            print(f"current_pattern = {current_pattern}")
            director.push(VentrackInstru())
    
        if director.was_pressed(director.BUTTON_B):
            instrumento = self.cursor.gridy
            posicion = self.cursor.gridx
            print(f"Pattern Copiado: {instrumento}")
            # Copiar manualmente el pattern (asumiendo que es una lista)
            current_pattern = [step for step in self.sonidito.instruments[instrumento].patterns[posicion]]
    
        if director.was_pressed(director.BUTTON_C):
            instrumento = self.cursor.gridy
            posicion = self.cursor.gridx
            print(f"Pattern pegado: {instrumento}")
    # Pegar el pattern copiadoo
            self.sonidito.instruments[instrumento].patterns[posicion] = [step for step in current_pattern]
            self.pasos[3*posicion + instrumento].sel(self.sonidito.instruments[instrumento].patterns[posicion][16])
    
        if director.was_pressed(director.BUTTON_D):
            self.finished()

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
        self.patterns = patterns if patterns else [ [0]*17 ] * 16
    
    def __iter__(self):
        for pattern in self.patterns:
            for note in pattern[:16]:  # last element is the pattern id, not a note
                if note:
                    yield f"{self.sound_bank}{self.kind}{note:02d}"
                    # x ej: AL09
                else:
                    # do not play anything for note 0
                    yield ""
    
    def __repr__(self):
        return f"Instrument({self.sound_bank}, {self.kind}, {self.patterns})"
    

class Sonidito:
    instruments: list[Instrument]
    interval: int   # between steps, in milliseconds
    n_step: int = 0     # step number for the rayita.
    step_ts: int   # Timestamp of the last step, in ms from the epoch
    running: bool = False
    
    def __init__(self, scene, bpm, instruments = None):
        self.scene = scene
        self.step_ts = time_ms()
        self.n_step = 0

        ##un beat es una negra y lo dividimos en semicorcheas
        self.interval = 60000 // (bpm * 4)
        
        
        self.instruments = instruments if instruments else []
        self.sounds_iterable = self.loop()
        print(f"sonidito instruments {instruments}")
    
    def start(self):
        if self.running: return

        self.running = True
        self.callback()
        
    def stop(self):
        self.running = False
    
    def loop(self):
        while True:
            #print("sound loop started")
            print(self.instruments)
            for step in zip_longest(*self.instruments, [None]):
                #print(f"sound on step {step}")
                self.n_step = (self.n_step + 1) % (16*16)
                notes = []
                for note in step: #step will be a list of sounds
                    if note:
                        notes.append(note)
                        #print("playing {sound}")
                if notes:
                    director.notes_play("ventrack", notes)
                yield
    
    def callback(self):
        #print("callback")
        if not self.running: return
        #print("callback running")
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
