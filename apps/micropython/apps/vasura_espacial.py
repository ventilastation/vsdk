from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from apps.vasura_scripts.nave import Nave

class VasuraEspacial(Scene):
    stripes_rom = "vasura_espacial"

    def on_enter(self):
        super(VasuraEspacial, self).on_enter()
        self.nave = Nave(stripes["ship-sprite-sym.png"])
        self.planet = Sprite()
        self.planet.set_strip(stripes["game-center.png"])
        self.planet.set_perspective(0)
        self.planet.set_frame(0)
        self.planet.set_y(160)

    def step(self):
        self.nave.ArtificialStep()
        '''
        target = [0, 0]
        if (self.nave.X() == 0):
            target[1] = 6
        target[0] = 1
        self.nave.Move(*target)
        '''
        '''    
        self.nave.set_x(self.nave.x() + 1)
        if director.was_pressed(director.BUTTON_D):
            self.finished()
        if director.was_pressed(director.BUTTON_A):
            nub_x = self.nubareda.x
            nub_finx = self.nubareda.x + self.nubareda.width + 16
            if nub_x < self.nave.x() < nub_finx:
                director.sound_play(b"vyruss/shoot1")
            else:
                director.sound_play(b"vyruss/explosion3")
                director.music_play("vyruss/vy-gameover")
                self.finished()
            
        '''

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return VasuraEspacial()

'''
NUBES_POR_NUBAREDA = 8

def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(strip)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet

class Nubareda:
    def __init__(self):
        self.nubareda = [Sprite() for n in range(NUBES_POR_NUBAREDA)]
        for nube in self.nubareda:
            nube.set_strip(stripes["target.png"])
            nube.set_y(16)

        self.planet = make_me_a_planet(stripes["fondo.png"])
        self.planet.set_frame(0)

    def reiniciar(self):
        self.x = randrange(256 - 64)
        self.width = randrange(8, 64)
        step = self.width / NUBES_POR_NUBAREDA
        for n, nube in enumerate(self.nubareda):
            nube.set_x(int(self.x + step * n))
            nube.set_frame(1)
'''