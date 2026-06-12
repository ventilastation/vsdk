from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from ventilastation import povdisplay, settings

def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(strip)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet


char_width = 4
char_height = 6
display_len = 18

class TextDisplay:
    def __init__(self, y):
        self.chars = []
        for n in range(display_len):
            s = Sprite()
            s.set_strip(stripes["tinyfont_white.png"])
            s.set_x((192 - n * char_width + (display_len * char_width) // 2) % 256)
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

    def set_strip(self, strip):
        for c in self.chars:
            c.set_strip(strip)


class ColumnOffsetSetting(Scene):
    stripes_rom = "other"

    def on_enter(self):
        super(ColumnOffsetSetting, self).on_enter()
        print('on_enter Settings')
        self.settings_display = TextDisplay(2)
        self.update_display()
        self.grid = make_me_a_planet(stripes["rotationgrid.png"])
        self.grid.set_frame(0)
        self.doom = make_me_a_planet(stripes["doom.png"])

    def update_display(self):
        column_offset = povdisplay.get_column_offset()
        self.settings_display.set_value("col off = %d" % column_offset)

    def step(self):

        if director.was_pressed(director.BUTTON_D):
            self.finished()

        left = director.was_pressed(director.JOY_LEFT)
        right = director.was_pressed(director.JOY_RIGHT)

        if left or right:
            povdisplay.set_column_offset(povdisplay.get_column_offset() - left + right)
            new_column_offset = povdisplay.get_column_offset()
            settings.set("pov_column_offset", new_column_offset)
            self.update_display()

        if director.was_pressed(director.BUTTON_A):
            if self.doom.frame() == 0:
                self.doom.disable()
                self.grid.set_frame(0)
            else:
                self.grid.disable()
                self.doom.set_frame(0)

    def finished(self):
        settings.save()
        director.pop()
        raise StopIteration()


def main():
    return ColumnOffsetSetting()