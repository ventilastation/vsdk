from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from time import sleep
import re
import utime


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

class Arrow(Sprite):
    
    arrow_colors = {
        0 : "flecha_azul.png", 
        1 : "flecha_roja.png", 
        2 : "flecha_roja.png", 
        3 : "flecha_azul.png",
    }
    
    def __init__(self, button, direction, bar):
        super().__init__()

        self.button = button
        self.direction = direction
        self.bar = bar
        self.is_disabled = True

        self.set_strip(stripes[self.arrow_colors[direction]]) # maybe super!
        self.set_x(64*(direction+1)-32)
        self.set_y(255)
        self.set_frame(6)
        self.disable()
        self.end_time = 0

def get_first_free_arrow(arrows, direction):
    for arrow in arrows:
        if arrow.direction == direction and arrow.is_disabled:
            return arrow

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

    step_counter = 0
    beats = []

    def on_enter(self):
        super(VanceGame, self).on_enter()
        file = open("apps/vance_songs/505.txt", "r")
        
        self.beats =  []
        for line in file.readlines():
            if "SONG_NAME" in line:
                self.song_name = line.split("=")[-1].strip()
            elif "BPMS" in line:
                self.bpms = float(line.split("=")[-1].strip())
            elif "OFFSET" in line:
                self.offset = float(line.split("=")[-1].strip())
            elif "LENGTH" in line:
                self.length = float(line.split("=")[-1].strip())
            else:
                self.beats.append(line.strip())
                

        self.scoreboard = ScoreBoard()
        self.score = 0

        self.bars = [Sprite() for _ in range(4)]
        self.bars[0].set_strip(stripes["borde_azul.png"])
        self.bars[1].set_strip(stripes["borde_rojo.png"])
        self.bars[2].set_strip(stripes["borde_rojo.png"])
        self.bars[3].set_strip(stripes["borde_azul.png"])

        self.score_labels = [ScoreLabel(direction) for direction in range(4)]

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

        director.music_play("vance/505")
        self.start_time = utime.ticks_ms()
        self.time_per_beat = 1#(self.bpms / 178)
        self.last_beat_time = 0
        self.beat_counter = 0

    def step(self):

        actual_time = utime.ticks_diff(utime.ticks_ms(),self.start_time) / 1000 # should be in secs.
        
        for arrow in self.arrows:
            if arrow.end_time < actual_time:
                arrow.disable()
                arrow.is_disabled = True

        for score_label in self.score_labels:
            if score_label.end_time < actual_time:
                score_label.disable()

        if self.beat_counter < len(self.beats) :
            if actual_time >= self.last_beat_time + self.time_per_beat:

                beat = self.beats[self.beat_counter]
                self.beat_counter += 1

                for j, tile in enumerate(beat):
                    if int(tile) > 0 and j != 2:
                        direction = j if j < 2 else j - 1
                        new_arrow = get_first_free_arrow(self.arrows, direction)
                        if new_arrow:
                            new_arrow.is_disabled = False
                            new_arrow.set_frame(0)
                            new_arrow.set_y(0)
                            new_arrow.end_time = 9999999
                            self.last_beat_time = actual_time

        for arrow in self.arrows:
            if not arrow.is_disabled:
                arrow.set_y(arrow.y() - 2)

        for i, arrow in enumerate(self.arrows):
            if director.is_pressed(arrow.button):
                arrow.bar.set_frame(0)
            else:
                arrow.bar.set_frame(1)

            if arrow.y() < 1 and not arrow.is_disabled:

                arrow.end_time = actual_time

                self.score_labels[arrow.direction].set_frame(0)
                self.score_labels[arrow.direction].end_time = actual_time + 0.75




            if director.was_pressed(arrow.button) and not arrow.is_disabled and arrow.y() in range(8, 26): 

                if arrow.y() in range(14, 18):
                    self.score += 3
                    self.score_labels[arrow.direction].set_frame(2)

                elif arrow.y() in range(8, 26):
                    self.score += 1
                    self.score_labels[arrow.direction].set_frame(1)

                self.score_labels[arrow.direction].end_time = actual_time + 1
                self.scoreboard.setscore(self.score)

                arrow.end_time = actual_time + 0.1

                arrow.set_frame(1)
                

        if director.was_pressed(director.BUTTON_D) or actual_time > self.length + 2:
            self.finished()

        self.step_counter +=1



    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return VanceGame()