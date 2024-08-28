from urandom import choice, randrange, seed
from libs.director import director
from libs.scene import Scene
from libs.sprites import Sprite
from libs.imagenes import strips

NUBES_POR_NUBAREDA = 8

class Nubareda:

    def __init__(self):
        self.nubareda = [Sprite() for n in range(NUBES_POR_NUBAREDA)]
        for nube in self.nubareda:
            nube.set_strip(strips.vyruss.explosion)
            nube.set_y(16)

    def reiniciar(self):
        self.x = randrange(256 - 64)
        self.width = randrange(8, 64)
        step = self.width / NUBES_POR_NUBAREDA
        for n, nube in enumerate(self.nubareda):
            nube.set_x(int(self.x + step * n))
            nube.set_frame(1)

def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(strip)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(0)
    return planet

class Ventap(Scene):

    def on_enter(self):
        self.bola = Sprite()
        self.bola.set_x(0)
        self.bola.set_y(16)
        self.bola.set_strip(strips.vyruss.galaga)
        self.bola.set_frame(6)

        self.nubareda = Nubareda()
        self.nubareda.reiniciar()

    def step(self):
        self.bola.set_x(self.bola.x() + 3)

        if director.was_pressed(director.BUTTON_A):
            nub_x = self.nubareda.x
            nub_finx = self.nubareda.x + self.nubareda.width + 16
            if nub_x < self.bola.x() < nub_finx:
                director.sound_play(b"vyruss/shoot1")
                self.nubareda.reiniciar()
            else:
                director.sound_play(b"vyruss/explosion3")
                director.music_play("vyruss/vy-gameover")
                self.finished()
            
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()
