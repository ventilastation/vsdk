from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

NUBES_POR_NUBAREDA = 8

class Nubareda:
    def __init__(self):
        self.planet = make_me_a_planet(stripes["ruleta.png"])
        self.planet.set_frame(0)

    def reiniciar(self):
        self.x = 0
        self.width = randrange(8, 64)

def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(strip)
    planet.set_perspective(0)
    planet.set_x(planet.x() + 5)
    planet.set_y(255)
    return planet

class Oraculo(Scene):
    stripes_rom = "oraculo"
    
    def on_enter(self):
        super(Oraculo, self).on_enter()
        self.ruleta = Sprite()
        self.ruleta.set_strip(stripes["ruleta.png"])
        self.ruleta.set_perspective(2)
        self.ruleta.set_x(0)
        self.ruleta.set_y(0)
        self.ruleta.set_frame(0)
        self.ruleta_pos = 0

    def step(self):
        self.ruleta_pos += 4
        self.ruleta.set_x(self.ruleta_pos // 8)

        if director.was_pressed(director.BUTTON_A):
            pass

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()

def main():
    return Oraculo()