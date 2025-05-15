from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from ventilastation import povdisplay

def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(strip)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet


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

class DebugMode(Scene):
    stripes_rom = "other"

    def on_enter(self):
        self.rpm_display = TextDisplay(char_height * 2 + 2)
        self.us_display = TextDisplay(char_height + 2)
        self.fps_display = TextDisplay(2)
        self.exponent = -1
        self.arxel_sprites = []
        for n in range(8):
            s = Sprite()
            s.set_strip(stripes["debug_arxels.png"])
            s.set_x(32*n)
            s.set_y(0)
            s.set_frame(0)
            s.set_perspective(2)
            self.arxel_sprites.append(s)

    def update_sprites(self):
        # apagamos todos
        for n in range(8):
            self.arxel_sprites[n].set_frame(0)

        x = self.exponent
        if x < 4:
            for n in range(2 ** (3-x)):
                self.arxel_sprites[n].set_frame(6)
        else:
            self.arxel_sprites[0].set_frame(9 - x)

    def step(self):
        last_turn_duration = povdisplay.last_turn_duration()

        if self.exponent == -1:
            line_one = ("%7d " + chr(230) + "s") % last_turn_duration
            line_two = "%.2f RPM" % (60000000 / last_turn_duration)
            line_three = "%.2f fps" % (1000000 / last_turn_duration * 2) # doubled due to two blades
        else:
            divisor = 2 ** self.exponent
            line_one = ("%7d " + chr(230) + "s") % last_turn_duration
            line_two = " /%d =" % divisor
            line_three = ("%7d " + chr(230) + "s") % (last_turn_duration / divisor)

        self.rpm_display.set_value(line_one[:display_len])
        self.us_display.set_value(line_two[:display_len])
        self.fps_display.set_value(line_three[:display_len])


        if director.was_pressed(director.BUTTON_D):
            self.finished()

        if director.was_pressed(director.BUTTON_A):
            self.exponent += 1
            if self.exponent > 8:
                self.exponent = 0
            self.update_sprites()

        if (director.is_pressed(director.JOY_DOWN)
            and director.is_pressed(director.JOY_LEFT)
            and director.is_pressed(director.JOY_RIGHT)
            and director.is_pressed(director.BUTTON_A) ):
            from apps.tutorial import Tutorial
            director.push(Tutorial())

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return DebugMode()