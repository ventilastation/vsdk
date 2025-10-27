from ventilastation.director import director, PIXELS, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from urandom import choice, randrange, seed

def make_me_a_planet(strip):
    planet = sprites.Sprite()
    planet.set_strip(stripes[strip])
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet

class Nivel01(Scene):
    stripes_rom = "vvv"
    bg = None
    p1_sprite = None
    p2_sprite = None
    p1_dir = -1
    p2_dir = 1
    contador = 0

    def on_enter(self):
        super(Nivel01, self).on_enter()

        self.p1_sprite = Sprite()
        self.p1_sprite.set_strip(stripes["vvv.png"])
        self.p1_sprite.set_x(0)
        self.p1_sprite.set_y(16)
        self.p1_sprite.set_frame(0)
        # 0: fullscreen: 320x320, centered, rotated
        # 1: perspective: tunnel, achata
        # 2: non-perspective: deform squash-stretch
        self.p1_sprite.set_perspective(1)

        self.p2_sprite = Sprite()
        self.p2_sprite.set_strip(stripes["vvv.png"])
        self.p2_sprite.set_x(0)
        self.p2_sprite.set_y(16)
        self.p2_sprite.set_frame(0)
        # 0: keep aspect, downscale
        # 1: achata?
        # 2: deform
        self.p2_sprite.set_perspective(1)

        self.bg = Sprite()
        self.bg.set_strip(stripes["full.png"])
        self.bg.set_x(0)
        self.bg.set_y(255)
        self.bg.set_frame(0)
        self.bg.set_perspective(0)

    def step(self):
        # is_pressed
        # was_pressed
        # was_released
        # self.coso.disable()
        # self.coso.set_x(self.coso.x() + 5)

        # dx = director.is_pressed(director.JOY_LEFT) - director.is_pressed(director.JOY_RIGHT)
        if director.was_pressed(director.BUTTON_A):
            self.p1_dir *= -1
        if director.was_pressed(director.BUTTON_B):
            self.p2_dir *= -1
        p1_dx = self.p1_dir * 3
        p2_dx = self.p2_dir * 3
        dy = director.is_pressed(director.JOY_UP) - director.is_pressed(director.JOY_DOWN)

        if p1_dx:
            self.p1_sprite.set_x((self.p1_sprite.x() + p1_dx) % 256)
        if p2_dx:
            self.p2_sprite.set_x((self.p2_sprite.x() + p2_dx) % 256)
        if dy:
            # self.p1_sprite.set_y((self.p1_sprite.y() + dy) % PIXELS)
            self.p1_sprite.set_y((self.p1_sprite.y() + dy) % 256)

        # if director.was_pressed(director.BUTTON_A):
        #     self.contador = (self.contador + 1) % 3
        #     self.coso.set_perspective(self.contador)
            # self.coso.disable()

        # print(self.coso.x())

        if director.was_pressed(director.BUTTON_D): # or director.timedout:
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()
