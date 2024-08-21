import utime
from director import director
from scene import Scene
from sprites import Sprite, reset_sprites
from urandom import randrange

credits = """
[TBD Group]
alecu
krakatoa
mer
chame

y amigos:
Club de Jaqueo
Python Arg
Tecnoestructuras
Videogamo
Cybercirujas
PVM
Flashparty
""".strip().split("\n")


RESET_SPEED = 2

def make_me_a_planet(n):
    planet = Sprite()
    planet.set_strip(n)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(0)
    return planet


class Letter(Sprite):
  strip = 20
  def __init__(self):
    super().__init__()
    self.set_strip(self.strip)
    self.set_frame(0)
    self.set_perspective(1)
    self.delta = 0

  def set_char(self, char):
    self.set_frame(ord(char))
    self.enabled = True
    self.set_x(256-64-16)
    self.set_y(0)

  def hide(self):
    self.disable()

  def step(self, n):
    x = self.x()
    self.set_x(x + 1)
    y = self.y()
    #expected = vibratto[x % tablelen] - 4
    expected = vibratto[n % tablelen] - 4
    if 100 < x < 140:
        y -= 1
    elif y < expected:
        y += 1
    else:
        y = expected
    self.set_y(y)

  def done(self):
    return 128 < self.x() < 140


class RainbowLetter(Letter):
  strip = 29

#sinetable = list(range(16,32,1)) + list(range(32,16,-1))
#sinetable = [24, 26, 27, 28, 30, 31, 31, 32, 32, 32, 31, 31, 30, 28, 27, 26, 24, 22, 21, 20, 18, 17, 17, 16, 16, 16, 17, 17, 18, 20, 21, 22]
vibratto = [20, 20, 20, 20, 20, 21, 21, 22, 22, 23, 24, 25, 26, 26, 27, 27, 28, 28, 28, 28, 28, 27, 27, 26, 26, 25, 24, 23, 22, 22, 21, 21]




tablelen = len(vibratto)


class VladFarty(Scene):
    def __init__(self):
        super().__init__()
        self.farty_step = 0

    def on_enter(self):
        if not director.was_pressed(director.BUTTON_D):
            self.next_scene()
        else:
            director.pop()
            raise StopIteration()

    def step(self):
        if director.was_pressed(director.BUTTON_D):
            director.pop()
            raise StopIteration()

    def next_scene(self):
        new_scene_class = scenes[self.farty_step]
        if new_scene_class:
            director.push(new_scene_class())
            self.farty_step += 1
        else:
            director.pop()
            raise StopIteration()

class TimedScene(Scene):
    keep_music = True

    def __init__(self):
        super().__init__()
        self.scene_start = utime.ticks_ms()
        if self.duration:
            print("Scene starting: ", self.__class__.__name__,
              " starts (ms): ", self.scene_start,
              " will end: ", utime.ticks_add(self.scene_start, self.duration))
            self.call_later(self.duration, self.finish_scene)

    def on_exit(self):
        print("Scene finished: ", self.__class__.__name__,
              " duration (ms): ", utime.ticks_diff(utime.ticks_ms(), self.scene_start),
              " current time: ", utime.ticks_ms())

    def scene_step(self):
        super().scene_step()
        left = director.is_pressed(director.JOY_LEFT)
        right = director.is_pressed(director.JOY_RIGHT)
        if director.was_pressed(director.BUTTON_A) and left and right:
            director.pop()
        if director.was_pressed(director.BUTTON_D):
            director.pop()
            raise StopIteration()

    def finish_scene(self):
        print("Later called to finish scene, current time: ", utime.ticks_ms())
        director.pop()


class Ready(TimedScene):
    duration = 6000

    def on_enter(self):
        self.ready = Sprite()
        self.ready.set_strip(23)
        self.ready.set_perspective(2)
        self.ready.set_x(256-24)
        self.ready.set_y(8)

        self.cursor = Sprite()
        self.cursor.set_strip(23)
        self.cursor.set_perspective(2)
        self.cursor.set_x(256-22)
        self.cursor.set_y(0)
        self.cursor_show = True

        self.background = make_me_a_planet(24)
        self.background.set_y(255)

        self.background.set_frame(0)
        self.ready.set_frame(0)
        self.cursor.set_frame(1)

        self.scrolling = False
        self.hiding = False

        self.blink()
        self.call_later(2000, self.start_scrolling)
        self.call_later(4000, self.start_hiding)
        director.music_play(b"demo/vladfarty/intro")

    def start_scrolling(self):
        self.scrolling = True
        self.ready.set_perspective(1)
        self.ready.set_y(26)
        self.cursor.set_perspective(1)
        self.cursor.set_y(18)

    def start_hiding(self):
        self.hiding = True

    def step(self):
        if self.scrolling:
            ready_y = self.ready.y()
            if ready_y < 250:
                self.ready.set_y(ready_y + 3)
                self.cursor.set_y(ready_y - 9)

        if self.hiding:
            bg_y = self.background.y()
            if bg_y > 0:
                self.background.set_y(bg_y - 3)


    def blink(self):
        self.cursor.set_frame(1 if self.cursor_show else -1)
        self.cursor_show = not self.cursor_show
        self.call_later(333, self.blink)
        


class Scroller(TimedScene):
    letter_class = Letter

    def create_letters(self):
        return [self.letter_class() for letter in range(25)]

    def on_enter(self):
        self.unused_letters = self.create_letters()
        self.visible_letters = []
        self.n = 0

    def add_letter(self, char):
        l = self.unused_letters.pop(0)
        l.set_char(char)
        self.visible_letters.append(l)

    def step(self):
        if self.n % 9 == 0 and self.n // 9 < len(self.phrase):
            char = self.phrase[self.n // 9]
            self.add_letter(char)
            #l.set_y(randrange(16,32))

        self.n = self.n + 1

        for l in self.visible_letters:
            self.step_letter(l)
            if l.done():
                l.hide()
                self.visible_letters.remove(l)
                self.unused_letters.append(l)

        if not self.visible_letters:
            director.pop()

class Welcome(Scroller):
    duration = 60000
    part1 = """Esto es Vlad Farty, la primer demo para"""
    phrase = part1 + """ Ventilastation, la consola GPL hecha con LEDs y RPMs."""

    def on_enter(self):
        super().on_enter()
        self.part2_started = False

    def change_letters(self):
        self.unused_letters = self.more_letters

    def create_letters(self):
        self.more_letters = [RainbowLetter() for _ in range(40)]
        return super().create_letters()
    
    def step_letter(self, letter):
        letter.step(self.n)

    def step(self):
        super().step()
        if not self.part2_started and self.n // 9 > len(self.part1):
            self.part2_started = True
            self.change_letters()


class BuildFuture(Scroller):
    duration = 60000
    phrase = """Deja los memes, corta la soma, construi nuestro futuro."""
    letter_class = RainbowLetter

    def on_enter(self):
        super().on_enter()
        director.music_play(b"demo/vladfarty/happy-place")

    def step_letter(self, letter):
        letter.step(letter.x())


class DancingLions(TimedScene):
    duration = 11960 + 1500

    def on_enter(self):
        self.farty_lionhead = make_me_a_planet(28)
        self.farty_lionhead.set_y(0)
        self.farty_lionhead.disable()
        self.farty_lion = make_me_a_planet(22)
        self.farty_lion.set_y(100)
        self.farty_lion.set_frame(0)
        self.n = 0
        self.call_later(self.duration - 1500, self.start_lionhead)
        director.music_play(b"demo/vladfarty/farty-lion")
        self.increment = 2

    def start_lionhead(self):
        self.increment = -5
        self.farty_lionhead.set_y(100)
        self.farty_lionhead.set_frame(0)
        director.music_off()
        director.sound_play(b"demo/vladfarty/hit")

    def step(self):
        new_y = self.farty_lion.y() + self.increment
        if 0 < new_y < 256:
            self.farty_lion.set_y(new_y)
        self.farty_lion.set_x(vibratto[self.n % tablelen]-24)
        self.n += 1
        lionhead_size = self.farty_lionhead.y()
        if 10 < lionhead_size < 200:
            self.farty_lionhead.set_y(lionhead_size + 10)



class Chanimation(TimedScene):
    duration = 15000
    CHAMEPICS = 7
    ANIMATE_SPEED = 15

    def on_enter(self):
        self.chame_pics = []
        for n in range(self.CHAMEPICS):
            chp = make_me_a_planet(30 + n)
            self.chame_pics.append(chp)
            chp.set_y(255)
        self.n = 0
        self.current_pic = 0
        self.update_pic()

    def update_pic(self):
        numpic = self.n // self.ANIMATE_SPEED
        if numpic < len(self.chame_pics):
            self.chame_pics[self.current_pic].disable()
            self.current_pic = numpic
            self.chame_pics[self.current_pic].set_frame(0)
        else:
            director.pop()
            raise StopIteration()

    def step(self):
        self.n += 1
        self.update_pic()


class Chanijump(TimedScene):
    duration = 10000
    CHAMEPICS = 6
    ANIMATE_SPEED = 5
    order = [0, 1, 2, 3, 4, 5, 5, 4, 3, 2, 1, 0]

    def on_enter(self):
        self.chame_pics = []
        for n in range(self.CHAMEPICS):
            chp = make_me_a_planet(37 + n)
            self.chame_pics.append(chp)
            chp.set_y(255)
        self.n = 0
        self.current_pic = 0
        self.update_pic()

    def update_pic(self):
        numpic = self.order[ (self.n // self.ANIMATE_SPEED) % len(self.order) ]
        self.chame_pics[self.current_pic].disable()
        self.current_pic = numpic
        self.chame_pics[self.current_pic].set_frame(0)

    def step(self):
        self.n += 1
        self.update_pic()

class OrchestraHit(TimedScene):
    duration = 1500

    def on_enter(self):
        director.sound_play(b"demo/vladfarty/hit")
        director.music_off()


class WorldRight(Scroller):
    duration = 50206
    phrase = """Un lindo mundo, girando a la DERECHA! Racistas, dictadores y payasos anaranjados. Aca copiamos lo peor..."""

    def create_letters(self):
        return [RainbowLetter() if n % 2 else Letter() for n in range(50)]

    def add_letter(self, char):
        l = self.unused_letters.pop()
        l.set_char(char)
        self.visible_letters.append(l)
        l = self.unused_letters.pop()
        l.set_char(char)
        l.set_x(l.x()+1)
        l.delta = 2
        self.visible_letters.append(l)

    def step_letter(self, letter):
        letter.step(letter.x() + letter.delta)

    def on_enter(self):
        super().on_enter()
        self.earth = make_me_a_planet(10)
        self.earth.set_y(50)
        self.earth.set_frame(0)
        director.music_play(b"demo/vladfarty/part2")

    def step(self):
        super().step()
        earth_y = self.earth.y()
        if earth_y < 255:
            self.earth.set_y(min(earth_y + 1, 255))
        else:
            self.earth.set_x(self.earth.x() + 2)


class Copyright(TimedScene):
    duration = 5000

    def on_enter(self):
        self.copyright = Sprite()
        self.copyright.disable()
        self.copyright.set_strip(25)
        self.copyright.set_perspective(2)
        self.copyright.set_x(256-64)
        self.copyright.set_y(1)

        self.reset = Sprite()
        self.reset.set_strip(27)
        self.reset.set_perspective(2)
        self.reset.set_x(256-64)
        self.reset.set_y(0)

        self.reset2 = Sprite()
        self.reset2.set_strip(27)
        self.reset2.set_perspective(2)
        self.reset2.set_x(256+64)
        self.reset2.set_y(0)

        self.background = make_me_a_planet(26)
        self.background.set_y(255)

        self.background.set_frame(0)
        self.reset.set_frame(4)
        self.reset_step = 0
        director.music_off()

    def step(self):
        if director.was_pressed(director.BUTTON_A):
            director.pop()
            raise StopIteration()

        if self.reset_step < (9 * RESET_SPEED):
            frame = abs(self.reset_step // RESET_SPEED - 4)
            self.reset.set_frame(frame)
            self.reset2.set_frame(frame)
            self.reset_step += 1
        else:
            self.reset.disable()
            self.reset2.disable()
            self.copyright.set_frame(0)


class KudoLine:
    def __init__(self, strip, xcenter, invert):
        self.xcenter = xcenter
        self.invert = invert
        self.letters = [Sprite() for n in range(16)]
        for l in self.letters:
            l.set_strip(strip)
            l.set_perspective(1)
            l.set_y(255)
        self.status = -1
        self.counter = 255
    
    def set_word(self, word):
        for l in self.letters:
            l.disable()

        charw = 9
        spacer = charw if self.invert else -charw
        start = self.xcenter - len(word) * spacer // 2
        if not self.invert:
            start -= charw
        for n, char in enumerate(word[:16]):
            l = self.letters[n]
            if self.invert:
                frame = 255 - ord(char)
                l.set_frame(frame)
            else:
                l.set_frame(ord(char))
            l.set_x(start + n * spacer + 256)
            l.set_y(255)
        self.status = 0
        self.counter = 255

    def step(self):
        if self.status == 0:
            self.counter -= 7
            if self.counter < 17:
                self.counter = 17
                self.status = 1
            for l in self.letters:
                l.set_y(self.counter)
        elif self.status == 1:
            self.counter += 2
            if self.counter > 70:
                self.status = 2
                self.counter = 17
        elif self.status == 2:
            self.counter += 5
            for l in self.letters:
                l.set_y(self.counter)
            if self.counter > 250:
                self.status = 3

    def done(self):
        return self.status >= 1 and self.counter > 50


class Kudowz(TimedScene):
    duration = 60000

    def on_enter(self):
        self.background = make_me_a_planet(18)
        self.background.set_y(255)
        self.background.set_frame(0)

        self.kudolines = [KudoLine(19, 128, invert=True), KudoLine(20, 0, invert=False)]
        self.line = 0
        self.advance_line()

        director.music_play(b"demo/vladfarty/credits")
    
    def advance_line(self):
        if self.line >= len(credits):
            director.pop()
            raise StopIteration()

        kl = self.kudolines[self.line % 2]
        kl.set_word(credits[self.line])
        self.line += 1

    def step(self):
        advance = False
        for kl in self.kudolines:
            kl.step()

        if self.kudolines[(self.line + 1) % 2].done():
            self.advance_line()


scenes = [
    Kudowz,
    Copyright,
]

scenes = [
    Ready,
    Welcome,
    OrchestraHit,
    WorldRight,
    OrchestraHit,
    DancingLions,
    BuildFuture,
    Chanimation,
    Chanijump,
    OrchestraHit,
    Kudowz,
    Copyright,
    None,
]
    
