from ventilastation.director import director
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from ventilastation.imagenes import strips
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

class DebugMode(Scene):

    def on_enter(self):
        self.us_display = TextDisplay(char_height)
        self.fps_display = TextDisplay(0)
        self.rpm_display = TextDisplay(char_height * 2)

    def step(self):
        last_turn_duration = povdisplay.last_turn_duration()
        microseconds = ("%7d " + chr(230) + "s") % last_turn_duration
        self.us_display.set_value(microseconds[:display_len])
        fps = "%.2f fps" % (1000000 / last_turn_duration * 2) # doubled due to two blades
        self.fps_display.set_value(fps[:display_len])
        rpms = "%.2f RPM" % (60000000 / last_turn_duration)
        self.rpm_display.set_value(rpms[:display_len])

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()
