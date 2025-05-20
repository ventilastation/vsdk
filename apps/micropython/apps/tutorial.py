from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from ventilastation import povdisplay


char_width = 9
char_height = 12
display_len = 12

class TextDisplay:
    def __init__(self, y):
        self.chars = []
        for n in range(display_len):
            s = Sprite()
            s.set_strip(stripes["rainbow437.png"])
            s.set_x((256 -n * char_width + (display_len * char_width) // 2) % 256)
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

class Tutorial(Scene):
    stripes_rom = "other"

    def on_enter(self):
        super(Tutorial, self).on_enter()
        self.display = TextDisplay(0)
        self.display.set_value("Tutorial!")

        self.planeta = Sprite()
        self.planeta.set_strip(stripes["bembi.png"])
        self.planeta.set_perspective(0)
        self.planeta.set_x(0)
        self.planeta.set_y(255)
        #self.planeta.set_frame(0)
        #self.planeta.name = "Planeta"   # does not work on the sprite C module

        self.doom = Sprite()
        self.doom.set_strip(stripes["doom.png"])
        self.doom.set_perspective(0)
        self.doom.set_x(0)
        self.doom.set_y(255)
        #self.planeta.set_frame(0)
        #self.planeta.name = "Planeta"   # does not work on the sprite C module

        self.bicho = Sprite()
        self.bicho.set_strip(stripes["galaga.png"])
        self.bicho.set_perspective(1)
        self.bicho.set_x(-32)
        self.bicho.set_y(16)
        #self.bicho.set_frame(6)
        #self.bicho.name = "Bicho"

        self.cartel = Sprite()
        self.cartel.set_strip(stripes["gameover.png"])
        self.cartel.set_perspective(2)
        self.cartel.set_x(256-32)
        self.cartel.set_y(16)
        #self.cartel.set_frame(0)
        #self.cartel.name = "Cartel"

        self.sprites = [self.planeta, self.bicho, self.cartel, self.doom]

        self.current = 0
        self.sprite = self.sprites[self.current]
        self.activate_next()

    def activate_next(self):
        self.current = (self.current + 1) % (len(self.sprites) - 1)
        self.activate(self.current)

    def activate(self, new_active):
        self.sprite = self.sprites[new_active]
        for n, s in enumerate(self.sprites):
            if n == new_active:
                s.set_frame(6 if self.sprite == self.bicho else 0)
            else:
                s.disable()

    def activate_doom(self):
        self.display.set_value("")
        self.current = len(self.sprites) - 1
        self.activate(self.current)

    def step(self):

        if director.was_pressed(director.BUTTON_D):
            self.finished()

        if director.was_pressed(director.BUTTON_A):
            self.activate_next()
            self.display.set_value("Persp: %d" % self.sprite.perspective())

        # SKIP movement if DOOM
        if self.current == len(self.sprites) - 1:
            return
            
        # Y
        up = director.is_pressed(director.JOY_UP)
        down = director.is_pressed(director.JOY_DOWN)

        if up or down:
            new_y = self.sprite.y() - down + up
            self.sprite.set_y(new_y)
            self.display.set_value("Y = %d" % self.sprite.y())

        # X

        left = director.is_pressed(director.JOY_LEFT)
        right = director.is_pressed(director.JOY_RIGHT)

        if left or right:
            new_x = self.sprite.x() + left - right
            self.sprite.set_x(new_x)
            self.display.set_value("X = %d" % self.sprite.x())

        # frame

        back = director.was_pressed(director.BUTTON_B)
        forth = director.was_pressed(director.BUTTON_C)

        if back or forth:
            new_frame = self.sprite.frame() - back + forth
            self.sprite.set_frame(new_frame)
            self.display.set_value("frame = %d" % self.sprite.frame())


        if up and down and left and right:
            self.activate_doom()


    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Tutorial()