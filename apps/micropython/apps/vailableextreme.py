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

BUTTON = director.JOY_DOWN

MISS_LIMIT=(255,45)
GOOD_LIMIT=(45,25)
PERFECT_LIMIT=()
ANIMATION_LIMIT=(25,1)



class CirclePart(Sprite):
    def __init__(self,i,button,y):
        super().__init__()
        self.button = button
        self.set_perspective(1)
        self.set_strip(stripes["borde_blanco.png"])
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
        self.score_state = 0
        self.order = 0
        self.set_frame(0)

class LimitScoreLine(CirclePart):
    def __init__(self,i,button,y):
        super().__init__(i,button,y)
        self.set_strip(stripes["limite.png"])
        self.set_frame(0)

class Circle:
    def __init__(self,circle_part:ExpandingLine,button,y):
        self.circle = [circle_part(i,button,y) for i in range(4)]
        self.first = False
        self.state = 0
        
    def expand(self,speed):
        for part in self.circle:
            if part.y() > 1:
                part.set_y(part.y()-speed)

    def limits(self,disabled_list,order_list):
        if self.circle in disabled_list:
            return
        
        for part in self.circle:
            py = part.y()

            # y[255,40] MISS
            if MISS_LIMIT[1] <= py <= MISS_LIMIT[0]:
                if not any(number < part.order for number in order_list): self.first = True
                s = self._detect_first(order_list,part,SCORE_STATES["miss"],0)
                if s: self.state = s

            # y[40,25] GOOD
            elif GOOD_LIMIT[1] <= py <= GOOD_LIMIT[0]:
                if not any(number < part.order for number in order_list): self.first = True
                s = self._detect_first(order_list,part,SCORE_STATES["good"],2)
                if s: self.state = s


            
            # y[25,1] animation score
            elif ANIMATION_LIMIT[1] < py < ANIMATION_LIMIT[0]:
                part.set_y(0)
                if part.is_red:
                    pass
                else:
                    self.state = SCORE_STATES["miss"]

            # Delete quarter and order
            elif py <= 1:
                self.first = False
                if part.order in order_list:
                    order_list.remove(part.order)
                if not self in disabled_list:
                    disabled_list.append(self)
                part.set_y(255)
                part.disable()
            
        if self.first:
            return self.state
        else:
            return

    @staticmethod
    def _detect_first(order_list, part, state, frame):

        if any(number < part.order for number in order_list):
            part.set_frame(frame)
            return
        
        if director.was_pressed(part.button):
            part.set_y(1)
            return SCORE_STATES["x"] if part.is_red else state
        elif part.score_state not in (SCORE_STATES["good"], SCORE_STATES["perfect"], SCORE_STATES["x"]):
            part.set_frame(frame)
            return SCORE_STATES["x"] if part.is_red else state
    
    @staticmethod
    def should_appear(beat,disabled_lines,enabled_lines,exit_order,order):
        if beat:
            if int(beat) > 0:
                # pop circle
                try:
                    print(f"creando : {beat}")
                    circle_object = disabled_lines.pop()
                    if not circle_object in enabled_lines:
                        enabled_lines.append(circle_object)

                    # add queue
                    order += 1
                    exit_order.append(order)

                    # Settea
                    for i in circle_object.circle:
                        i.order = order
                        i.set_y(255)
                        i.state = SCORE_STATES["miss"]
                        if int(beat) == 1:
                            i.is_red = False
                            i.set_strip(stripes["borde_blanco.png"])
                        elif int(beat) == 2:
                            i.is_red = True
                            i.set_strip(stripes["borde_rojo.png"])

                    return order
                except:
                    print("disabled_lines error : " + disabled_lines)

class Music:
    def __init__(self,filepath):
        self.time_per_beat = 1
        self.last_beat_time = 0
        self.beat_counter = 0

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

    def beat(self,actual_time):
        if self.beat_counter < len(self.beats):
            if actual_time >= self.last_beat_time + self.time_per_beat:

                beat = self.beats[self.beat_counter]
                self.beat_counter += 1
                if int(beat) > 0:
                    return beat
                else:
                    return
    
class Animation:
    def __init__(self,cantidad):
        self.enabled_animations = []
        self.disabled_animations = [[ScoreAnimation(i,BUTTON,ANIMATION_LIMIT[0]-1) for i in range(4)] for _ in range(cantidad)]

    def score(self,state):
        #Set
        self._set_score_animation(state,False)
        
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
                
    def _set_score_animation(self,state,auto):
        for animation in self.disabled_animations:
            try:
                if director.was_pressed(BUTTON) or auto:
                    score = self.disabled_animations.pop()

                    if not score in self.enabled_animations:
                        self.enabled_animations.append(score)

                    for i in score:
                        i.set_frame(state)
                        i.set_y(GOOD_LIMIT[1]-2)
            except:pass

        self.state_anterior = state

class VailableExtremeGame(Scene):
    stripes_rom = "vailableextreme"

    def on_enter(self):
        super(VailableExtremeGame, self).on_enter()
        
        self.music = Music("apps/extreme_songs/test.txt")
        director.music_play("vance/505")
        self.start_time = utime.ticks_ms()


        self.order = 0
        self.exit_order=[]

        # create circles
        self.enabled_lines = []
        self.disabled_lines = [Circle(ExpandingLine,BUTTON,255) for _ in range(10)]

        # create limit
        self.limit_good_line = [LimitScoreLine(i,BUTTON,25) for i in range(4)]

        self.animation = Animation(7)

        self.score_state = 0
        self.beat = 0

    def step(self):
        actual_time = utime.ticks_diff(utime.ticks_ms(),self.start_time) / 1000

        self.animation.score(self.score_state)
        self.beat = self.music.beat(actual_time)

        # circle management
        for circle in self.disabled_lines:
            order = circle.should_appear(self.beat,self.disabled_lines,self.enabled_lines,self.exit_order,self.order)
            if order:
                self.order = order 
                break
        
        # Boundary detection and circle movement
        for circle in self.enabled_lines:
            state = circle.limits(self.disabled_lines,self.exit_order)
            if state != None: self.score_state = state
            if not circle in self.disabled_lines: circle.expand(2)


        # Automatic Animation score when passing pixel 25
        for obj in self.enabled_lines:
            for part in obj.circle:
                if not any(number < part.order for number in self.exit_order) and part.y() == GOOD_LIMIT[1] and not part.is_red:
                    self.score_state = SCORE_STATES["miss"]
                    self.animation._set_score_animation(self.score_state,True)
                    break

    def finished(self):
        director.pop()
        raise StopIteration()

def main():
    return VailableExtremeGame()