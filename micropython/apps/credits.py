from libs.director import director
from libs.scene import Scene
from libs.sprites import Sprite
from libs.imagenes import strips

SPEED = 4
TITLE_DELAYS = 3000
END_OF_TITLES = 583


def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(strip)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet


class Credits(Scene):

    def start_music(self):
        director.music_play("other/credits")

    def on_enter(self):
        self.vs = make_me_a_planet(strips.other.ventilastation)
        self.vs.set_frame(0)
        self.te = make_me_a_planet(strips.other.tecno_estructuras)
        self.sves = make_me_a_planet(strips.other.sves)
        self.counter = 0
        self.y = 0
        self.sprites = []
        for n in range(31, -1, -1):
            sprite = Sprite()
            sprite.set_x(256 - 32)
            sprite.set_y(0)
            sprite.set_strip(strips.other.credits)
            sprite.set_perspective(1)
            sprite.set_frame(n)
            self.sprites.append(sprite)
        self.sprites.reverse()
        self.call_later(TITLE_DELAYS, self.start_scrolling)
        self.scrolling = False
        self.call_later(100, self.start_music)

    def start_scrolling(self):
        self.vs.disable()
        self.scrolling = True

    def move(self, direction):
        self.y += direction
        if self.y < 0:
            self.y = 0
        if self.y > END_OF_TITLES:
            self.y = END_OF_TITLES


        for n, sprite in enumerate(self.sprites):
            this_y = self.y - n * 16
            if this_y >= 0 and this_y < 255:
                sprite.set_y(this_y)

        if self.y == END_OF_TITLES:
            self.scrolling = False
            self.te.set_frame(0)
            self.call_later(TITLE_DELAYS, self.end_credit)

    def step(self):
        self.counter = self.counter + 1

        if director.was_pressed(director.BUTTON_D):
            self.finished()

        if self.scrolling:
            if director.is_pressed(director.JOY_UP):
                self.move(1)
            elif director.is_pressed(director.JOY_DOWN):
                self.move(-1)
            elif self.counter % SPEED == 0:
                self.move(1)

    def end_credit(self):
        self.te.disable()
        self.sves.set_frame(0)
        self.call_later(TITLE_DELAYS, self.finished)

    def finished(self):
        director.pop()
        raise StopIteration()
