from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
import utime

TIME_MODIFIER = 3500

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

class ScoreAnimation(Sprite):
    def __init__(self,i,y,buttons):
        super().__init__()
        self.buttons = buttons
        self.set_perspective(1)
        self.set_x(64*i)
        self.set_y(y)
        self.set_strip(stripes["scores.png"])
        self.disable()

class Limit(Sprite):
    def __init__(self,y):
        super().__init__()
        self.set_perspective(1)
        self.set_strip(stripes["limite.png"])
        self.set_frame(0)
        self.set_x(0)
        self.set_y(y)

class Wave(Sprite):
    def __init__(self,buttons,y):
        super().__init__()
        self.set_perspective(1)
        self.set_strip(stripes["borde_blanco.png"])
        self.set_x(0)
        self.set_y(y)
        self.buttons = buttons
        self.is_red = False
        self.score_state = 0
        self.order = 0

    def expand(self,speed,disabled_list):
        if self.y() > 1 and not self in disabled_list:
            self.set_y(self.y()-speed)
    
    def limits(self,disabled_list,order_list):
        if any(number < self.order for number in order_list):
            self.first = False
            return

        if not order_list:
            self.first = False
            return

        py = self.y()

        # y[255,40] MISS
        if MISS_LIMIT[1] < py <= MISS_LIMIT[0]:
            if not any(number < self.order for number in order_list):
                self.first = True
                self.state = SCORE_STATES["miss"]

        # y[45,35] GOOD
        elif GOOD_LIMIT_1[0] >= py > GOOD_LIMIT_1[1]:
            if self._detect_first(order_list,1):
                self.first = True
                self.state = SCORE_STATES["x"] if self.is_red else SCORE_STATES["good"]

        # y[35,27] PERFECT
        elif PERFECT_LIMIT[0] >= py >= PERFECT_LIMIT[1]:
            if self._detect_first(order_list,1):
                self.first = True
                self.state = SCORE_STATES["x"] if self.is_red else SCORE_STATES["perfect"]
        
        # y[27,25] GOOD
        elif GOOD_LIMIT_2[0] > py > GOOD_LIMIT_2[1]:
            if self._detect_first(order_list,1):
                self.first = True
                self.state = SCORE_STATES["x"] if self.is_red else SCORE_STATES["good"]
        
        elif 25 == py:
            self.state = SCORE_STATES["miss"]

        # y[25,1] animation score
        elif 23 >= py > 1:
            self.set_y(1)

        # Delete quarter and order
        elif py <= 1:
            self.first = False
            if self.order in order_list:
                order_list.remove(self.order)
            if not self in disabled_list:
                disabled_list.append(self)
            self.disable()
    
        if self.first:
            return self.state
        
    def _detect_first(self,order_list, frame):
        self.set_frame(frame)

        if any(number < self.order for number in order_list):
            return False
        
        if director.was_pressed(self.buttons[0]) or director.was_pressed(self.buttons[1]):
            self.set_y(25)
            self.disable()
            return True
        elif self.score_state not in (SCORE_STATES["good"], SCORE_STATES["perfect"], SCORE_STATES["x"]):
            return True
    
    @staticmethod
    def should_appear(beat,disabled_lines,enabled_lines,exit_order,order):
        if beat:
            # pop wave
            wave = disabled_lines.pop()
            if not wave in enabled_lines:
                enabled_lines.append(wave)

            # add queue
            order += 1
            exit_order.append(order)

            wave.set_frame(0)
            wave.order = order
            wave.set_y(255)
            wave.state = SCORE_STATES["miss"]
            if int(beat) == 1:
                wave.is_red = False
                wave.set_strip(stripes["borde_blanco.png"])
            elif int(beat) == 2:
                wave.is_red = True
                wave.set_strip(stripes["borde_rojo.png"])
            return order

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
        self.score = 15
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
                if self.score < 20:
                    self.score += 1
                if self.score >= 20:
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

class Dancer(Sprite):   
    def __init__(self):
        super().__init__()
        self.sprites_n = ["av_n1.png","av_n2.png","av_n3.png"]
        self.sprites_d = ["av_t1.png","av_t2.png","av_t3.png"]
        self.sprites_p = ["av_f1.png","av_f2.png","av_f3.png"]
        self.sprites_m = ["av_apunialado01.png","av_apunialado.png","av_apunialado02.png"]
        self.sprites_win = ["av_win1.png","av_win2.png"]
        self.sprites_dead = ["av_apunialado01.png","av_apunialado02.png","av_apunialado03.png","av_apunialado04.png","av_apunialado05.png"]

        self.set_strip(stripes["av_first.png"])
        self.set_perspective(0)
        self.set_x(0)
        self.set_y(255)
        self.set_frame(0)
        self.disable()
        self.count = 0
        self.count_dead = 0

        self.anterior = -1
        self.dead_accumulation = 0
        self.dead_timer = False
        self.start_dead = 0
    
    def dance(self,mode):
        if not mode == -3:
            sprite_list = self._choice_dance(mode)
            if mode == -2:
                if self.count == 0:
                    self.count = 1
                else:
                    self.count = 0
            else:
                if self.count < 2:
                    self.count += 1
                else:
                    self.count = 0
            self._show(sprite_list,self.count)

    def _choice_dance(self,mode):
        if mode == -1:
            sprite_list = self.sprites_d
        elif mode == 0:
            sprite_list = self.sprites_n
        elif mode == 1:
            sprite_list = self.sprites_p
        elif mode == -2:
            sprite_list = self.sprites_m
        return sprite_list
        
    def lose(self,mode):
        if mode == -3:
            return True
        
    def dead(self,time):
        if self.anterior == time:
            return
        
        if not self.dead_timer:
            self.dead_timer = time
            self.start_dead = time

        self.dead_accumulation = time - self.dead_timer

        if self.dead_accumulation >= 300:
            sprite_list = self.sprites_dead
            self.count_dead += 1
            self._show(sprite_list,self.count_dead)
            self.dead_accumulation = 0
            self.dead_timer = time

        if self.start_dead + 5000 == time:
            return True
        
    def win(self,time):
        if self.anterior == time:
            return
        
        if not self.dead_timer:
            self.dead_timer = time
            self.start_dead = time

        self.dead_accumulation = time - self.dead_timer

        if self.dead_accumulation >= 100:
            if self.count == 0:
                self.count = 1
            else:
                self.count = 0
            self._show(self.sprites_win,self.count)
            self.dead_accumulation = 0
            self.dead_timer = time
        
    def _show(self,sprite,count):
        try:
            self.set_strip(stripes[sprite[count]])
            self.set_perspective(0)
            self.set_x(0)
            self.set_y(255)
            self.set_frame(0)
        except:pass


class VailableExtremeGame(Scene):
    stripes_rom = "vailableextreme"

    def press(self):
        self.mode.life(self.score_state,True)
        self.dancer.dance(self.mode.mangment())
        self.animation.set_score(self.score_state,True)

    def on_enter(self):
        super(VailableExtremeGame, self).on_enter()
        self.music_test = False

        self.order = 0
        self.exit_order=[]

        self.dancer = Dancer()

        self.win = Sprite()
        self.win.set_strip(stripes["gane.png"])
        self.win.set_perspective(0)
        self.win.set_x(0)
        self.win.set_y(255)
        self.win.set_frame(0)
        self.win.disable()

        self.lose = Sprite()
        self.lose.set_strip(stripes["perdi.png"])
        self.lose.set_perspective(0)
        self.lose.set_x(0)
        self.lose.set_y(255)
        self.lose.set_frame(0)
        self.lose.disable()

        self.tutorial = Sprite()
        self.tutorial.set_strip(stripes["tutorial.png"])
        self.tutorial.set_perspective(0)
        self.tutorial.set_x(0)
        self.tutorial.set_y(255)
        self.tutorial.set_frame(0)

        self.mode = Mode()

        self.limit1 = Limit(34)
        self.limit2 = Limit(41)

        self.enabled_lines = []
        self.disabled_lines = [Wave([BUTTON,BUTTON2],200) for _ in range(10)]

        self.animation = Animation(10)

        self.score_state = 0
        self.beat = 0
        self.stop = False

        self.start_time = utime.ticks_ms()

    def step(self):
        actual_time = utime.ticks_diff(utime.ticks_ms(), self.start_time)
        redondeado = (actual_time // 50) * 50

        if redondeado == 2000:
            self.music_test = Music("apps/extreme_songs/electrochongo.txt")

        if redondeado == TIME_MODIFIER + 2000:
            director.music_play("vailableextreme/electrochongo")
            self.tutorial.disable()
            self.dancer.set_frame(0)

        # wave management
        if self.music_test:
            self.beat = self.music_test.beat(redondeado)
            for wave in self.disabled_lines:
                order = wave.should_appear(self.beat,self.disabled_lines,self.enabled_lines,self.exit_order,self.order)
                if order:
                    self.order = order
                    break
        
        # pop wave and expand
        for wave in self.enabled_lines:
            if not wave in self.disabled_lines:
                state = wave.limits(self.disabled_lines,self.exit_order)
                if state != None: 
                    self.score_state = state
                wave.expand(2,self.disabled_lines)

        if not self.stop:
            for wave in self.enabled_lines:
                    if wave.y() == 23 and not wave.is_red:
                        self.press()
                        break
                    elif (director.was_pressed(BUTTON) != director.was_pressed(BUTTON2)) and not any(number < wave.order for number in self.exit_order) and wave.y() > GOOD_LIMIT_1[0]:
                        self.press()
                        break

        self.animation.move_score()

        if self.dancer.lose(self.mode.mangment()):
            if self.dancer.dead(redondeado):
                self.finished()
            self.lose.set_frame(0)
            self.stop = True

        if 119900 <= redondeado:
            self.dancer.win(redondeado)
            self.win.set_frame(0)
            self.stop = True

        if 125900 == redondeado:
            self.finished()
        
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return VailableExtremeGame()
