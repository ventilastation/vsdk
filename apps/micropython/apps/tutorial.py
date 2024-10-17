from ventilastation.director import director
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from ventilastation.imagenes import strips
from ventilastation import povdisplay


char_width = 9
char_height = 12
display_len = 12

class TextDisplay:
    def __init__(self, y):
        self.chars = []
        for n in range(display_len):
            s = Sprite()
            s.set_strip(strips.vladfarty.rainbow437)
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

    def on_enter(self):
        self.display = TextDisplay(0)
        self.display.set_value("Tutorial!")

        self.planeta = Sprite()
        self.planeta.set_strip(strips.other.bembi)
        self.planeta.set_perspective(0)
        self.planeta.set_x(0)
        self.planeta.set_y(255)
        #self.planeta.set_frame(0)
        #self.planeta.name = "Planeta"   # does not work on the sprite C module

        self.bicho = Sprite()
        self.bicho.set_strip(strips.vyruss.galaga)
        self.bicho.set_perspective(1)
        self.bicho.set_x(-32)
        self.bicho.set_y(16)
        #self.bicho.set_frame(6)
        #self.bicho.name = "Bicho"

        self.cartel = Sprite()
        self.cartel.set_strip(strips.vyruss.gameover)
        self.cartel.set_perspective(2)
        self.cartel.set_x(256-32)
        self.cartel.set_y(16)
        #self.cartel.set_frame(0)
        #self.cartel.name = "Cartel"

        self.sprites = [self.planeta, self.bicho, self.cartel]

        self.current = 0
        self.sprite = self.sprites[self.current]
        self.activate_next()

    def activate_next(self):
        self.current = (self.current + 1) % len(self.sprites)
        self.sprite = self.sprites[self.current]
        for n, s in enumerate(self.sprites):
            if n == self.current:
                s.set_frame(6 if self.sprite == self.bicho else 0)
            else:
                s.disable()

    def step(self):

        if director.was_pressed(director.BUTTON_A):
            self.activate_next()
            self.display.set_value("Persp: %d" % self.sprite.perspective())
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

        if director.was_pressed(director.BUTTON_D):
            self.finished()


    def finished(self):
        director.pop()
        raise StopIteration()
