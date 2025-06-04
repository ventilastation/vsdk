from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from time import sleep
import utime
import gc

TIME_MODIFIER = 3200

SCORE_STATES = {
    "miss" : 0,
    "good" : 1,
    "perfect" : 2,
    "x": 3
}

BUTTON = director.JOY_RIGHT
BUTTON2 = director.JOY_LEFT

GOOD_LIMIT_1=(39,35)
PERFECT_LIMIT=(35,30)
GOOD_LIMIT_2=(30,25)
ANIMATION_LIMIT=(25,1)
MISS_LIMIT=(255,GOOD_LIMIT_1[0])


class CirclePart(Sprite):
    def __init__(self,i,buttons,y):
        super().__init__()
        self.buttons = buttons
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
    def __init__(self,circle_part:ExpandingLine,buttons,y):
        self.circle = [circle_part(i,buttons,y) for i in range(4)]
        self.first = False
        self.state = 0
        
    def expand(self,speed,disabled_list):
        for part in self.circle:
            if part.y() > 1 and not self in disabled_list:
                part.set_y(part.y()-speed)

    def limits(self,disabled_list,order_list):
        for part in self.circle:
            if any(number < part.order for number in order_list):
                self.first = False
                return

            if not order_list:
                self.first = False
                return

            py = part.y()

            # y[255,40] MISS
            if MISS_LIMIT[1] < py <= MISS_LIMIT[0]:
                if not any(number < part.order for number in order_list):
                    self.first = True
                    self.state = SCORE_STATES["miss"]

            # y[45,35] GOOD
            elif GOOD_LIMIT_1[0] >= py > GOOD_LIMIT_1[1]:
                if self._detect_first(order_list,part,1):
                    self.first = True
                    self.state = SCORE_STATES["x"] if part.is_red else SCORE_STATES["good"]

            # y[35,27] PERFECT
            elif PERFECT_LIMIT[0] >= py >= PERFECT_LIMIT[1]:
                if self._detect_first(order_list,part,1):
                    self.first = True
                    self.state = SCORE_STATES["x"] if part.is_red else SCORE_STATES["perfect"]
            
            # y[27,25] GOOD
            elif GOOD_LIMIT_2[0] > py > GOOD_LIMIT_2[1]:
                if self._detect_first(order_list,part,1):
                    self.first = True
                    self.state = SCORE_STATES["x"] if part.is_red else SCORE_STATES["good"]
            
                if 27 >= py:
                    self.state = SCORE_STATES["miss"]

            # y[25,1] animation score
            elif 25 >= py > 1:
                part.set_y(1)

            # Delete quarter and order
            elif py <= 1:
                self.first = False
                if part.order in order_list:
                    order_list.remove(part.order)
                if not self in disabled_list:
                    disabled_list.append(self)
                part.disable()
        
        if self.first:
            return self.state

    @staticmethod
    def _detect_first(order_list, part, frame):
        part.set_frame(frame)

        if any(number < part.order for number in order_list):
            return False
        
        if director.was_pressed(part.buttons[0]) or director.was_pressed(part.buttons[1]):
            part.set_y(27)
            part.disable()
            return True
        elif part.score_state not in (SCORE_STATES["good"], SCORE_STATES["perfect"], SCORE_STATES["x"]):
            return True
    
    @staticmethod
    def should_appear(beat,disabled_lines,enabled_lines,exit_order,order):
        if beat:
            if int(beat) > 0:
                # pop circle
                try:
                    circle_object = disabled_lines.pop()
                    if not circle_object in enabled_lines:
                        enabled_lines.append(circle_object)

                    # add queue
                    order += 1
                    exit_order.append(order)

                    # Settea
                    for i in circle_object.circle:
                        i.set_frame(0)
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
        self.anterior = 0
        file = open(filepath, "r")
        self.ms = {}
        self.tipo = []
        self.contador = 0
        for line in file:
            partes = line.strip().split('\t')
            self.ms[int(partes[0])] = int(partes[1])
            
    
    def beat(self,actual_time):
        time = int(actual_time)
        if self.contador > len(self.ms):
            return "win"
        if time in self.ms and self.anterior != time:
            self.anterior = time
            self.contador += 1
            return self.ms[time]
            
    
class Animation:
    def __init__(self,cantidad):
        self.enabled_animations = []
        self.disabled_animations = [[ScoreAnimation(i,BUTTON,24) for i in range(4)] for _ in range(cantidad)]

    def move_score(self):
        for animation in self.enabled_animations:
            for quarter in animation:
                if animation in self.disabled_animations:
                    continue

                if quarter.y() >= 1:
                    quarter.set_y(quarter.y()-1)
                elif quarter.y() <= 1:
                    self.disabled_animations.append(animation)
                    quarter.disable()
                    quarter.set_y(GOOD_LIMIT_2[1])
                
    def set_score(self,state,auto):
        for animation in self.disabled_animations:
            try:
                if auto:
                    score = self.disabled_animations.pop()

                    if not score in self.enabled_animations:
                        self.enabled_animations.append(score)

                    for i in score:
                        i.set_frame(state)
                        i.set_y(GOOD_LIMIT_2[1])
            except:pass

class Mode:
    def __init__(self):
        self.score = 10
        self.contador_perfect = 0
        self.mode = 0
        self.state = 0
    
    def life(self, state, auto=False):
        if self.score < 0:
            return
        
        if auto:
            self.state = state
            if state == SCORE_STATES["miss"]:
                if self.score >= 1:
                    self.score -= 1
                self.contador_perfect = 0
            elif state == SCORE_STATES["good"]:
                if self.contador_perfect < 4:
                    self.contador_perfect = 0
            elif state == SCORE_STATES["perfect"]:
                if self.score < 15:
                    self.score += 1
                if self.score >= 15:
                    self.contador_perfect += 1
    
    def mangment(self):
        if self.score < 0:
            return -3

        if self.score <= 5:
            if self.score <= 0:
                self.mode = -3
            else:
                self.mode = -1
        elif self.score >= 5:
            if self.contador_perfect >= 4:
                self.mode = 1
            else:
                self.mode = 0

        if self.state == 0 and self.mode != -3:
            return -2
        else:
            return self.mode

class Dancer:   
    def __init__(self):
        self.sprites_n = ["av_n1.png","av_n2.png","av_n3.png"]
        self.sprites_d = ["av_t1.png","av_t2.png","av_t3.png"]
        self.sprites_p = ["av_f1.png","av_f2.png","av_f3.png"]
        self.sprites_dead = ["av_apunialado01.png","av_apunialado02.png","av_apunialado03.png","av_apunialado04.png","av_apunialado05.png"]
        self.sprites_m = "av_apunialado.png"

        self.dancer = Sprite()
        self.dancer.set_strip(stripes[self.sprites_n[0]])
        self.dancer.set_perspective(0)
        self.dancer.set_x(0)
        self.dancer.set_y(255)
        self.dancer.set_frame(0)
        self.count = 0
    
    def dance(self,mode):
        if mode == -1:
            sprite_list = self.sprites_d
        elif mode == 0:
            sprite_list = self.sprites_n
        elif mode == 1:
            sprite_list = self.sprites_p

        if mode == -3:
            sprite_list = self.sprites_dead
            self.count += 1
        else:
            if self.count < 2:
                self.count += 1
            else:
                self.count = 0

        try:
            if mode == -2:
                self.dancer.set_strip(stripes[self.sprites_m])
                self.dancer.set_perspective(0)
                self.dancer.set_x(0)
                self.dancer.set_y(255)
                self.dancer.set_frame(0)
            else:
                self.dancer.set_strip(stripes[sprite_list[self.count]])
                self.dancer.set_perspective(0)
                self.dancer.set_x(0)
                self.dancer.set_y(255)
                self.dancer.set_frame(0)
        except:pass

        if mode == -3:
            return True


class VailableExtremeGame(Scene):
    stripes_rom = "vailableextreme"

    def on_enter(self):
        super(VailableExtremeGame, self).on_enter()
    
        self.music_test = Music("apps/extreme_songs/electrochongo.txt")
        self.start_time = utime.ticks_ms()

        self.order = 0
        self.exit_order=[]

        self.dancer = Dancer()

        self.mode = Mode()
        
        # create limit
        self.limit_good_line = [LimitScoreLine(i,BUTTON,(34)) for i in range(4)]
        self.limit_good_line = [LimitScoreLine(i,BUTTON,(41)) for i in range(4)]

        # create circles
        self.enabled_lines = []
        self.disabled_lines = [Circle(ExpandingLine,[BUTTON,BUTTON2],255) for _ in range(10)]

        self.animation = Animation(10)

        self.score_state = 0
        self.beat = 0

        self.stop = False
        self.cronometrer = -1

    def step(self):
        actual_time = utime.ticks_diff(utime.ticks_ms(), self.start_time)
        redondeado = (actual_time // 50) * 50

        if redondeado == TIME_MODIFIER:
            director.music_play("vailableextreme/electrochongo")

        self.beat = self.music_test.beat(redondeado)
        if self.beat == "win":
            self.cronometrer = actual_time + 3000

        # circle management
        for circle in self.disabled_lines:
            order = circle.should_appear(self.beat,self.disabled_lines,self.enabled_lines,self.exit_order,self.order)
            if order:
                self.order = order 
                break
  
        # Boundary detection and circle movement
        for circle in self.enabled_lines:
            if not circle in self.disabled_lines: 
                state = circle.limits(self.disabled_lines,self.exit_order)
                if state != None: self.score_state = state
                circle.expand(2,self.disabled_lines)

        # Automatic Animation score when passing pixel 25
        show = False
        for obj in self.enabled_lines:
            for part in obj.circle:
                if part.y() == GOOD_LIMIT_2[1] and not part.is_red:
                    show = True
                    part.disable()
                    break

        
        if (director.was_pressed(BUTTON) or director.was_pressed(BUTTON2) and self.score_state == SCORE_STATES["miss"]) or show:
            if not self.stop:
                self.mode.life(self.score_state,True)
                if self.dancer.dance(self.mode.mangment()):
                    self.cronometrer = redondeado + 4000
                    self.stop = True
            else:
                self.dancer.dance(-3)
                self.score_state = SCORE_STATES["miss"]
            self.animation.set_score(self.score_state,True)
        
        if self.cronometrer == redondeado:
            self.finished()

        self.animation.move_score()

        if not self.exit_order:
            self.score_state = 0

        if director.was_pressed(director.BUTTON_D):
            self.finished()
        
        gc.collect()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return VailableExtremeGame()