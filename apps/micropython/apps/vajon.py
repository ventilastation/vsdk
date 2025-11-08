from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

NUBES_POR_NUBAREDA = 8
TICK_COUNTER = 0

AVANCE_PER_LEVEL = 32

REST_TIME = 240.0

class MySprite(Sprite):
    pass

def everyXTicks(n):
    global TICK_COUNTER
    TICK_COUNTER += 1
    return TICK_COUNTER % n == 0

def make_me_a_planet(strip):
    planet = MySprite()
    planet.set_strip(strip)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet

def make_me_a_planet_nop(strip):
    planet = MySprite()
    planet.set_strip(strip)
    planet.set_perspective(1)
    planet.set_x(8)
    planet.set_y(255)
    return planet

class ScoreBoard:
    def __init__(self):
        self.chars = []
        for n in range(4):
            s = MySprite()
            s.set_strip(stripes["numerals.png"])
            s.set_x(118 + n * 5)
            s.set_y(2)
            s.set_frame(11)
            s.set_perspective(2)
            self.chars.append(s)

        self.setscore(0)

    def setscore(self, value):
        for n, l in enumerate("%03d" % value):
            v = ord(l) - 0x30
            self.chars[n+1].set_frame(v)

class HitVfx(Sprite):
    def __init__(self):
        super().__init__()

        self.set_strip(stripes["hit_vfx.png"])
        self.playing = False
        self.actualFrame = 0
        self.totalFrames = 5

    def play(self):
        self.actualFrame = 0
        self.playing = True

    def step(self):
        if (not self.playing):
            return

        self.set_frame( self.actualFrame )
        self.actualFrame += 1
        if ( self.actualFrame > self.totalFrames ):
            self.actualFrame = 0
            self.playing = False
            self.disable()

class Impact:
    def __init__(self):
        super().__init__()
        self.sprite = make_me_a_planet(stripes["impact.png"])
        self.tickcount = 0
        self.duration = 0
        self.enabled = False
        self.sprite.disable()

    def play(self, duration = 1):
        self.enabled = True
        self.sprite.set_frame(0)
        self.tickcount = 1
        self.duration = duration

    def step(self):

        if (self.enabled == False):
            return
        
        if(self.tickcount > self.duration):
            self.tickcount = 0
            self.sprite.disable()
            return

        if (self.tickcount>0):
            self.tickcount += 1
        

class Roca(Sprite):
    def __init__(self):
        super().__init__()
        self.set_strip(stripes["roca.png"])
        self.set_x(0)
        self.set_y(0)
        self.enabled = True
        self.set_frame(0)

        
    def finish(self):
        self.set_x(randrange(0,255))
        self.set_y(randrange(200,255))
        #self.enabled = False
        #self.disable()

    def step(self):
        LASER_SPEED = 4
        self.set_y(self.y() - LASER_SPEED)
        if self.y() < 10:
            self.finish()

class Vajon(Scene):
    stripes_rom = "vajon"

    def on_enter(self):
        super(Vajon, self).on_enter()

        self.scoreboard = ScoreBoard()
        self.cantidad_rocas = 1


        self.hit = HitVfx()
        self.impact = Impact()

        self.player = MySprite()
        self.player.set_x(0)
        self.player.set_y(24)
        self.player.set_strip(stripes["pj.png"])
        self.pjindex = 0
        self.player.set_frame(self.pjindex)

        #self.nubareda = Nubareda()
        #self.nubareda.reiniciar()
        
        #self.roca = Roca()
        #self.roca2 = Roca()
        #self.roca3 = Roca()
        #self.roca4 = Roca()

        #self.rocas = [self.roca, self.roca2, self.roca3, self.roca4]
        
        self.rocas = []
        for _ in range(4):
            roca = Roca()
            self.rocas.append(roca)
        
        #self.brazo = MySprite()
        #self.brazo.set_strip(stripes["tentacle2.png"])
        #self.brazo.set_x(100)
        #self.brazo.set_y(32)
        #self.brazo.set_frame(0)

        #self.brazo2 = MySprite()
        #self.brazo2.set_strip(stripes["tentacle1.png"])
        #self.brazo2.set_x(0)
        #self.brazo2.set_y(32)
        #self.brazo2.set_frame(0)

        self.monsterPart = make_me_a_planet(stripes["monster_part0.png"])
        self.monsterPart.set_frame(0)

        self.monster = make_me_a_planet(stripes["monster.png"])
        self.monster.set_frame(0)
        self.monster.set_y( 100 )
        self.monster.appearing = False
        self.monster.disable()

        self.hoyo = make_me_a_planet(stripes["pozo0.png"])
        self.hoyo.set_frame(0)

        self.pozoi = 0

        self.force = 0.0
        self.inertia = 0
        self.inertiaMax = 8

        self.speedActual = 0

        self.avance = 0
        self.level = 0

        self.rest_time = REST_TIME

        director.music_play("vajon/synt263_l")

        self.ending = False

        self.endingFall = False
        self.endingChomp = False

        #self.chomp

    def step(self):
        # self.bola.set_x(self.bola.x() + 1)

        
        
        self.impact.step()


        self.pozoi += 1
        pi = (self.pozoi // 4) % 3

        self.pjindex += 1
        pf = (self.pjindex // 2) % 3

        self.hoyo.set_strip( stripes["pozo"+str(pi)+".png" ] )

        #if (self.endingChomp)
        #self.monsterPart.set_strip( stripes["pozo"+str(pi)+".png" ] )

        #self.roca.step()
        #self.roca2.step()
        #self.roca3.step()
        #self.roca4.step()
        

        for roca in self.rocas:
            roca.step()

        self.hoyo.set_x( randrange( -3,4 ) )
        self.hoyo.set_y( randrange( 250,255 ) )
        self.player.set_frame ( pf )

        #self.brazo.set_x( self.brazo.x() + -1 )

        self.hit.set_x( self.player.x() )
        self.hit.set_y( self.player.y() )
        self.hit.step()

        if (not self.ending):
            self.rest_time -= 0.03
            self.scoreboard.setscore( int(self.rest_time) )

        if ( self.monster.appearing ):
            self.monster.set_y( self.monster.y() + 1 )

        if ( self.monster.y() >= 200 ):
            self.monster.appearing = False

        #if (self.player.x() > 100 and self.player.x() < 150 ):
        #    self.impact.set_frame(0)
        #else:
        #    self.impact.disable()

        #sync monster part to monster
        self.monsterPart.set_y( self.monster.y() )

        #print("player X: ", self.player.x())

        #print("monster Y", self.monster.y())

        #if (randrange(0,20)<1):
            #self.roca.set_y(100)
            #self.bola.set_x( self.bola.x() + 1)
        
 
        #self.hoyo.set_frame(0)


        #if director.was_pressed(director.BUTTON_A):
            #nub_x = self.nubareda.x
            #nub_finx = self.nubareda.x + self.nubareda.width + 16
            #if nub_x < self.bola.x() < nub_finx:
                #director.sound_play(b"vyruss/shoot1")
                #self.nubareda.reiniciar()
            #else:
                #director.sound_play(b"vyruss/explosion3")
                #director.music_play("vyruss/vy-gameover")
                #self.finished()
        
        if director.is_pressed( director.BUTTON_A ):
            print("BUTTON A!")
            #self.hit.play()

        if director.is_pressed( director.JOY_LEFT ) and self.inertia < self.inertiaMax:
            #self.force +=  0.2
            self.inertia += 1
            
        if director.is_pressed( director.JOY_RIGHT ) and self.inertia > -self.inertiaMax:
            #self.force -= 0.2
            self.inertia -= 1

        if director.is_pressed( director.JOY_UP ):
            print("arriba")
            #self.brazo.set_y( self.brazo.y() - 1 )
            #self.brazo2.set_y( self.brazo2.y() - 1 )
            #self.monster.set_y( self.monster.y() - 1 )
            #self.player.set_y(self.player.y() + 2)
            #self.nubareda.planet.set_y( self.nubareda.planet.y() - 2 )

        if director.is_pressed( director.JOY_DOWN ):
            print("abajo")
            #self.brazo.set_y( self.brazo.y() + 1 )
            #self.brazo2.set_y( self.brazo2.y() + 1 )
            #self.monster.set_y( self.monster.y() + 1 )
            #self.player.set_y(self.player.y() - 2)
            #self.nubareda.planet.set_y( self.nubareda.planet.y() + 2 )

        #self.inertia = int( self.force )
        #print( "inertia actual: ", self.inertia)
        #if (everyXTicks(2)):
        self.player.set_x(self.player.x() + self.inertia)

        if director.was_pressed(director.BUTTON_D):
            self.finished()

        #if ( self.force < 0 ):
        #    self.force += 0.1

        #if (self.force > 0):
         #   self.force -= 0.1

        if ( everyXTicks(3) ):
            if self.inertia < 0:
               self.inertia += 1

            if self.inertia > 0:
                self.inertia -= 1

            #self.avance += 1

        if ( everyXTicks(4) ):
            self.avance += 1

        if ( self.avance > 100 * (self.level+1) and not self.ending):
            self.level +=1
            director.sound_play("vajon/fallmore")

        if (not self.ending):
            self.player.set_y( 16 + 16 * self.level )
        
        if (self.ending and self.player.y() > 16 and not self.endingFall):
            self.player.set_y(self.player.y() - 1)

        if (self.endingFall):
            self.player.set_y(self.player.y()+1)

        if (self.rest_time<200 and self.rocas[0].enabled):
            self.rocas[0].disable()
            self.rocas[0].enabled = False
            
        if (self.rest_time<150 and self.rocas[1].enabled):
            self.rocas[1].disable()
            self.rocas[1].enabled = False            
        
        if (self.rest_time<80 and self.rocas[2].enabled):
            self.rocas[2].disable()
            self.rocas[2].enabled = False

        hittedRock = self.player.collision(self.rocas)
        if ( hittedRock and hittedRock.enabled ):
            self.hit.play()
            hittedRock.finish()
            self.impact.play(2)
            self.avance = max(self.avance-100, 0)
            self.level = max(self.level-1, 0)
            director.sound_play("vajon/hurt")
            print("COLISION CON ROCA! PLAF!")

        # end
        if (self.level==5 and not self.ending):
            self.endAnimation()


        #print("Avance: ", AVANCE)
        #self.scoreboard.setscore( self.avance )
        #self.scoreboard.setscore( self.rest_time )
    def endAnimation(self):
        self.ending = True
        self.monster.set_frame(0)
        self.monster.appearing = True

        for roca in self.rocas:
            roca.enabled = False
            roca.disable()

        self.call_later(4000, self.endFalling)

    def endFalling(self):
        director.sound_play("vajon/end")
        self.endingFall = True


    def finished(self):
        director.pop()
        raise StopIteration()

def main():
    return Vajon()