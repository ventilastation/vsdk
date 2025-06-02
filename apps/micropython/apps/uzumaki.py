from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
import utime

lorem_ipsum = """Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."""

class Letter(Sprite):
    def __init__(self):
        super().__init__()
        self.disable()
        self.set_perspective(1)
        self.set_strip(stripes["vga_cp437.png"])
    
    def set_char(self, char, n):
        self.disable()
        self.set_x(-n * 9)
        self.set_y(int(n * 2))
        self.set_frame(ord(char))
        self.position = 200 + n * 9

    def step_out(self):
        self.position -= 1
        self.set_x(-(self.position - 64) % 256)
        self.set_y(int(self.position / 4))


class Uzumaki(Scene):
    stripes_rom = "other"
    phrase = lorem_ipsum

    def on_enter(self):
        super().on_enter()
        self.letters = []
        for n in range(90):
            letter = Letter()
            letter.set_char(self.phrase[n], n)
            self.letters.append(letter)

    def step(self):
        super().step()
        for l in self.letters:
            l.step_out()

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Uzumaki()