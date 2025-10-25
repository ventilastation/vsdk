from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

def animate(sp):
    sp.set_frame(sp.init_frame + (sp.frame() - sp.init_frame + 1) % sp.frames)


def peron():
    sp = Sprite()
    sp.set_strip(stripes["peron.png"])
    sp.set_perspective(0)
    sp.set_x(0)
    sp.set_y(255)
    sp.set_frame(0)
    return sp

def bicho_sprite():
    sp = Sprite()
    sp.set_strip(stripes["mano.png"])
    sp.set_frame(1)
    sp.set_perspective(1)
    sp.set_x(0)
    sp.set_y(20)

    sp.init_frame = 6
    sp.frames = 2

    return sp


def cosito():
    sp = Sprite()
    sp.set_strip(stripes["bola.png"])
    sp.set_frame(5)
    sp.set_perspective(1)
    sp.set_x(0)
    sp.set_y(255)

    sp.init_frame = 6
    sp.frames = 2

    return sp

class GameOver(Scene):

    def on_enter(self):
        pass
    
    def finished(self):
        director.pop()


class PeronJam(Scene):
    stripes_rom = "peronjam"

    def on_enter(self):
        super(PeronJam, self).on_enter()

        self.cosito = cosito()

        self.manod = bicho_sprite()
        self.manod.set_x(64)
        self.manod.set_frame(2)
        self.manoi = bicho_sprite()
        self.manoi.set_x(192-32)

        self.peron = peron()

        self.score = 0
        self.vidas = 3

    def step(self):
        
        dx = director.is_pressed(director.JOY_LEFT) - director.is_pressed(director.JOY_RIGHT)
        dy = director.is_pressed(director.JOY_UP) - director.is_pressed(director.JOY_DOWN)
        
        self.manoi.set_x(self.manoi.x() - dy * 8)
        self.manod.set_x(self.manod.x() + dy * 8)

        self.manoi.set_y(self.manoi.y() + dx * 8)
        self.manod.set_y(self.manod.y() + dx * 8)


        if self.cosito.y() > 250:
            self.cosito.set_x(randrange(255))

        self.cosito.set_y(self.cosito.y() - 5)

        if self.cosito.collision([self.manoi,self.manod]):
            self.score += 1
            print("Viva Perón! ", self.score)
            self.cosito.set_y(0)
            return
        
        if self.cosito.y() < 5:
            self.vidas -= 1
            print("Se te escapó la tortuga ", self.vidas)
            if self.vidas <= 0:
                self.finished()


        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return PeronJam()