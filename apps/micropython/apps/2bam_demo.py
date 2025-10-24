from urandom import choice, randint, seed
from utime import ticks_ms, ticks_diff, ticks_add
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

from math import sqrt, atan2, floor, copysign

GUSANOS=20
# !"#$%&'()*+,-./0123456789:;>=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_
class Demo2bam(Scene):
    stripes_rom = "2bam_demo"

    def on_enter(self):
        super().on_enter()

        self.main_frame=0
        seed(ticks_ms())

        self.bicho=Sprite()
        self.label=Label(14,x=48,y=0)
        self.gusanos=[Gusano(randint(0,255), 14+(60-14)*i//GUSANOS, randint(0,2)*90) for i in range(GUSANOS)]
        self.pupila = Sprite()
        self.ojo = Sprite()

        self.bicho.set_x(0)
        self.bicho.set_y(255)
        self.bicho.set_strip(stripes["bichorot.png"])
        self.bicho.set_frame(0)
        self.bicho.set_perspective(2)
        self.bicho_path_index=0

        self.ojo.set_x(0)
        self.ojo.set_y(255)
        # self.bola.set_strip(stripes["colores32.png"])
        self.ojo.set_strip(stripes["blanco-off-right.png"])
        self.ojo.set_frame(0)
        self.ojo.set_perspective(0)

        self.pupila.set_x(0)
        self.pupila.set_y(230)
        self.pupila.set_frame(0)
        self.pupila.set_perspective(0)
        self.pupila_ps = [stripes[f"p{i}.png"] for i in reversed(range(0,5))]
        self.pupila_p = 0
        self.pupila_pdir = 1
        self.pupila.set_strip(self.pupila_ps[0])

        self.label.setText("2BAM NOT DEAD!")
        # self.ojo.disable()
        # self.pupila.disable()        
        # print('\n\n\nbg0 wh', self.ojo.width(), self.ojo.height())

    def step(self):
        # Skip menu sound
        if self.main_frame==15:
            director.sound_play(b"2bam_demo/werewolf")
        self.main_frame+=1

        for b in [self.ojo]: # 201-255 / 0-55 
            b.set_x(b.x()+1)

        # self.pupila.set_strip(self.pupila_ps[self.pupila_p//5 % len(self.pupila_ps)])
        # self.pupila_p+=1
        # print('\n\n\nwh', self.bola.width(), self.bola.height())

        i=self.bicho_path_index
        i=(i+0.1)%20
        self.bicho_path_index=i
        if i<5:
            x=i
            y=0
        elif i<10:
            x=5
            y=(i-5)
        elif i<15:
            x=5-(i-10)
            y=5
        elif i<20:
            x=0
            y=5-(i-15)
        # print('\nxy', int(x),int(y))
        
        x-=2.5
        y-=2.5
        x/=2.5
        y/=2.5
        sqrt_l=sqrt(x*x + y*y)/1.415
        #l=round(16+(1-sqrt_l)*self.bicho.width())
        #l=round(16+(1-sqrt_l)*self.bicho.width()*2)

        # 0 at the outermost LED, to (54 - the sprite height)
        l=round(54*(1-sqrt_l))
        hw=self.bicho.width()//2
        a=round(-hw+128+128*atan2(y,x)/3.1415)

        self.bicho.set_frame(27-floor(28*a/255))
        self.bicho.set_x(a)
        self.bicho.set_y(l)
        # print('al', a, l)
        # print('sqrt_l', sqrt_l, l)
        

        #self.pupila.set_strip(self.pupila_ps[floor(sqrt_l*5)])
        p1 = self.pupila_p
        p1dir =self.pupila_pdir        
        p1 += 0.3 * p1dir
        if p1*p1dir > 4:
            p1 = 4*p1dir
            self.pupila_pdir *= -1
        self.pupila.set_strip(self.pupila_ps[abs(round(p1))])
        self.pupila.set_x(a if p1>0 else a+128)
        self.pupila_p = p1

        self.label.step(wiggle=4)
        for gusano in self.gusanos:
            gusano.step()

        # b=self.pupila
        # if director.is_pressed(director.JOY_LEFT):
        #     b.set_x(b.x() + 5)
        # if director.is_pressed(director.JOY_RIGHT):
        #     b.set_x(b.x() - 5)
        # if director.is_pressed(director.JOY_UP):
        #     b.set_y(b.y() + 5)
        # if director.is_pressed(director.JOY_DOWN):
        #     b.set_y(b.y() - 5)
            
        # print(b.y())
        if director.was_pressed(director.BUTTON_D):
            director.pop()
            raise StopIteration()

class Gusano:
    def __init__(self, x, y, angle):
        self.sprite=Sprite()
        self.sprite.set_x(x)
        self.sprite.set_y(y)
        self.sprite.set_strip(stripes["gusano360.png"])
        self.sprite.set_perspective(1)
        
        self.x=x
        self.frame = 0
        self.angle=angle
        self.step()

    def step(self):
        self.x+=randint(-1,1)*randint(1,4)
        self.sprite.set_x(int(self.x))
        self.frame=(self.frame+1)%4
        self.sprite.set_frame(self.frame+6*(self.angle//90))


class Label:
    def __init__(self, count, charWidth=8, x=0, y=0, wiggle=4):
        self.chars = []
        for n in range(count):
            s = Sprite()
            s.set_strip(stripes["spookyfont.png"])
            s.set_x(x - n * charWidth)
            s.set_y(y)
            s.set_perspective(2)
            self.chars.append(s)

        self.base_y=y
        self.frame=0
        self.setText("")

    def setText(self, value):
        chs = self.chars
        l1 = len(value)
        l2 = len(chs)
        i = 0
        while i < l1:
            f = ord(value[i]) - 32
            if not 0<=f<64:
                f=0
            chs[i].set_frame(f)
            i+=1
        while i < l2:
            chs[i].set_frame(0)
            i+=1

    def step(self, wiggle=0):
        chs=self.chars
        l=len(chs)

        self.frame += 1

        i = (self.frame//4)%l
        chs[i].set_y(self.base_y)
        i = (i+1)%l
        chs[i].set_y(self.base_y+wiggle)

        # for i in range(0, l):
            # offset=floor(max(0,min(abs(self.frame-i)*.5,1)*wiggle))
            # chs[i].set_y(floor(self.base_y + self.frame + i) % wiggle)
            # chs[i].set_y(self.base_y+offset)



def main():
    return Demo2bam()