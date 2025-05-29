from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from time import sleep
import utime

SCORE_STATES = {
    "miss" : 0, 
    "good" : 1, 
    "perfect" : 2,
    "x": 3
}

MISS_LIMIT=(255,45)
GOOD_LIMIT=(45,25)
PERFECT_LIMIT=()
ANIMATION_LIMIT=(25,1)



class CirclePart(Sprite):
    def __init__(self,i,button,y):
        super().__init__()
        self.button = button
        self.set_perspective(1)
        self.set_x(64*i)
        self.set_y(y)

class ScoreAnimation(CirclePart):
    def __init__(self,i,button,y):
        super().__init__(i,button,y)
        self.set_strip(stripes["scores.png"])
        self.disable()

class ExpandingLine(CirclePart):
    def __init__(self,i,button,y):
        super().__init__(i,button,y)
        self.is_red = False
        self.score_state = 0 #frame del score
        self.order = 0
        self.set_frame(0)

class LimitScoreLine(CirclePart):
    def __init__(self,i,button,y):
        super().__init__(i,button,y)
        self.set_strip(stripes["limite.png"])
        self.set_frame(0)

class Music:
    def extract(self,filepath):
        file = open(filepath, "r")
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


class VailableExtremeGame(Scene):
    stripes_rom = "vailableextreme"

    def on_enter(self):
        super(VailableExtremeGame, self).on_enter()
        
        Music.extract(self,"apps/extreme_songs/test.txt")

        director.music_play("vance/505")
        self.start_time = utime.ticks_ms()
        self.time_per_beat = 1
        self.last_beat_time = 0
        self.beat_counter = 0

        self.buttons = [director.JOY_LEFT, director.JOY_UP, director.JOY_RIGHT,director.JOY_DOWN]

        self.order = 0
        self.exit_order=[]

        # create n circles
        self.enabled_lines = []
        self.disabled_lines = [[ExpandingLine(i,self.buttons[3],255) for i in range(4)] for _ in range(10)]

        # create limit
        self.limit_good_line = [LimitScoreLine(i,self.buttons[3],25) for i in range(4)]

        # create animation score
        self.enabled_animations = []
        self.disabled_animations = [[ScoreAnimation(i,self.buttons[3],ANIMATION_LIMIT[0]-1) for i in range(4)] for _ in range(7)]

        self.score_state = 0

    def set_score_animation(self):
        for animation in self.disabled_animations:
            try:
                if director.was_pressed(self.buttons[3]):
                    score = self.disabled_animations.pop()

                    if not score in self.enabled_animations:
                        self.enabled_animations.append(score)

                    for i in score:
                        i.set_frame(self.score_state)
                        i.set_y(GOOD_LIMIT[1]-2)
            except:pass

    def score_animation(self):
        #Set
        self.set_score_animation()
        
        #Move
        for animation in self.enabled_animations:
            for quarter in animation:
                if animation in self.disabled_animations:
                    continue

                if quarter.y() >= 1:
                    quarter.set_y(quarter.y()-1)
                elif quarter.y() <= 1:
                    self.disabled_animations.append(animation)
                    quarter.disable()
                    quarter.set_y(GOOD_LIMIT[1]-2)
             

    def detect_first(self, quarter, velocity, state, frame):
        move = lambda: (
            quarter.set_frame(frame),
            quarter.set_y(quarter.y() - velocity)
            )

        if any(number < quarter.order for number in self.exit_order):
            move()
            return
        
        if director.was_pressed(quarter.button):
            quarter.set_y(1)
        elif quarter.state not in (SCORE_STATES["good"], SCORE_STATES["perfect"], SCORE_STATES["x"]):
            self.score_state = SCORE_STATES["x"] if quarter.is_red else state
            move()


    def expand_line(self):
        for circle in self.enabled_lines:
            for quarter in circle:
                if circle in self.disabled_lines:
                    continue

                qy = quarter.y()

                # y[255,40] MISS
                if GOOD_LIMIT[0] <= qy <= MISS_LIMIT[0]:
                    self.detect_first(quarter,2,SCORE_STATES["miss"],0)

                # y[40,25] GOOD
                elif GOOD_LIMIT[1] <= qy <= GOOD_LIMIT[0]:
                    self.detect_first(quarter,2,SCORE_STATES["good"],2)

                # y[25,1] animation score
                elif ANIMATION_LIMIT[1] < qy < ANIMATION_LIMIT[0]:
                    quarter.set_y(0)
                    if quarter.is_red:
                        pass
                    else:
                        self.score_state = SCORE_STATES["miss"]
                        self.set_score_animation()

                # Delete quarter and order
                elif qy <= 1:
                    self.exit_order.remove(quarter.order)
                    self.disabled_lines.append(circle)

    def step(self):
        actual_time = utime.ticks_diff(utime.ticks_ms(),self.start_time) / 1000
        self.score_animation()
        self.expand_line()
        
        if director.was_pressed(director.BUTTON_D):
            self.finished()
       

        if self.beat_counter < len(self.beats):
            if actual_time >= self.last_beat_time + self.time_per_beat:

                beat = self.beats[self.beat_counter]
                self.beat_counter += 1

                for tile in beat:
                    if int(tile) > 0:
                        # pop circle
                        try:
                            circle = self.disabled_lines.pop()
                            if not circle in self.enabled_lines:
                                self.enabled_lines.append(circle)

                            # add queue
                            self.order += 1
                            self.exit_order.append(self.order)

                            # Settea
                            for i in circle:
                                i.order = self.order
                                i.set_y(255)
                                i.state = SCORE_STATES["miss"]
                                if int(tile) == 1:
                                    i.is_red = False
                                    i.set_strip(stripes["borde_blanco.png"])
                                elif int(tile) == 2:
                                    i.is_red = True
                                    i.set_strip(stripes["borde_rojo.png"])
                        except:pass

        

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return VailableExtremeGame()