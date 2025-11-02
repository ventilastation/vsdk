# Senile command
# Ayuda al motor del ventilador a evitar que los dedos geriatricos lo atasquen.
# 2bam.com 2025

# Controles: Flechas                   : Movimiento
#            Boton A      (emu: SPACE) : Dispara
#            Mantener boton A          : Activa movimiento rapido

# TODO: REVISAR SCORE: Ojo de usar el centro q tiene una tapita en el de españa

# TODO ^: Que tambien haya impacto en el suelo (te resta puntos groso pero no perdes) -- igual q apunte "mas" hacia los edificios
# TODO ^: Wave wait all enemies dead before next step or max_time? -- or stop waiting? min_time
# TODO ^: Tweak missile Y speed (per level)
# TODO ^: Better explosions for player - COlor de paleta "glitch" para explosiones tuyas

# TODO ^: End of level animation / change level
#         Score numbers "lifted up" --> y=24
#         Add buildings alive to score (remove from screen)
#         Add score per hit rate
#         (Add inflation multiplier here?)
#         Is it hiscore? "HI"
#         Flush effect for sprites
#         End of level warp fx (paleta y efecto loco del fullscreen
#         Efecto loco con texto_intro en perspective 2 yendo hacia adentro!

#        
# TODO: Intro (Game)
# TODO: Score change palette to black, then flashy on EOL
# TODO ^: SFX placeholder
# TODO^: Level progression
# TODO^: Define waves
# TODO: Define overwave

# TODO: Enemigo2 bomba q cambia de direccion sin estela mas dificil
# TODO: better SFX
# TODO: Integrate new finger sprites
# TODO: Finger skins
# TODO v: Perder "traba" el ventilador (imagen)

# NO: Estela azul para tus misiles/delay?
# NO: Bonus points con misiles no usados y ciudades no destruidas

# TODO v: animacion (wiggle onda 2bam demo) del score cuando cambia
# TODO v: almacenar score somehow?

# Game scene sprite budget
#    1 BG fan move (FS)
#    1 BG fan stop (FS)
#    1 center core
#    1 crosshair/aim
#    5 cities            NUM_CITIES
#    4 booms             MAX_WEAPON
#   20 missiles (trail+warhead)
#    1 "WARNING" circle
#    6 score
#    ? bombs
# ------------------
#   40 total 

from urandom import choice, randint, seed
from utime import ticks_ms, ticks_diff, ticks_add
from ventilastation.director import director, stripes as STRIPS
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from math import sqrt, atan2, floor, copysign, sin,cos, pi, ceil
import gc

from ventilastation import povdisplay
import struct

STEPS_PER_SECOND=33
SECONDS_PER_STEP=1.0/STEPS_PER_SECOND
AIM_LIMIT=110

INV_SQRT2=0.70710678

#15frames 72x36 step 12 
# TRAIL_FRAMES=8
#TRAIL_FRAMES=15
#73x36
TRAIL_SUB_FRAMES=3
TRAIL_LINE_HW=1.5

MISSILE_ANGLES =  [-65,-45, 0, 45, 65]
MISSILE_SINS=[sin(deg*pi/180) for deg in MISSILE_ANGLES]
TRAIL_FRAME_HEIGHT=40
TRAIL_FRAME_WIDTH=105
TRAIL_X_OFFSETS=[-(round(TRAIL_FRAME_HEIGHT*sin(deg*pi/180)/cos(deg*pi/180))+(TRAIL_FRAME_WIDTH-2 if deg <= 0 else 2)) for deg in MISSILE_ANGLES]
MISSILE_XXX=[sin(deg*pi/180)/cos(deg*pi/180) for deg in MISSILE_ANGLES]
TRAIL_SEQ_FRAME_COUNT=7
TRAIL_Y_PER_FRAME=6
WARHEAD_ORIGIN_Y=2

print("TRAIL_X_OFFSETS", TRAIL_X_OFFSETS)
# MISSILE_ANGLES = [-60,-40,-20, 0, 20, 40, 60]

# 32 limit is due to how trails work (they kind of wrap around but are hidden
# by the center image, if they were longer it would require special case math
MISSILE_MAX_DEPTH=40
MISSILE_Y_SPEED=0.25
WARHEAD_FRAMES=3

NUM_CITIES=5
MAX_WEAPON=4
MAX_ATTACKS=20

BOOM_FRAMES=[0,1,2,3,2,3,2,3,2,1,0]
BOOM_RADIUS_POW2=10*10

palette=bytearray([randint(0,255) for _ in range(1024*6)])

P_FULLSCREEN=0
P_DISTORTED=2
def make_sprite(name, x=0, y=0, persp=1):
    s=Sprite()
    s.set_strip(STRIPS[name+".png"])
    s.set_perspective(persp)
    s.set_x(x)
    s.set_y(y)
    s.disable()
    return s

def find_color_index(pal, r,g,b):
    for i in range(0, len(pal), 4):
        if pal[i+1] == b and pal[i+2] == g and pal[i+3] == r:
            print('COLOR FOUND',r,g,b, 'AT', i)
            return i

    print('COLOR NOT FOUND',r,g,b)
    return 254

class Entity:
    alive=False
    hit_x=-1000
    hit_y=-1000
    sprite=None
    def step():
        pass

class Boom:
    def __init__(self):
        self.sprite=make_sprite("target")
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



        self.trail=make_sprite("trail", persp=P_DISTORTED)
        self.trail_hw=self.trail.width()//2
        self.alive=False

    def reset(self, target_city, target_x, angle_index, speed):
        self.angle_index=angle_index
        #self.base_x=base_x-16
        self.target_city=target_city
        self.base_x=target_x-round(MISSILE_XXX[angle_index]*TRAIL_FRAME_HEIGHT)
        self.trail.set_x(target_x+TRAIL_X_OFFSETS[angle_index])
        self.trail_base_frame = TRAIL_SEQ_FRAME_COUNT*angle_index
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
        if self.hit_ground:
            return

        self.depth+=self.speed
        if self.depth >= MISSILE_MAX_DEPTH:
            self.hit_ground=True

        d = floor(self.depth)
        bx = self.base_x

        # The trail grows in "steps", approx 6px (TRAIL_Y_PER_FRAME), and the idea is that it
        # gets totally hidden by the finger, which is the one that actually moves towards the center.
        if d < TRAIL_Y_PER_FRAME:
            self.trail.disable()
            # TODO: warhead set_frame que se va asomando pero no cambia el Y solo el X
        else: 
            self.trail.set_frame(self.trail_base_frame+d//TRAIL_Y_PER_FRAME-1)        


        sin_rad=MISSILE_SINS[self.angle_index]
        # off_x_bis = int(bx-self.trail_hw + TRAIL_LINE_HW + sin_rad * (d))#-sin_rad*MISSILE_MAX_DEPTH)
        # self.trail.set_y(d)  # HACK: Wrap around center and hide that with the Core
        # self.trail.set_x( off_x_bis)
        # self.trail.set_frame(self.angle_index*TRAIL_SUB_FRAMES + d//TRAIL_STEP)

        # self.trail.set_frame(d//TRAIL_STEP)
        
        off_x = int(sin_rad * self.depth)
        wx=bx+off_x
        wx=bx+int(MISSILE_XXX[self.angle_index]* self.depth)
        #wy=42+d+self.warhead.height()
        #wy=(42+d+self.warhead.height())%54
        # wy=d-self.warhead.height()+WARHEAD_ORIGIN_Y
        wy=d-self.warhead.height()+WARHEAD_ORIGIN_Y
        self.warhead.set_x(wx-self.warhead_hw)
        self.warhead.set_y(wy)
        self.warhead.set_frame(d%WARHEAD_FRAMES)
        self.hit_x=wx
        if 0 <= d < 54:
            self.hit_y=INV_DEEPSPACE[54-d] # TODO: lerp [d] y [d+1] usando self.depth?    
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

class Anim(Entity):
    def __init__(self, strip_id, frames, duration_secs, **kwargs):
        super().__init__()
        self.sprite=make_sprite(strip_id, **kwargs)
        self.sprite.set_frame(frames[0])
        self._frames=frames
        self._fracIndex=0
        self._fracInc=SECONDS_PER_STEP*len(frames)/duration_secs
        self.alive=True
    
    def step(self):
        super().step()
        self._fracIndex += self._fracInc
        self._fracIndex %= len(self._frames)
        self.sprite.set_frame(self._frames[floor(self._fracIndex)])


class Game(Scene):
    quit=False
    score=0
    level=0




    def save_score():
        # TODO
        pass

    def on_enter(self):
        super().on_enter()
        # TODO: load score
        pass

    def step(self):
        if self.quit:
            director.pop()
            raise StopIteration()
        else:
            director.push(Combat(self))

class Warning(Entity):
    def __init__(self):
        super().__init__()
        self.sprite=make_sprite("warning", persp=P_DISTORTED)
        self.tmr=0
        self.alive=False

    def activate(self):
        # TODO sound here?
        self.tmr=3*STEPS_PER_SECOND
        self.alive=True

    def step(self):
        if self.tmr > 0:
            self.tmr-=1
            self.sprite.set_x(self.sprite.x()+1)
            self.sprite.set_frame(0 if (self.tmr //12) % 3 > 0 else 255)
            if self.tmr <= 0:
                self.sprite.disable()
                self.alive=False


class Combat(Scene):
    stripes_rom = "2bam_sencom"

    next_missile=1

    def __init__(self, game):
        super().__init__()
        self.game=game

    def on_enter(self):
        super().on_enter()

        self.ents=[]

        self.waves=Waves(level_waves[self.game.level])

        self.warning=Warning()
        # self.warning.activate()
        self.ents.append(self.warning)

        self.score=ScoreTopLabel("font_hiscore_16px_top", digit_count=6, y=42, char_width=16)

        seed(ticks_ms())

        # self.texto_intro=Sprite()
        # self.texto_intro.set_strip(STRIPS["texto_intro.png"])
        # self.texto_intro.set_perspective(1)
        # self.texto_intro.set_frame(0)
        # self.texto_intro.set_x(128-self.texto_intro.width()//2)
        if False:
            def calc_target_offset(angle_index):
                return TRAIL_X_OFFSETS[angle_index]
            i=0
            a=Anim("trail", [255]+list(range(i,i+7)), 2, persp=P_DISTORTED)
            a.sprite.set_x(calc_target_offset(0))
            self.ents.append(a)
            i+=7
            a=Anim("trail", [255]+list(range(i,i+7)), 2, persp=P_DISTORTED)
            a.sprite.set_x(calc_target_offset(1))
            self.ents.append(a)
            i+=7
            a=Anim("trail", [255]+list(range(i,i+7)), 2, persp=P_DISTORTED)
            a.sprite.set_x(calc_target_offset(2))
            self.ents.append(a)
            i+=7
            a=Anim("trail", [255]+list(range(i,i+7)), 2, persp=P_DISTORTED)
            a.sprite.set_x(calc_target_offset(3))
            self.ents.append(a)
            i+=7
            a=Anim("trail", [255]+list(range(i,i+7)), 2, persp=P_DISTORTED)
            a.sprite.set_x(calc_target_offset(4))
            self.ents.append(a)
            i+=7

        # lala = make_sprite("trail", persp=P_DISTORTED)
        # lala.set_frame(3)
        # lala = make_sprite("trail", persp=P_DISTORTED)
        # lala.set_frame(7)
        # lala = make_sprite("trail", persp=P_DISTORTED)
        # lala.set_frame(11)

        # lala = make_sprite("trail")
        # lala.set_frame(3)
        # lala.set_x(128)
        # lala = make_sprite("trail")
        # lala.set_frame(7)
        # lala.set_x(128)
        # lala = make_sprite("trail")
        # lala.set_x(128)
        # lala.set_frame(11)


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
        # self.core.disable()

        # FIXME: los spawnear trailes por separado (menor prioridad visual z-index)
        self.missiles=[Missile() for _ in range(MAX_ATTACKS)]

        #self.bombs=[EnemyBomb()]
        self.bombs=[]

        bg_black=Sprite()
        bg_black.set_strip(STRIPS["bg_black.png"])
        bg_black.set_y(255)
        bg_black.set_frame(0)
        bg_black.set_perspective(0)

    def spawn_missile(self, cities_alive, angles):
        y_speed = MISSILE_Y_SPEED # TODO: div by level (or overlevel)
        for missile in self.missiles:
            if not missile.alive:
                if len(cities_alive) > 0:
                    target_city=choice(cities_alive)
                    missile.reset(
                        target_city,
                        target_city*255//NUM_CITIES+randint(-10, 10),
                        choice(angles),
                        y_speed
                    )
                return
        print('NOT ENOUGH MISSILES TO SPAWN', len(self.missiles))

    def step(self):


        # povdisplay.set_palettes(palette)
        for ent in self.ents:
            if ent.alive:
                ent.step()


        
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
                    hit=False
                    if dx*dx+dy*dy < BOOM_RADIUS_POW2:
                        hit=True
                    else:
                        dx=((missile.hit_x+128) & 0xff)-(bx+128)&0xff
                        if dx*dx+dy*dy < BOOM_RADIUS_POW2:
                            hit=True
                    if hit:
                        missile.kill()
                        self.game.score += 125 # TODO: inflation per level/type
                        self.score.set_score(self.game.score)


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
            # Deactivate random missiles TODO: reactivate at high levels
            # if not missile.alive:
            #     if len(cities_alive) > 0 and self.next_missile == 0:
            #         self.next_missile = 3 * STEPS_PER_SECOND # TODO: level defined

            #         target_city=choice(cities_alive)

            #         missile.reset(
            #             target_city,
            #             target_city*255//NUM_CITIES+randint(-10, 10),
            #             randint(0, len(MISSILE_ANGLES)-1),
            #             MISSILE_Y_SPEED
            #         )
            #     else:
            #         continue     
            # else:           
            if missile.alive:    
                missile.step()
                if missile.hit_ground:
                    # self.missile.reset(128, randint(0, 6))
                    # missile.reset(randint(0,255), randint(0, 6), MISSILE_Y_SPEED)
                    self.cities[missile.target_city].explode()
                    missile.kill()
                    # missile.alive = False
                    #TODO: remove life from player

        next_spawn = self.waves.next()
        if next_spawn == W_WARN:
            self.warning.activate()
        elif next_spawn == W_COMPLETE:
            # TODO!!
            pass
        elif next_spawn == W_M0:
            self.spawn_missile(cities_alive, [2]) #[0]
        elif next_spawn == W_M1:
            self.spawn_missile(cities_alive, [1,2,3]) #[-45, 0, 45]
        elif next_spawn == W_M2:
            self.spawn_missile(cities_alive, [0,1,2,3,4]) #[-65,-45, 0, 45, 65]



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
            self.game.quit=True
            director.pop()
            raise StopIteration()
    
    def update_aim(self):
        aim_speed=0.1 if director.is_pressed(director.BUTTON_A) else 0.05
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

        self.aim.set_x(a - self.aim.width()//2)
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



        

class ScoreTopLabel:
    # Score font id should be a strip with 0-9 numbers first and any string you
    # want to show before the number should be after it in the strip, e.g.
    # "0123456789HI" will be optionally shown as HI##### in-game.
    def __init__(self, score_font_id, digit_count, char_width=8, y=0):
        self.digits = []
        x0 = 128-int((digit_count-.5)*char_width/2)
        for i in range(digit_count):
            s = make_sprite(score_font_id, x=x0+i*char_width, y=y, persp=P_DISTORTED)
            self.digits.append(s)
            s.set_frame(i)

        self.base_y=y
        self.frame=0
        self.set_score(0)

    def set_score(self,num):
        self.score = num 
        i=len(self.digits)-1
        while i >= 0:
            self.digits[i].set_frame(num % 10)
            num //= 10
            i -= 1

    def highlight_digit(self, jump_index, jump_size=-4):
        for sp in self.digits: 
            sp.set_y(self.base_y)
        self.digits[jump_index].set_y(self.base_y+jump_size)



def main():
    return Game()

INV_DEEPSPACE=[255, 190, 167, 153, 143, 135, 128, 122, 116, 111, 107, 103, 99, 95, 92, 88, 85, 82, 79, 77, 74, 72, 69, 67, 64, 62, 60, 58, 56, 54, 52, 50, 48, 46, 45, 43, 41, 39, 38, 36, 35, 33, 32, 30, 29, 27, 26, 24, 23, 22, 20, 19, 18, 16, 15]


# WAVES

W_NONE=0
W_WARN=1
W_COMPLETE=2
W_M0=10
W_M1=11
W_M2=12
W_B0=20
W_B1=21
level_waves=[
    # ------- LEVEL 1 -------
    [
        #  ,----------- Duration seconds (will extend to amount steps if too low)
        # |  ,--------- Amount
        # |  |   ,---- Enemy shuffle bag 
        ( 3, 0, []          ),
        (10, 5, [W_M0]      ),
        ( 3, 0, []          ),
        ( 4, 4, [W_M0,W_M1] ),
        ( 3, 0, []          ),
        ( 3, 1, [W_WARN]    ),
        ( 0, 5, [W_M0]      ),
    ],
]

class Waves:
    def __init__(self, waves):
        self.step=0
        self.done=False
        self.warn=False
        self.waves=waves

        self.next_waves_i=0
        self.load_next_wave()
    
    def load_next_wave(self):
        (secs, wave_spawn_amount, bag) = self.waves[self.next_waves_i]
        print('load wave', self.next_waves_i, secs, wave_spawn_amount, bag)
        # Max between wanted seconds, and being able to spawn at least all!
        self.wave_tmr = max(wave_spawn_amount, ceil(STEPS_PER_SECOND*secs))
        self.spawn_pending=wave_spawn_amount
        self.spawn_period= 0 if wave_spawn_amount==0 else self.wave_tmr//wave_spawn_amount
        self.spawn_tmr=0 
        self.next_spawn_i=0
        self.bag=bag
        self.shuffle()
        self.next_waves_i += 1

    def shuffle(self):
        for i in range(1, len(self.bag)):
            j = randint(0,i)
            tmp=self.bag[i]
            self.bag[i]=self.bag[j]
            self.bag[j]=tmp

    def next(self): 
        self.wave_tmr -= 1
        if self.wave_tmr <= 0:
            if self.next_waves_i >= len(self.waves):
                return W_COMPLETE
            self.load_next_wave()

        if self.spawn_pending > 0 and len(self.bag) > 0:
            self.spawn_tmr -= 1
            if self.spawn_tmr <= 0:
                to_spawn = self.bag[self.next_spawn_i]
                self.spawn_tmr = self.spawn_period
                self.next_spawn_i += 1
                if self.next_spawn_i == len(self.bag):
                    self.shuffle()
                    self.next_spawn_i = 0
                self.spawn_pending -= 1
                return to_spawn


        return W_NONE


