# Senile command v.2511
# Ayuda al motor del ventilador a evitar que los dedos geriatricos lo atasquen.
# 2bam.com 2025
#
#                              En una galaxia lejana,
#                                  en el planeta
#                                 Arg-n-tina ZX25
#                              ancianos sub medicados
#                              cegados por atractivos
#                            colores ingresan sus dedos
#                            a la imparcial maquinaria...
#                             
#                              ¿Quién podra salvar el
#                                  venti-núcleo?
#
# Reglas     Dispararle a los dedos que caen antes de que impacten los motores
#            magicos que hacen funcionar el Ventilastation.
#            Si no quedan motores se pierde el juego.
#
# Puntos     +125 puntos  : Dedo destruido
#            -250 puntos  : Impacto directo al nucleo 
#            +1000 puntos : Por cada motor que sobreviva hasta el fin del nivel.
#            NOTA: El impacto enemigo a un motor no quita puntos,
#                  los proyectiles propios tampoco los afectan.
#
# Controles                      Flechas : Movimiento
#                   Boton A (emu: SPACE) : Dispara
#                       Mantener boton A : Activa movimiento rapido




# MEMO: En perspectiva 2, mas al centro que y=54-7, esos ultimos 7px por ahi
# estan cubiertos por la tapa del ventilador de madrid.

# TODO ^^^: LOSE SCREEN!



# TODO ^: End of level animation / change level
#         DONE: Score numbers "lifted up" --> y=24
#         DONE: Add buildings alive to score (remove from screen)
#         Add score per hit rate - HIT 78% (baja el numbero sube el score)
#         End of level warp fx (paleta y efecto loco del fullscreen)
#           - en vez de zoom del core, zoom de una espiral
#         Is it hiscore? HI SCORE label en tally
#         NO: Flush effect for sprites


# FIXME^^^: extend boom Y using INV_DEEPSPACE_DELTA
# FIXME^^^: use depth (persp=2) collisions instead!!
# FIXME^^^: player explosions not always hit right

# TODO: Intro (Game) -- Senile command title arriba, hiscore y la historia subiendo fragmentada. Efecto loco con texto_intro en perspective 2 yendo hacia adentro!
# TODO: Enemigo q cambia de direccion sin estela mas dificil
# TODO: Enemigo q cae en espiral larga (diagonal polar), da ponele 3 vueltas completas antes de impactar
# TODO: Enemigo cae en espiral hasta cierto pos-y luego cambia a vertical y cae derecho
#       --variante que randomiza la diagonal entre centro -45, 0, 45°
# TODO: "Navecita Bonus", destornillador?

# TODO^: Define waves
# TODO: Define overwave

# FIXME: WH_MODE=1 needs perspective adjusted trail lengths if used

# TODO ^: Tweak missile Y speed (per level)
# TODO ^: Better explosions for player - COlor de paleta "glitch" para explosiones tuyas
# TODO ^: Wave wait all enemies dead before next step or max_time? -- or stop waiting? min_time

# TODO: better SFX
# TODO: Integrate new finger sprites
# TODO v: Explosions more like "aim/crosshair" size-compensated for looped damage frames (frame index: depth <-> depth-1)
# TODO v: Finger skins
# TODO v: Perder "traba" el ventilador (imagen) -- SFX clank!
# TODO v: score inflation

# TODO v: animacion (wiggle onda 2bam demo) del score cuando cambia
# TODO v: persistir hiscore somehow?
# TODO v: End of level music

# DONE^: Level progression
# DONE ^: shuffle bag target city (double, triple size bag for less predictability)
# DONE ^: Red alert 1 building
# DONE ^: Que tambien haya impacto en el suelo (te resta puntos groso pero no perdes)
# DONE: Score change palette to black, then flashy on EOL
# DONE ^: SFX placeholder
# NO: Estela azul para tus misiles/delay?
# NO: Bonus points con misiles no usados y ciudades no destruidas

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

HISCORE=0

INV_SQRT2=0.70710678

#15frames 72x36 step 12 
# TRAIL_FRAMES=8
#TRAIL_FRAMES=15
#73x36
TRAIL_SUB_FRAMES=3
TRAIL_LINE_HW=1.5

WARHEAD_STRIP_IDS=["dedo-frames65","dedo-frames45","dedo-frames0","dedo-frames45-neg","dedo-frames65-neg"]
MISSILE_ANGLES =  [-65,-45, 0, 45, 65]
MISSILE_SINS=[sin(deg*pi/180) for deg in MISSILE_ANGLES]
TRAIL_FRAME_HEIGHT=40
TRAIL_FRAME_WIDTH=105
TRAIL_X_OFFSETS=[-(round(TRAIL_FRAME_HEIGHT*sin(deg*pi/180)/cos(deg*pi/180))+(TRAIL_FRAME_WIDTH-2 if deg <= 0 else 2)) for deg in MISSILE_ANGLES]
#print("TRAIL_X_OFFSETS", TRAIL_X_OFFSETS)
MISSILE_XXX=[sin(deg*pi/180)/cos(deg*pi/180) for deg in MISSILE_ANGLES]
TRAIL_SEQ_FRAME_COUNT=7
TRAIL_Y_PER_FRAME=6
WARHEAD_ORIGIN_Y=2

# MISSILE_ANGLES = [-60,-40,-20, 0, 20, 40, 60]

# 32 limit is due to how trails work (they kind of wrap around but are hidden
# by the center image, if they were longer it would require special case math
MISSILE_MAX_DEPTH=40
MISSILE_Y_SPEED=0.20
WARHEAD_LOOP_START=10
WARHEAD_LOOP_FRAMES=3

NUM_CITIES=5
MAX_WEAPON=4
MAX_ATTACKS=20

#BOOM_FRAMES=[0,1,2,3,2,3,2,3,2,1,0]
BOOM_FRAMES=[ 4, 3, 2, 3, 2, 3,2, 3,2, 3, 2, 1, 0]
BOOM_RADIUS=[0,0,10,10,5]
BOOM_TTL=99#60

palette=bytearray([randint(0,255) for _ in range(1024*6)])

P_FULLSCREEN=0
P_DISTORTED=2
def make_sprite(name, x=0, y=0, persp=1, frame=255):
    s=Sprite()
    s.set_strip(STRIPS[name+".png"])
    s.set_perspective(persp)
    s.set_x(x)
    s.set_y(y)
    s.set_frame(frame)
    return s

# SND_WARNING=b"2bam_sencom/test/531488__rickplayer__alarmalert.mp3"
SND_WARNING=b"2bam_sencom/warning" # TODO: recortar en tiempo
SND_EMPTY_CLIP=b"2bam_sencom/empty-clip"
SND_RED_ALERT=b"2bam_sencom/red-alert"
SND_CITY_EXPLODE=b"2bam_sencom/city-explode" # LPF menos chillon o pitch down
SND_CORE_HIT=b"2bam_sencom/core-hit"
SND_BOOM=b"2bam_sencom/boom"
SND_TALLY_CITY=b"2bam_sencom/plin"
SND_TALLY_POINT=b"2bam_sencom/plinito"
SND_TALLY_END=b"2bam_sencom/tally-end"
SNDS_SPAWN=[
    b"2bam_sencom/chop0",
    b"2bam_sencom/chop1",
    b"2bam_sencom/chop2",
]
SND_NEW_LEVEL=b"2bam_sencom/new-level"

#SND_BOOM=b"2bam_sencom/test/434751__djfroyd__monster-kick.wav"

# Faltan: lose, level win, score raising, city counting

def find_color_index(pal, r,g,b):
    for i in range(0, len(pal), 4):
        if pal[i+1] == b and pal[i+2] == g and pal[i+3] == r:
            #print('COLOR FOUND',r,g,b, 'AT', i)
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

class Boom(Entity):
    def __init__(self):
        self.sprite=make_sprite("target")
        self.alive=False
        self.do_damage=False
    
    def reset(self, x, y, ttl):
        self.fpst = len(BOOM_FRAMES)/ttl
        self.frame = 0
        self.radius = 0
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
            self.do_damage=False
            self.sprite.disable()
            return
        real_frame=BOOM_FRAMES[fi]
        self.radius=BOOM_RADIUS[real_frame]
        self.do_damage=self.radius > 0
        self.sprite.set_frame(real_frame)

WH_MODE=2

class Missile:
    angle_index=0
    depth=0
    base_x=0
    hit_ground=False
    def __init__(self, warhead_sprite):
        # self._debug=Sprite()
        # self._debug.set_strip(STRIPS["crosshair.png"])
        # self._debug.set_perspective(1)
        # self._debug.set_frame(0)
        
        self.warhead=warhead_sprite

        # TODO: Remove this, already done in reset
        self.warhead.set_strip(STRIPS["dedo.png"])
        self.warhead.set_perspective(WH_MODE)
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
        self.warhead.set_strip(STRIPS[WARHEAD_STRIP_IDS[angle_index]+".png"])
        self.warhead_hw=self.warhead.width()//2
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
        if WH_MODE == 2:
            wy=d-self.warhead.height()+WARHEAD_ORIGIN_Y
        elif WH_MODE == 1:
            k=INV_DEEPSPACE[53-MISSILE_MAX_DEPTH]
            wy=(d*k//MISSILE_MAX_DEPTH)-self.warhead.height()+WARHEAD_ORIGIN_Y

        if d < 10:
            still_off_x = int(sin_rad * 10)
            still_x=bx+off_x
            #self.warhead.set_x(bx-self.warhead_hw)
            self.warhead.set_x(still_x-self.warhead_hw)
            self.warhead.set_y(0)
            self.warhead.set_frame(d)
        else:
            self.warhead.set_x(wx-self.warhead_hw)
            #self.warhead.set_x(-self.warhead_hw)
            self.warhead.set_y(wy)
            self.warhead.set_frame(WARHEAD_LOOP_START+d%WARHEAD_LOOP_FRAMES)

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
        self.sprite=sprite=Sprite()
        sprite.set_strip(STRIPS["dedo2.png"])
        sprite.set_perspective(1)
        sprite.set_x(0)
        sprite.set_y(36)

    def step(self):
        sprite=self.sprite
        sprite.set_x(sprite.x()+1)
        sprite.set_frame(sprite.x()//4 % 3)

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
    # Normalized cartesian x and y [-1.0, 1.0]
    aim_cart_x=0
    aim_cart_y=0.5

    def reset(self):
        self.score=0
        self.level=0

    def save_score():
        HISCORE=max(HISCORE, self.score)
        # TODO: persist
        pass

    def on_enter(self):
        super().on_enter()
        # MEMO: This also gets called when the Combat state pops
        # NO!!: self.reset()
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
        director.sound_play(SND_WARNING)
        self.tmr=0.707*4*STEPS_PER_SECOND
        self.alive=True

    def step(self):
        if self.tmr > 0:
            self.tmr-=1
            self.sprite.set_x(self.sprite.x()+1)
            self.sprite.set_frame(0 if (self.tmr // 7) % 3 > 0 else 255)
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

        self.tally=False#True
        self.tally_tmr=0

        self.all_cities=ShuffleBag(2*list(range(NUM_CITIES)))
        self.cities_alive=ShuffleBag(list(range(NUM_CITIES)))
        self.ents=[]
        print(self.game.level, 'level')
        self.waves=Waves(level_waves[min(self.game.level, len(level_waves)-1)])


        self.aim=make_sprite("crosshair", frame=0)



        self.warning=Warning()
        # self.warning.activate()
        self.ents.append(self.warning)

        self.score=ScoreTopLabel("font_hiscore_16px_top", digit_count=6, y=41, char_width=16)
        self.score.set_score(self.game.score)

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
        self.pal_ind_blue=find_color_index(pal_copy, 0, 7, 250)
        self.pal_ind_city=find_color_index(pal_copy, 147, 0, 255)
        self.pal_ind_score=find_color_index(pal_copy, 0, 255, 0)
        pal_copy[self.pal_ind_city+1] = randint(128,255)
        pal_copy[self.pal_ind_city+2] = randint(128,255)
        pal_copy[self.pal_ind_city+3] = randint(128,255)
        pal_copy[self.pal_ind_score+1] = 0
        pal_copy[self.pal_ind_score+2] = 0
        pal_copy[self.pal_ind_score+3] = 0

        # TODO: Change by level color!
        if self.game.level < len(level_colors):
            level_color=level_colors[self.game.level]
        else:
            level_color=(randint(0,255)|0x80,0,randint(0,255)|0x80)
        self.set_color_core(*level_color)



        self.pal_ind_boom=find_color_index(pal_copy, 0, 0xff, 0xf0)



        self.cities=[City(i*255//5) for i in range(NUM_CITIES)]
        self.cities_dead=0
        self.booms=[Boom() for _ in range(MAX_WEAPON)]

        self.core=Sprite()
        self.core.set_strip(STRIPS["core.png"])
        self.core.set_y(164) #160
        self.core.set_frame(0)
        self.core.set_perspective(0)
        # self.core.disable()

        # Spawn warheads first so they have more z-order priority
        warhead_sprites=[Sprite() for _ in range(MAX_ATTACKS)]
        self.missiles=[Missile(warhead_sprite) for warhead_sprite in warhead_sprites]

        #self.bombs=[EnemyBomb()]
        self.bombs=[]

        bg_black=Sprite()
        bg_black.set_strip(STRIPS["bg_black.png"])
        bg_black.set_y(255)
        bg_black.set_frame(0)
        bg_black.set_perspective(0)

    def set_color_core(self,r,g,b):
        if self.pal_ind_blue and self.pal_ind_city:
            self.pal_copy[self.pal_ind_city+1]=self.pal_copy[self.pal_ind_blue+1]=b
            self.pal_copy[self.pal_ind_city+2]=self.pal_copy[self.pal_ind_blue+2]=g
            self.pal_copy[self.pal_ind_city+3]=self.pal_copy[self.pal_ind_blue+3]=r
            povdisplay.set_palettes(self.pal_copy)

    def spawn_missile(self, target_cities_bag, angles):
        y_speed = MISSILE_Y_SPEED # TODO: div by level (or overlevel)
        for missile in self.missiles:
            if not missile.alive:
                if not target_cities_bag.empty:
                    target_city=target_cities_bag.next()
                    
                    missile.reset(
                        target_city,
                        target_city*255//NUM_CITIES+randint(-10, 10),
                        choice(angles),
                        y_speed
                    )
                return
        print('NOT ENOUGH MISSILES TO SPAWN', len(self.missiles))

    def step(self):
        if self.tally:
            self.step_tally()
        else:
            self.step_play()


    def step_tally(self):
        for boom in self.booms:
            boom.sprite.disable()

        # if any(city.state == CITY_DYING for city in self.cities) or any(boom.alive for boom in self.booms):
        #     for city in self.cities:
        #         city.step()
        #     for boom in self.booms:
        #         boom.step()
        #     return

        self.warning.sprite.disable()

        if self.score.y()>10:
            self.score.set_y(self.score.y()-1)
        else:
            self.score.set_y(0)

            city_moved=False
            for city in self.cities:
                if city.state == CITY_OK:
                    city_moved=True
                    s=city.sprite
                    if s.y() > 10:
                        s.set_y(s.y()-2)
                        if s.x() < 116:
                            s.set_x(s.x()+4)
                        elif s.x() > 120:
                            s.set_x(s.x()-4)
                    else:
                        self.game.score += 1000 # TODO: inflation per level/type
                        self.score.set_score(self.game.score)
                        s.disable()
                        city.state=CITY_DEAD
                        director.sound_play(SND_TALLY_CITY)
                    break
            if not city_moved:
                if self.tally_tmr == 0:
                    director.sound_play(SND_TALLY_END)
                self.tally_tmr += 1

                self.core.set_y(min(self.core.y()+3,255))

                if self.tally_tmr >= 2.954*STEPS_PER_SECOND:
                    self.game.level += 1
                    director.sound_play(SND_NEW_LEVEL)
                    director.pop()


                # city.step()
                # if city.state == CITY_OK:
                #     city.explode()
                #     self.game.score += 1000 # TODO: inflation per level/type
                #     self.score.set_score(self.game.score)
                #     break
                # elif city.state == CITY_DYING:
                #     break
            

        self.update_aim()


        if self.pal_ind_score:
            pal=self.pal_copy
            pal[self.pal_ind_score+1] = randint(0,128)
            pal[self.pal_ind_score+2] = randint(0,255)|0x80
            pal[self.pal_ind_score+3] = randint(0,128)
            povdisplay.set_palettes(pal)


    def step_play(self):

        
        pal_i=self.pal_ind_boom
        pal=self.pal_copy
        if pal_i:
            pal[pal_i+1]=randint(0,255)|0x80
            pal[pal_i+2]=randint(0,255)|0x80
            pal[pal_i+3]=randint(0,255)|0x80
            povdisplay.set_palettes(pal)

        # povdisplay.set_palettes(palette)
        for ent in self.ents:
            if ent.alive:
                ent.step()


        
        # Boom-Enemy Collisions
        for boom in self.booms:
            if not boom.alive:
                continue
            boom.step()
            if boom.do_damage:
                for missile in self.missiles:
                    if missile.alive:
                        dx=(missile.hit_x & 0xff) - (boom.x&0xff)
                        dy=missile.hit_y - boom.y
                        hit=False
                        boom_sq_rd=boom.radius*boom.radius
                        if dx*dx+dy*dy <= boom_sq_rd:
                            hit=True
                        else:
                            dx=((missile.hit_x+128) & 0xff)-((boom.x+128)&0xff)
                            if dx*dx+dy*dy <= boom_sq_rd:
                                hit=True
                        if hit:
                            missile.kill()
                            self.game.score += 125 # TODO: inflation per level/type
                            self.score.set_score(self.game.score)


        for city_index, city in enumerate(self.cities):
            city.step()
        
        if self.cities_dead == NUM_CITIES:
            # TODO: LOSE STATE
            self.game.reset()
            director.pop()
            #raise StopIteration()
            return


        frame_enemies_alive=0

        for bomb in self.bombs:
            if bomb.alive:
                bomb.step()
                frame_enemies_alive+=1

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
                frame_enemies_alive+=1
                missile.step()
                if missile.hit_ground:
                    # self.missile.reset(128, randint(0, 6))
                    # missile.reset(randint(0,255), randint(0, 6), MISSILE_Y_SPEED)
                    city = self.cities[missile.target_city]
                    if city.state == CITY_OK:
                        self.cities_alive.remove(missile.target_city)
                        self.cities_dead+=1
                        if self.cities_dead == NUM_CITIES-1:
                            director.sound_play(SND_RED_ALERT)
                            self.set_color_core(255,0,0)


                        director.sound_play(SND_CITY_EXPLODE)
                        city.explode()
                    else:
                        # TODO: lesser explosion sound
                        # TODO: some lesser explosion anim?
                        self.game.score = max(0, self.game.score-250)
                        self.score.set_score(self.game.score)
                        director.sound_play(SND_CORE_HIT)
                        city.re_explode()

                    missile.kill()


        next_spawn = self.waves.next()
        if next_spawn == W_WARN:
            self.warning.activate()
        elif next_spawn == W_COMPLETE:
            if all(city.state != CITY_DYING for city in self.cities) and frame_enemies_alive==0: 
                self.tally=True
        elif next_spawn == W_M0:
            self.spawn_missile(self.all_cities, [2]) #[0]
        elif next_spawn == W_M1:
            self.spawn_missile(self.all_cities, [1,2,3]) #[-45, 0, 45]
        elif next_spawn == W_M2:
            self.spawn_missile(self.all_cities, [0,1,2,3,4]) #[-65,-45, 0, 45, 65]
        elif next_spawn == W_M2CA:
            self.spawn_missile(self.cities_alive, [0,1,2,3,4]) #[-65,-45, 0, 45, 65]

        if W_ENEMY_MIN <= next_spawn < W_ENEMY_MAX:
            director.sound_play(choice(SNDS_SPAWN))


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
                boom.reset(self.aim_a, self.aim_l, BOOM_TTL)
                director.sound_play(SND_BOOM)
            else:
                director.sound_play(SND_EMPTY_CLIP)
        
            
        if director.was_pressed(director.BUTTON_D):
            self.game.quit=True
            director.pop()
            raise StopIteration()
    
    def update_aim(self):
        ax = self.game.aim_cart_x
        ay = self.game.aim_cart_y

        aim_speed=0.1 if director.is_pressed(director.BUTTON_A) else 0.05
        if director.is_pressed(director.JOY_LEFT):
            ax -= aim_speed
        if director.is_pressed(director.JOY_RIGHT):
            ax += aim_speed
        if director.is_pressed(director.JOY_UP):
            ay += aim_speed
        if director.is_pressed(director.JOY_DOWN):
            ay -= aim_speed

        ax = min(max(-INV_SQRT2, ax), INV_SQRT2)
        ay = min(max(-INV_SQRT2, ay), INV_SQRT2)
        
        l_p2=round(54*sqrt(ax*ax + ay*ay))
        self.aim_l=l=INV_DEEPSPACE[l_p2]
        self.aim_a=a=round(192-atan2(ay,ax)*128/pi)

        self.aim.set_x(a - self.aim.width()//2)
        self.aim.set_y(l - self.aim.height()//2)
        if 0<=l<AIM_LIMIT:
            self.aim.set_frame(l//4)

        self.game.aim_cart_x=ax
        self.game.aim_cart_y=ay

CITY_OK=0
CITY_DYING=2
CITY_DEAD=8
class City:
    def __init__(self, x):
        self.sprite=sprite=Sprite()
        sprite.set_strip(STRIPS["city.png"])
        sprite.set_perspective(1)
        sprite.set_x(x-sprite.width()//2)
        sprite.set_y(64)
        # sprite.set_y(74)
        self.reset()

    def explode(self):
        if self.state == CITY_OK:
            self._t = 0
            self.state = CITY_DYING
    
    def re_explode(self):
        if self.state != CITY_OK:
            self._t = 2
            self.state = CITY_DYING

    def reset(self):
        self._t = 0
        self.state = CITY_OK
        self.sprite.set_frame(CITY_OK)

    def step(self):
        sprite=self.sprite
        st=self.state
        if st == CITY_OK:
            self._t += SECONDS_PER_STEP/0.24
            sprite.set_frame(CITY_OK+int(self._t)%2)
        elif st == CITY_DYING:
            self._t += SECONDS_PER_STEP/0.5
            fi = CITY_DYING+int(self._t)
            if fi == CITY_DEAD:
                self.state=CITY_DEAD
                sprite.disable()
            else:
                sprite.set_frame(fi)



        

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

    def y(self):
        return self.base_y

    def set_y(self,v):
        self.base_y=v
        for sp in self.digits: 
            sp.set_y(self.base_y)

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

W_ENEMY_MIN=10
W_M0=10
W_M1=11
W_M2=12
W_M2CA=13 # CITY AIM
W_B0=20
W_B1=21
W_ENEMY_MAX=29

level_colors=[
    # DO NOT USE RED: Reserved for red alert (last city standing)
    (0,192,0),      # green
    (64,192,192),   # cyan
    (192,192,64),   # yellow
]
level_waves=[
    # ------- LEVEL 1 -------
    [
        #  ,----------- Duration seconds (will extend to amount steps if too low)
        # |  ,--------- Amount
        # |  |   ,---- Enemy shuffle bag 

        # ###
        # ### DEBUG REMOVE ME
        # ###
        # ( 2  ,  1, [W_M2]          ),
        # ( 2  ,  1, [W_M2]          ),
        # ( 2  ,  1, [W_M2]          ),
        # ( 2  ,  1, [W_M2]          ),
        # ( 2  ,  1, [W_M2]          ),
        # ( 2  ,  1, [W_M2]          ),
        # ( 2  ,  1, [W_M2]          ),

        ###
        ###
        ( 3  ,  0, []          ),
        (10  ,  5, [W_M0]      ),
        ( 3  ,  0, []          ),
        ( 4  ,  4, [W_M0,W_M1] ),
        ( 3  ,  0, []          ),
        (2.4 ,  1, [W_WARN]    ),
        ( 0  ,  5, [W_M0]      ),
    ],
    # ------- LEVEL 2 -------
    [
        #  ,----------- Duration seconds (will extend to amount steps if too low)
        # |  ,--------- Amount
        # |  |   ,---- Enemy shuffle bag 
        ( 3  ,  0, []          ),
        (10  ,  5, [W_M0]      ),
        ( 3  ,  0, []          ),
        ( 1  ,  1, [W_M2] ),
        ( 4  ,  4, [W_M0,W_M1] ),
        ( 1  ,  1, [W_M2] ),
        ( 2  ,  0, []          ),
        (2.4 ,  1, [W_WARN]    ),
        ( 0  ,  5, [W_M0]      ),
        ( 5  ,  0, []          ),
        ( 0  ,  5, [W_M0]      ),
        ( 5  ,  0, []          ),
        ( 0  ,  5, [W_M1]      ),
    ],    
    # ------- LEVEL 3 -------
    [
        #  ,----------- Duration seconds (will extend to amount steps if too low)
        # |  ,--------- Amount
        # |  |   ,---- Enemy shuffle bag 
        ( 3  ,  0, []          ),
        (10  ,  5, [W_M1]      ),
        ( 3  ,  0, []          ),
        ( 1  ,  1, [W_M2,W_M1] ),
        ( 4  ,  4, [W_M2,W_M1] ),
        ( 2  ,  2, [W_M2CA] ),
        ( 3  ,  0, []          ),
        ( 10 , 20, [W_M0] ),
        ( 3  ,  0, []          ),
        ( 1  ,  1, [W_M2,W_M1] ),
        ( 4  ,  4, [W_M2,W_M1] ),
        ( 2  ,  2, [W_M2CA] ),
        ( 2  ,  0, []          ),
        (2.4 ,  1, [W_WARN]    ),
        ( 10  , 20, [W_M2]      ),
    ],    
]

class ShuffleBag:
    def __init__(self, elems):
        self.bag=elems.copy()
        self.shuffle()
        self.empty=len(self.bag) == 0

    def shuffle(self):
        for i in range(1, len(self.bag)):
            j = randint(0,i)
            tmp=self.bag[i]
            self.bag[i]=self.bag[j]
            self.bag[j]=tmp
        self.next_i=0

    def remove(self, elem):
        self.bag.remove(elem)
        self.empty=len(self.bag) == 0
        self.shuffle()

    def next(self):
        if self.empty:
            raise Exception("next on empty ShuffleBag")

        elem = self.bag[self.next_i]
        self.next_i += 1
        if self.next_i == len(self.bag):
            self.shuffle()
            self.next_i = 0
        return elem


class Waves:
    def __init__(self, waves):
        self.step=0
        self.warn=False
        self.waves=waves

        self.next_waves_i=0
        self.load_next_wave()
    
    def load_next_wave(self):
        (secs, wave_spawn_amount, bag_elems) = self.waves[self.next_waves_i]
        # Max between wanted seconds, and being able to spawn at least the full amount!
        self.wave_tmr = max(wave_spawn_amount, ceil(STEPS_PER_SECOND*secs))
        self.spawn_pending=wave_spawn_amount
        self.spawn_period= 0 if wave_spawn_amount==0 else self.wave_tmr//wave_spawn_amount
        self.spawn_tmr=0 
        self.next_spawn_i=0
        self.bag=ShuffleBag(bag_elems)
        self.next_waves_i += 1



    def next(self): 
        self.wave_tmr -= 1
        if self.wave_tmr <= 0:
            if self.next_waves_i >= len(self.waves):
                return W_COMPLETE
            self.load_next_wave()

        if self.spawn_pending > 0 and not self.bag.empty:
            self.spawn_tmr -= 1
            if self.spawn_tmr <= 0:
                self.spawn_tmr = self.spawn_period
                self.spawn_pending -= 1
                return self.bag.next()

        return W_NONE


