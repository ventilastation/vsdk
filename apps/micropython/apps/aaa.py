from urandom import choice, randrange, seed
from time import ticks_ms, ticks_diff
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite


display_len = 4
char_width = 9

class TextDisplay:
    def __init__(self, y):
        self.chars = []
        for n in range(display_len):
            s = Sprite()
            s.set_strip(stripes["rainbow437.png"])
            s.set_x((256 - n * char_width + (display_len // 2 * char_width) // 2) % 256)
            s.set_y(y)
            s.set_frame(10)
            s.set_perspective(2)
            self.chars.append(s)

        self.set_value("")

    def set_value(self, value):
        for n in range(len(self.chars)):
            self.chars[n].set_frame(0)
        for n, l in enumerate(value):
            v = ord(l)# - 0x30
            self.chars[n].set_frame(v)

#  TODO (como terminar el juego)
# ===============================
# - Sonido 
# - Musica con mix gradual por nivel

MAX_BARRAS = 11

class MySprite(Sprite):
    pass

def gen_sprite(name, x=0):
    s = MySprite()
    s.set_strip(stripes[name])
    s.set_frame(0)
    s.set_x(0)
    s.set_y(250) # ready to launch
    s.drift = 0
    return s

class AAA(Scene):
    stripes_rom = "aaa"

    def on_enter(self):
        super(AAA, self).on_enter()
        self.barras = []
        for a in range(0, MAX_BARRAS):
            self.barras.append(gen_sprite("barra.png"))
        self.punto = gen_sprite("punto.png")
        self.punto.set_x(251)
        self.punto.set_y(11)
        self.launch = {
            "total": 0,
            "last": 0,
            "freq": 2000
        }
        self.y_speed = 3
        self.x_center = 0
        self.unlucky = 1
        self.dead = 0

    def adjust_diff(self):
        if self.launch['freq'] > 420:
            self.launch['freq'] -= 42
        if self.launch['total'] > 100:
            self.unlucky = 2
        if self.launch['total'] > 200:
            self.y_speed = 4
        if self.launch['total'] > 300:
            self.launch['freq'] = 300

    def check_launcher(self):
        now = ticks_ms()
        if ticks_diff(now, self.launch['last']) > self.launch['freq']:
            for a in range(0, len(self.barras)):
                if self.barras[a].y() == 250:
                    self.barras[a].og_x = randrange(0,208)
                    self.barras[a].drift = 0
                    # target
                    if randrange(0, 13) <= self.unlucky:
                        self.barras[a].og_x = 251 - self.x_center
                    # drift
                    if randrange(0, 17) <= self.unlucky:
                        self.barras[a].drift = randrange(-2,3)
                    # launch
                    self.barras[a].set_y(249)
                    self.launch['total'] += 1
                    self.launch['last'] = now
                    # quit?
                    if randrange(0,23) > self.unlucky:
                        break

    def step(self):
        if director.was_pressed(director.BUTTON_D) or (self.dead > 0 and ticks_diff(ticks_ms(), self.dead) > 9000):
            self.finished()

        if self.dead == 0:
            if director.is_pressed(director.JOY_LEFT):
                self.x_center -= self.y_speed
            if director.is_pressed(director.JOY_RIGHT):
                self.x_center += self.y_speed

            if self.punto.collision(self.barras):
                self.dead = ticks_ms()
                self.unlucky = 20
                self.launch['freq'] = 1
                self.score = self.launch['total']
                self.score_display = TextDisplay(17)
                self.score_display.set_value(str(self.score))


        self.check_launcher()

        for barra in filter(lambda b: b.y() < 250, self.barras):
            cy = barra.y()
            cy -= self.y_speed
            if cy < 8:
                if self.dead == 0:
                    cy = 250
                    self.adjust_diff()
                else:
                    cy = 11
            barra.set_y(cy)
            barra.og_x += barra.drift
            barra.set_x(barra.og_x + self.x_center)


    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return AAA()
