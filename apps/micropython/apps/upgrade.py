from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from ventilastation import povdisplay
from ventilastation.sync import sync_with_server, SYNC_HOST, PORT

def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(strip)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet


char_width = 4
char_height = 6
display_len = 48

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


def sync_with_server_test(host, port):
    import utime
    for n in range(10):
        print(f"yielding sample filename {n}.txt")
        yield f"sample/filename{n}.txt", n % 2 == 0
        utime.sleep_ms(500)
        yield None, None
        utime.sleep_ms(100)

class Upgrade(Scene):
    stripes_rom = "other"

    def on_enter(self):
        super(Upgrade, self).on_enter()
        print('on_enter Upgrade')
        self.filename_display = TextDisplay(2)
        self.upgrade_iterator = sync_with_server(SYNC_HOST, PORT)

    def step(self):
        print("step Upgrade")
        try:
            filename, writing = next(self.upgrade_iterator)
            print("Syncing file:", filename)
            if filename:
                filename = filename.split('/')[-1]
            else:
                filename = f""
            if writing:
                self.filename_display.set_strip(stripes["tinyfont_red.png"])
            else:
                self.filename_display.set_strip(stripes["tinyfont_white.png"])
            self.filename_display.set_value(filename[:display_len])
        except StopIteration:
            self.finished()
            return

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Upgrade()