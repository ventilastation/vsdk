from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite


DAMERO_COLS = 8
DAMERO_ROWS = 12
TILE_WIDTH = 32
TILE_HEIGHT = 16
TUNNEL_START = 8;

COLS_CENTERS = [int(TILE_WIDTH * (c - DAMERO_COLS/2 + 0.5) ) for c in range(DAMERO_COLS)]

def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(strip)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet

class TvnelGame(Scene):
    stripes_rom = "tvnel"

    def on_enter(self):
        super(TvnelGame, self).on_enter()
        
        self.fondos = {}
        for x in range(DAMERO_COLS):
            for y in range(DAMERO_ROWS):
                sf = Sprite()
                self.fondos[(x,y)] = sf 
                sf.set_strip(stripes["moregrass.png"])
                sf.set_x(COLS_CENTERS[x] - TILE_WIDTH // 2)
                sf.set_y(y * (TILE_HEIGHT-1) - TUNNEL_START)
                print(sf.y())
                sf.set_perspective(1)
                sf.set_frame(randrange(3))
         
        self.planet = make_me_a_planet(stripes["fondo.png"])
        self.planet.set_frame(0)                     
        
    
    def animar_paisaje(self):
        for f in self.fondos.values():
            fy = f.y() 
            fx = f.x()
            if (fy > 0):
                f.set_y(fy-1)
                f.set_x(fx-1)
            else:
                f.set_y(DAMERO_ROWS * (TILE_HEIGHT-1) - TUNNEL_START)
                f.set_frame(randrange(3))

    def step(self):
        #self.y -= 1
        #self.planet.set_y(self.y)
        #print(self.y)
        
        self.animar_paisaje()
        
        #Quits the scene
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()

def main():
    return TvnelGame()