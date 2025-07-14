from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
import re
import utime
import ujson

class ScoreBoard:
    def __init__(self):
        self.chars = []
        for n in range(9):
            s = Sprite()
            s.set_strip(stripes["numerals.png"])
            s.set_x(120 + n * 4)
            s.set_y(0)
            s.set_frame(10)
            s.set_perspective(2)
            self.chars.append(s)

        self.setscore(0)

    def setscore(self, value):
        for n, l in enumerate("%05d" % value):
            v = ord(l) - 0x30
            self.chars[n].set_frame(v)

class Bar(Sprite):

    def __init__(self, direction):
        super().__init__()

        if direction == 0 or direction == 3:
            bar_strip = "borde_azul.png"
        else:
            bar_strip = "borde_rojo.png"

        self.set_strip(stripes[bar_strip])
        self.set_y(5)
        self.set_x(64*direction)
        self.set_perspective(2)
        self.set_frame(1)

class Arrow(Sprite):

    def __init__(self, direction):
        super().__init__()

        self.direction = direction
        self.end_time = 0

        if direction == 0 or direction == 3:
            arrow_strip = "flecha_azul.png"
        else:
            arrow_strip = "flecha_roja.png"

        self.set_strip(stripes[arrow_strip])
        self.set_x(64*(direction+1)-32)
        self.set_y(255)
        self.disable()

    def is_disabled(self):
        return self.frame() == 255

    def enable(self):
        self.set_frame(0)
        self.set_y(255)
        self.end_time = 9999999

class ScoreLabel(Sprite):
    
    def __init__(self, direction):
        super().__init__()

        self.set_x(64*(direction)+18)
        self.set_y(0)
        self.set_perspective(2)
        self.set_frame(1)
        self.disable()
        self.set_strip(stripes["scores.png"])
        self.end_time = 0

class VanceGame(Scene):
    stripes_rom = "vance"

    def on_enter(self):

        song="badapple"

        super(VanceGame, self).on_enter()

        with open(f"./apps/vance_songs/{song}.json", 'r') as file:
            self.beats = ujson.load(file)

        self.length = self.beats["length"]

        self.scoreboard = ScoreBoard()
        self.score = 0

        self.all_buttons = [director.JOY_LEFT, director.JOY_UP, director.JOY_RIGHT,director.JOY_DOWN]
        self.all_bars = [Bar(direction) for direction in range(4)]
        self.all_labels = [ScoreLabel(direction) for direction in range(4)]
        self.all_arrows = [[Arrow(direction) for _ in range(10)] for direction in range(4)]

        self.start_time = utime.ticks_ms()
        self.beat_counter = 0

        director.music_play(f"vance/{song}")

    def step(self):

        actual_time = utime.ticks_diff(utime.ticks_ms(),self.start_time) / 1000 # should be in secs.
        for direction in range(4):

            arrows = self.all_arrows[direction]
            bar    = self.all_bars[direction]
            label  = self.all_labels[direction]
            button = self.all_buttons[direction]

            if label.end_time < actual_time:
                label.disable()

            for arrow in arrows:
                if not arrow.is_disabled():
                    if arrow.end_time < actual_time:
                        arrow.set_y(255)
                        arrow.disable()
                    elif arrow.y() < 2:
                        arrow.set_y(255)
                        arrow.disable()
                        label.set_frame(0)
                        label.end_time = actual_time + 1
                    else:
                        arrow.set_y(arrow.y() - 2)

            if director.is_pressed(button):
                bar.set_frame(0)
            else:
                bar.set_frame(1)

            if director.was_pressed(button):

                closest_arrow_to_bar = min(arrows, key=lambda arrow: abs(arrow.y() - 16))
                
                if closest_arrow_to_bar.y() in range(8, 26):
                    score_bonus = 1
                    label_frame = 1
                    if closest_arrow_to_bar.y() in range(14, 18):
                        score_bonus = 3
                        label_frame = 2
                    label.set_frame(label_frame)
                    label.end_time = actual_time + 1

                    closest_arrow_to_bar.set_frame(1)
                    closest_arrow_to_bar.end_time = actual_time + 0.1
          
                    self.score += score_bonus
                    self.scoreboard.setscore(self.score)

        if self.beat_counter < self.length:

            if actual_time > (self.beats[str(self.beat_counter)]["time"] - 0.03 * (255-16) / 2):
                
                self.beat_counter += 1
    
                direction = self.beats[str(self.beat_counter)]["direction"]
    
                for arrow in self.all_arrows[direction]:
                    if arrow.is_disabled():
                        arrow.enable()
                        break
        
        if director.was_pressed(director.BUTTON_D): # or actual_time > self.length + 2:
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return VanceGame()