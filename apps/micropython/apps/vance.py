from urandom import choice, randrange, seed
from ventilastation.director import director
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from ventilastation.imagenes import strips
from time import sleep
import re
import utime


class ScoreBoard:
    def __init__(self):
        self.chars = []
        for n in range(9):
            s = Sprite()
            s.set_strip(strips.vyruss.numerals)
            s.set_x(110 + n * 4)
            s.set_y(0)
            s.set_frame(10)
            s.set_perspective(2)
            self.chars.append(s)

        self.setscore(0)

    def setscore(self, value):
        for n, l in enumerate("%05d" % value):
            v = ord(l) - 0x30
            self.chars[n].set_frame(v)

class Arrow(Sprite):
    
    arrow_colors = {
        0 : strips.vance.flecha_azul, 
        1 : strips.vance.flecha_roja, 
        2 : strips.vance.flecha_roja, 
        3 : strips.vance.flecha_azul
    }
    
    def __init__(self, button, direction, bar):
        super().__init__()

        self.button = button
        self.direction = direction
        self.bar = bar
        self.is_disabled = True

        self.set_strip(self.arrow_colors[direction]) # maybe super!
        self.set_x(64*(direction+1)-32)
        self.set_y(255)
        self.set_frame(6)
        self.disable()

def get_first_free_arrow(arrows, direction):
    for arrow in arrows:
        if arrow.direction == direction and arrow.is_disabled:
            return arrow


class VanceGame(Scene):

    step_counter = 0
    beats = []

    arrow_colors = {
        0 : strips.vance.flecha_azul, 
        1 : strips.vance.flecha_roja, 
        2 : strips.vance.flecha_roja, 
        3 : strips.vance.flecha_azul
    }

    def on_enter(self):
        director.music_play("vance/505")
        file = open("../vance_songs/505-S2-HIDDEN.txt", "r")
        
        self.beats =  []
        for line in file.readlines():
            if "SONG_NAME" in line:
                self.song_name = line.split("=")[-1].replace("\n", "")
            elif "BPMS" in line:
                self.bpms = float(line.split("=")[-1].replace("\n", ""))
            elif "OFFSET" in line:
                self.offset = float(line.split("=")[-1].replace("\n", ""))
            else:
                self.beats.append(line.replace("\n", ""))
                

        self.scoreboard = ScoreBoard()
        self.score = 0

        self.bars = [Sprite() for _ in range(4)]
        self.bars[0].set_strip(strips.vance.borde_azul)
        self.bars[1].set_strip(strips.vance.borde_rojo)
        self.bars[2].set_strip(strips.vance.borde_rojo)
        self.bars[3].set_strip(strips.vance.borde_azul)

        for i, bar in enumerate(self.bars):
            bar.set_y(5)
            bar.set_x(64*i)
            bar.set_perspective(2)
            bar.set_frame(1)

        self.buttons = [director.JOY_LEFT, director.JOY_UP, director.JOY_RIGHT,director.JOY_DOWN]
        self.arrows = []
        for i in range(10):
            for direction in range(4):
                new_arrow = Arrow(self.buttons[direction], direction, self.bars[direction])
                self.arrows.append(new_arrow)

        self.start_time = utime.ticks_ms()
        self.time_per_beat = 60 / self.bpms
        self.last_beat_time = 0
        self.beat_counter = 0

    def step(self):
        actual_time = utime.ticks_diff(utime.ticks_ms(),self.start_time) / 1000 # should be in secs.

        if self.beat_counter < len(self.beats):
            if actual_time >= self.last_beat_time + self.time_per_beat:

                beat = self.beats[self.beat_counter]
                self.beat_counter += 1

                for j, tile in enumerate(beat):
                    if int(tile) > 0 and j != 2:
                        direction = j if j < 2 else j - 1
                        new_arrow = get_first_free_arrow(self.arrows, direction)
                        new_arrow.is_disabled = False
                        new_arrow.set_frame(0)
                        new_arrow.set_y(0)
                        self.last_beat_time = actual_time

        for arrow in self.arrows:
            arrow.set_y(arrow.y() - 2)

        for i, arrow in enumerate(self.arrows):
            if director.is_pressed(arrow.button):
                arrow.bar.set_frame(0)
            else:
                arrow.bar.set_frame(1)

            if arrow.y() < 1:
                arrow.disable()
                arrow.is_disabled = True

            if arrow.y() < 30 and director.was_pressed(arrow.button):
                self.score += 1
                self.scoreboard.setscore(self.score)
                arrow.disable()

        if director.was_pressed(director.BUTTON_D):
            self.finished()

        self.step_counter +=1


    def finished(self):
        director.pop()
        raise StopIteration()

