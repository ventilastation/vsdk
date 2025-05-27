from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite



def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(strip)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet

def make_me_a_nube(x,y):
        """nube = Sprite()
        nube.set_strip(strip)"""
        target=Sprite()
        target.set_strip(stripes["target.png"])
        target.set_x(x)
        target.set_y(y)
        target.set_frame(6)
       ## print("en meikmianube")
        return target

   

  
class Mijuegui(Scene):
    stripes_rom = "mijuegui"
    

   

    def on_enter(self):
        super(Mijuegui, self).on_enter()
        self.bola = Sprite()
        self.bola.set_x(0)
        self.bola.set_y(16)
        self.bola.set_strip(stripes["bola.png"])
        self.bola.set_frame(6)
        self.sono = False
        self.contador_sonido = 0

    

    def step(self):
        
        if(self.sono == False):
            self.sono = True
            self.call_later(1000,self.sonidito)

        if director.is_pressed(director.JOY_RIGHT):
            self.bola.set_x(self.bola.x() + 1)
            
        if director.is_pressed(director.JOY_LEFT):
            self.bola.set_x(self.bola.x() - 1)
                       


        if director.was_pressed(director.BUTTON_A):
            self.target = make_me_a_nube(self.bola.x(),self.bola.y())
            print(self.bola.x())
            ##director.sound_play(b"vyruss/shoot1")
              
            
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def sonidito(self):
       ## director.sound_play(b"vyruss/shoot1")
        if self.contador_sonido < 4:
            director.sound_play(b"mijuegui/1")
            self.contador_sonido +=1
        elif self.contador_sonido >= 4 and self.contador_sonido <8:
            director.sound_play(b"mijuegui/1")
            director.sound_play(b"mijuegui/2")
            self.contador_sonido +=1
        elif self.contador_sonido >= 8 and self.contador_sonido <12:
            director.sound_play(b"mijuegui/1")
            director.sound_play(b"mijuegui/2")
            director.sound_play(b"mijuegui/3")
            self.contador_sonido +=1
        elif self.contador_sonido >= 12 and self.contador_sonido <16:
            director.sound_play(b"mijuegui/1")
            director.sound_play(b"mijuegui/2")
            director.sound_play(b"mijuegui/3")
            director.sound_play(b"mijuegui/4")
            self.contador_sonido +=1
        elif self.contador_sonido >= 16 and self.contador_sonido <20:
            director.sound_play(b"mijuegui/1")
            director.sound_play(b"mijuegui/2")
            director.sound_play(b"mijuegui/3")
            director.sound_play(b"mijuegui/4")
            director.sound_play(b"mijuegui/5")
            self.contador_sonido +=1
        elif self.contador_sonido >= 20 and self.contador_sonido <24:
            director.sound_play(b"mijuegui/1")
            director.sound_play(b"mijuegui/2")
            director.sound_play(b"mijuegui/3")
            director.sound_play(b"mijuegui/4")
            director.sound_play(b"mijuegui/5")
            director.sound_play(b"mijuegui/6")
            self.contador_sonido +=1
        if self.contador_sonido >= 24:
            self.contador_sonido = 0
 

        self.sono = False

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Mijuegui()