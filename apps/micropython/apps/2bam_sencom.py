# Senile command
# Ayuda al motor del ventilador a evitar que los dedos geriatricos lo atasquen.
# 2bam.com 2025

# Controles: Flechas                   : Movimiento
#            Boton A      (emu: SPACE) : Dispara
#            Mantener boton A          : Activa movimiento rapido


# TODO ^: Fix colision
# TODO: End of level warp fx (paleta y efecto loco del fullscreen
# TODO: Dedos GFX

# TODO: Enemigo2 bomba q cambia de direccion sin estela mas dificil

# TODO: Estela azul para tus misiles/delay?
# TODO: COlor de paleta "glitch" para explosiones tuyas

# TODO: Score y missile count ( te deja usar de mas?? )
# TODO: waves dificiles
# TODO v: Perder "traba" el ventilador (imagen)
# TODO: Si no es prohibitivo, otros colores para la estela --> no lo es ahora q la reduje, pero quizás simplemente
#       que ciclen

# Bonus points con misiles no usados y ciudades no destruidas

# TODO: Ojo de usar el centro q tiene una tapita en el de españa

# TODO: Level manager
# TODO: "Edificios"
# TODO: GFX dedos
# TODO: SFX
# TODO: Miniboss "WARNING WARNING WARNING" q tira todos juntos
# Efecto loco con texto_intro en perspective 2 yendo hacia adentro!

# TODO ^: Que tambien haya impacto en el suelo (te resta puntos groso pero no perdes) -- igual q apunte "mas" hacia los edificios

# Game scene sprite budget
#    1 BG fan move (FS)
#    1 BG fan stop (FS)
#    1 center core
#    5 cities            NUM_CITIES
#    1 crosshair/aim
#    4 booms             MAX_WEAPON
#   10 (x2) missiles
#    X hiscore?
# ------------------
#   33 total 

from urandom import choice, randint, seed
from utime import ticks_ms, ticks_diff, ticks_add
from ventilastation.director import director, stripes as STRIPS
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from math import sqrt, atan2, floor, copysign, sin,cos, pi

from ventilastation import povdisplay
import struct

STEPS_PER_SECOND=33
SECONDS_PER_STEP=1.0/STEPS_PER_SECOND
AIM_LIMIT=110

INV_SQRT2=0.70710678

#15frames 72x36 step 12 
# TRAIL_FRAMES=8
# TRAIL_STEP=4
#TRAIL_FRAMES=15
#73x36
TRAIL_SUB_FRAMES=3
TRAIL_STEP=12
TRAIL_LINE_HW=1.5

MISSILE_ANGLES = [-45,-25, 0, 25, 45]
MISSILE_SINS=[sin(deg*pi/180) for deg in MISSILE_ANGLES]
# MISSILE_ANGLES = [-60,-40,-20, 0, 20, 40, 60]

# 32 limit is due to how trails work (they kind of wrap around but are hidden
# by the center image, if they were longer it would require special case math
MISSILE_MAX_DEPTH=34
WARHEAD_FRAMES=3

NUM_CITIES=5
MAX_WEAPON=4
MAX_ATTACKS=20

BOOM_FRAMES=[0,1,2,3,2,3,2,3,2,1,0]
BOOM_RADIUS_POW2=10*10
# BOOM_FRAMES=[0,1,2,3,4,3,4,3,4,3,2,1,0]

BASE_SPEED=0.25

palette=bytearray([randint(0,255) for _ in range(1024*6)])

def find_color_index(pal, r,g,b):
    for i in range(0, len(pal), 4):
        if pal[i+1] == b and pal[i+2] == g and pal[i+3] == r:
            print('COLOR FOUND',r,g,b, 'AT', i)
            return i

    print('COLOR NOT FOUND',r,g,b)
    return 254


class Boom:
    def __init__(self):
        self.sprite=Sprite()
        self.sprite.set_strip(STRIPS["target.png"])
        self.sprite.set_perspective(1)
        # self.sprite.set_frame(0)
        self.alive=False
        self.do_damage=False
    
    def reset(self, x,y, ttl):
        self.fpst = len(BOOM_FRAMES)/ttl
        self.frame = 0
        self.x=x
        self.y=y
        self.sprite.set_x(x-self.sprite.width()//2)
        self.sprite.set_y(y-self.sprite.height()//2)
        self.alive=True
        self.do_damage=False
    
    def step(self):
        if not self.alive:
            return

        self.frame += self.fpst
        fi=floor(self.frame)
        if fi == len(BOOM_FRAMES):
            self.alive=False
            self.sprite.disable()
            return
        real_frame=BOOM_FRAMES[fi]
        self.do_damage=real_frame >= 3
        self.sprite.set_frame(real_frame)

class Missile:
    angle_index=0
    depth=0
    base_x=0
    hit_ground=False
    def __init__(self):
        # self._debug=Sprite()
        # self._debug.set_strip(STRIPS["crosshair.png"])
        # self._debug.set_perspective(1)
        # self._debug.set_frame(0)
        
        self.warhead=Sprite()
        self.warhead.set_strip(STRIPS["dedo.png"])
        self.warhead.set_perspective(2)
        #self.warhead.set_frame(0)
        self.warhead_hw=self.warhead.width()//2


        self.trail=Sprite()
        self.trail.set_strip(STRIPS["trail.png"])
        self.trail.set_perspective(2)
        #self.trail.set_frame(0)
        self.trail_hw=self.trail.width()//2
        self.alive=False

    def reset(self, target_city, target_x, angle_index, speed):
        #self.base_x=base_x-16
        self.target_city=target_city
        self.base_x=target_x-round(MISSILE_SINS[angle_index]*MISSILE_MAX_DEPTH)#-self.warhead_hw
        self.angle_index=angle_index
        self.depth=0
        self.hit_ground=False
        self.alive=True
        self.speed=speed
        self.warhead.set_frame(0)
        self.step()


    def kill(self):
        self.warhead.disable()
        self.trail.disable()
        self.alive=False

    def step(self):
        # MEMO: 54-TRAIL_STEP is a hack to be able to draw from the border itself in perspective mode 2
        if self.depth >= MISSILE_MAX_DEPTH:
            self.hit_ground=True
            return

        self.depth+=self.speed
        bx = self.base_x
        d = floor(self.depth)
        # self.trail.set_y(54-TRAIL_STEP)

        sin_rad=MISSILE_SINS[self.angle_index]
        off_x_bis = int(bx-self.trail_hw + TRAIL_LINE_HW + sin_rad * (d))#-sin_rad*MISSILE_MAX_DEPTH)
        # off_x_bis = round(bx-self.trail_hw + sin_rad * (d%TRAIL_STEP)- sin_rad*MISSILE_MAX_DEPTH)
        self.trail.set_y(54-TRAIL_STEP + d%TRAIL_STEP)  # HACK: Wrap around center and hide that with the Core
        self.trail.set_x( off_x_bis)

        # self.trail.set_y(54-TRAIL_STEP + d % TRAIL_STEP)
        # off_x_bis = round(sin_rad*(d%TRAIL_STEP - TRAIL_STEP))
        # self.trail.set_x(bx -self.trail_hw + off_x_bis) #-self.trail_hw) # -w/2

        # self.trail.set_y(54-TRAIL_STEP + d)# % TRAIL_STEP)
        #self.trail.set_y(16)
        # self.trail.set_x(bx-self.trail_hw + off_x) #-self.trail_hw) # -w/2

        # self.trail.set_y(d % TRAIL_STEP - 16)
        # self.trail.set_y(16-(d % TRAIL_STEP))
        self.trail.set_frame(self.angle_index*TRAIL_SUB_FRAMES + d//TRAIL_STEP)

        # self.trail.set_frame(d//TRAIL_STEP)
        off_x = int(sin_rad * d)
        wx=bx+off_x
        wy=42+d+self.warhead.height()
        self.warhead.set_x(wx-self.warhead_hw)
        self.warhead.set_y(wy)
        self.warhead.set_frame(d%WARHEAD_FRAMES)
        self.hit_x=wx
        if 0 <= d < 54:
            self.hit_y=self.warhead.height()+INV_DEEPSPACE[54-d] # TODO: lerp [d] y [d+1] usando self.depth?    
        else:
            self.hit_y=-10000
        
        # self._debug.set_x(self.hit_x-self._debug.width()//2)
        # self._debug.set_y(self.hit_y-self._debug.height()//2)

        # self.warhead.set_y(42+d - round(cos(rad) * (d//TRAIL_STEP)))
        # #TODO: cos offset self.set_y(
        
def find_dead(pool):
    for ent in pool:
        if not ent.alive:
            return ent


class EnemyBomb:
    def __init__(self):
        self._sp=_sp=Sprite()
        _sp.set_strip(STRIPS["dedo2.png"])
        _sp.set_perspective(1)
        _sp.set_x(0)
        _sp.set_y(36)

    def step(self):
        _sp=self._sp
        _sp.set_x(_sp.x()+1)
        _sp.set_frame(_sp.x()//4 % 3)


class Demo(Scene):
    stripes_rom = "2bam_sencom"

    next_missile=1

    def on_enter(self):
        super().on_enter()

        # self.texto_intro=Sprite()
        # self.texto_intro.set_strip(STRIPS["texto_intro.png"])
        # self.texto_intro.set_perspective(1)
        # self.texto_intro.set_frame(0)
        # self.texto_intro.set_x(128-self.texto_intro.width()//2)


        # Palette cache
        num_STRIPS, num_palettes = struct.unpack("<HH", director.romdata)
        offsets = struct.unpack_from("<%dL%dL" % (num_STRIPS, num_palettes), director.romdata, 4)
        palette_offsets = offsets[num_STRIPS:]
        self.pal_copy=pal_copy = bytearray(director.romdata[palette_offsets[0]:])
        
        self.pal_ind_blue=find_color_index(pal_copy, 0, 7, 250)
        self.pal_ind_city=find_color_index(pal_copy, 147, 0, 255)
        pal_copy[self.pal_ind_city+1] = randint(128,255)
        pal_copy[self.pal_ind_city+2] = randint(128,255)
        pal_copy[self.pal_ind_city+3] = randint(128,255)

        self.aim=Sprite()
        self.aim.set_strip(STRIPS["crosshair.png"])
        self.aim.set_perspective(1)
        self.aim.set_frame(0)
        self.aim_x=1
        self.aim_y=0

        self.cities=[City(i*255//5) for i in range(NUM_CITIES)]
        self.booms=[Boom() for _ in range(MAX_WEAPON)]

        self.core=Sprite()
        self.core.set_strip(STRIPS["core.png"])
        self.core.set_y(160)
        self.core.set_frame(0)
        self.core.set_perspective(0)

        # FIXME: los trailes por separado (menor prioridad?)
        self.missiles=[Missile() for _ in range(MAX_ATTACKS)]

        self.bombs=[EnemyBomb()]

        bg_black=Sprite()
        bg_black.set_strip(STRIPS["bg_black.png"])
        bg_black.set_y(255)
        bg_black.set_frame(0)
        bg_black.set_perspective(0)





    def step(self):
        # povdisplay.set_palettes(palette)
        
        # Boom-Enemy Collisions
        for boom in self.booms:
            if not boom.alive:
                continue
            boom.step()
            for missile in self.missiles:
                bx=boom.x & 0xff
                by=boom.y & 0xff
                if missile.alive:
                    dx=(missile.hit_x & 0xff) - bx
                    dy=(missile.hit_y & 0xff) - by
                    if dx*dx+dy*dy < BOOM_RADIUS_POW2:
                        missile.kill()
                    else:
                        dx=((missile.hit_x+128) & 0xff)-(bx+128)&0xff
                        if dx*dx+dy*dy < BOOM_RADIUS_POW2:
                            missile.kill()


        if self.pal_ind_blue:
            self.pal_copy[self.pal_ind_city+1]=self.pal_copy[self.pal_ind_blue+1]=randint(0,255)
            self.pal_copy[self.pal_ind_city+2]=self.pal_copy[self.pal_ind_blue+2]=randint(0,255)
            self.pal_copy[self.pal_ind_city+3]=self.pal_copy[self.pal_ind_blue+3]=randint(0,255)
            povdisplay.set_palettes(self.pal_copy)


        cities_alive=[]
        cities_dead=0
        for city_index, city in enumerate(self.cities):
            if city.state == CITY_OK:
                cities_alive.append(city_index)
            elif city.state == CITY_DEAD:
                cities_dead+=1
            city.step()
        
        if cities_dead == NUM_CITIES:
            # TODO: LOSE STATE
            director.pop()
            #raise StopIteration()
            return

        for bomb in self.bombs:
            bomb.step()

        self.next_missile -= 1
        for missile in self.missiles:
            if not missile.alive:
                if len(cities_alive) > 0 and self.next_missile == 0:
                    self.next_missile = 30 # TODO: level defined

                    target_city=choice(cities_alive)

                    missile.reset(
                        target_city,
                        target_city*255//NUM_CITIES+randint(-10, 10),
                        randint(0, len(MISSILE_ANGLES)-1),
                        BASE_SPEED
                    )
                else:
                    continue     
            else:               
                missile.step()
                if missile.hit_ground:
                    # self.missile.reset(128, randint(0, 6))
                    # missile.reset(randint(0,255), randint(0, 6), BASE_SPEED)
                    self.cities[missile.target_city].explode()
                    missile.alive = False
                    #TODO: remove life from player

        
        # if director.was_pressed(director.JOY_UP):
        #     self.missile.depth += 1
        #     print(self.missile.depth)
        # if director.was_pressed(director.JOY_DOWN):
        #     self.missile.depth -= 1
        #     print(self.missile.depth)
        # if director.is_pressed(director.JOY_UP):
        #     self.texto_intro.set_y(self.texto_intro.y()+1)
        # if director.is_pressed(director.JOY_DOWN):
        #     self.texto_intro.set_y(self.texto_intro.y()-1)
        
        self.update_aim()

        if director.was_pressed(director.BUTTON_A):
            boom = find_dead(self.booms)
            if boom is not None:
                boom.reset(self.aim_a, self.aim_l, 60)
            else:
                pass #TODO: SFX empty
        
            
        if director.was_pressed(director.BUTTON_D):
            director.pop()
            raise StopIteration()
    
    def update_aim(self):
        aim_speed=0.1 if director.is_pressed(director.BUTTON_A) else 0.05
        # aim_speed=0.1 if director.is_pressed(director.BUTTON_B) else 0.05
        if director.is_pressed(director.JOY_LEFT):
            self.aim_x -= aim_speed
        if director.is_pressed(director.JOY_RIGHT):
            self.aim_x += aim_speed
        if director.is_pressed(director.JOY_UP):
            self.aim_y += aim_speed
        if director.is_pressed(director.JOY_DOWN):
            self.aim_y -= aim_speed

        self.aim_x = min(max(-INV_SQRT2, self.aim_x), INV_SQRT2)
        self.aim_y = min(max(-INV_SQRT2, self.aim_y), INV_SQRT2)
        
        l_p2=round(54*sqrt(self.aim_x**2 + self.aim_y**2))
        self.aim_l=l=INV_DEEPSPACE[l_p2]
        self.aim_a=a=round(192-atan2(self.aim_y,self.aim_x)*128/pi)

        self.aim.set_x(a - self.aim.width()//2)  #TODO: optimizar esto a una constante
        self.aim.set_y(l - self.aim.height()//2)
        if 0<=l<AIM_LIMIT:
            self.aim.set_frame(l//4)

CITY_OK=0
CITY_DYING=2
CITY_DEAD=8
class City:
    def __init__(self, x):
        self._sp=_sp=Sprite()
        _sp.set_strip(STRIPS["city.png"])
        _sp.set_perspective(1)
        _sp.set_x(x-_sp.width()//2)
        _sp.set_y(74)
        self.reset()

    def explode(self):
        if self.state == CITY_OK:
            self._t = 0
            self.state = CITY_DYING
    

    def reset(self):
        self.done=False
        self._t = 0
        self.state = CITY_OK
        self._sp.set_frame(CITY_OK)

    def step(self):
        _sp=self._sp
        st=self.state
        if st == CITY_OK:
            self._t += SECONDS_PER_STEP/0.25
            _sp.set_frame(CITY_OK+int(self._t)%2)
        elif st == CITY_DYING:
            self._t += SECONDS_PER_STEP/0.5
            fi = CITY_DYING+int(self._t)
            if fi == CITY_DEAD:
                self.state=CITY_DEAD
                _sp.disable()
            else:
                _sp.set_frame(fi)



        



def main():
    return Demo()

INV_DEEPSPACE=[255, 190, 167, 153, 143, 135, 128, 122, 116, 111, 107, 103, 99, 95, 92, 88, 85, 82, 79, 77, 74, 72, 69, 67, 64, 62, 60, 58, 56, 54, 52, 50, 48, 46, 45, 43, 41, 39, 38, 36, 35, 33, 32, 30, 29, 27, 26, 24, 23, 22, 20, 19, 18, 16, 15]