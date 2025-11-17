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

class Torta50(Scene):
    stripes_rom = "torta50"

    def on_enter(self):
        super(Torta50, self).on_enter()
        self.alecu = Sprite()
        self.alecu.set_x(128-50)
        self.alecu.set_y(2)
        self.alecu.set_perspective(2)
        self.alecu.set_strip(stripes["alecu.png"])
        self.alecu.set_frame(0)

        self.corazones = Sprite()
        self.corazones.set_perspective(2)
        self.corazones.set_strip(stripes["corazones.png"])
        self.corazones.set_x(128-self.corazones.width()//2)
        self.corazones.set_y(27)
        self.corazones.set_frame(0)

        self.nave1 = Sprite()
        self.nave1.set_perspective(2)
        self.nave1.set_strip(stripes["ll9.png"])
        self.nave1.set_x(64-self.nave1.width()//2)
        self.nave1.set_y(5)
        self.nave1.set_frame(1)

        self.nave2 = Sprite()
        self.nave2.set_perspective(2)
        self.nave2.set_strip(stripes["ll9.png"])
        self.nave2.set_x(192-self.nave2.width()//2)
        self.nave2.set_y(5)
        self.nave2.set_frame(1)

        
        self.halfcent = Sprite()
        self.halfcent.set_x(0-50)
        self.halfcent.set_y(3)
        self.halfcent.set_perspective(2)
        self.halfcent.set_strip(stripes["halfcent.png"])
        self.halfcent.set_frame(0)

        self.fondo = make_me_a_planet(stripes["fondo.png"])
        self.fondo.set_frame(0)

    def step(self):
        
            
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Torta50()