from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

MAX_VIDAS = 3
SPEED = 8
LIMIT = 30

IZQ = 1
DER = -1

SPEED_0 = 1.8       # Velocidad inicial
ACC = 0.2           # Aceleracion

class MySprite(Sprite):
    pass


def animate(sp):
    sp.set_frame(sp.init_frame + (sp.frame() - sp.init_frame + 1) % sp.frames)

def peron():
    sp = MySprite()
    sp.set_strip(stripes["peronsad.png"])
    sp.set_perspective(0)
    sp.set_x(0)
    sp.set_y(255)
    sp.set_frame(0)
    sp.disable()
    return sp

def crear_mano(sentido):
    sp = MySprite()
    sp.set_strip(stripes["mano.png"])
    sp.set_frame(1)
    sp.set_perspective(1)
    sp.set_x(0)
    sp.set_y(20)

    sp.set_x(112 + 48 * sentido)
    sp.set_frame(1 - sentido)

    return sp

def cosito():
    sp = MySprite()
    sp.set_strip(stripes["bola.png"])
    sp.set_frame(1)
    sp.set_perspective(1)
    sp.set_x(0)
    sp.set_y(255)

    # sp.init_frame = 6
    # sp.frames = 2

    return sp

class Peron():
    def __init__(self):
        self.frames = []
        self.frames.append(self.crear_sprite("peron.png"))
        self.frames.append(self.crear_sprite("peronsad.png"))
        self.feliz()

    def feliz(self):
        self.frames[0].set_frame(0)
        self.frames[1].disable()

    def triste(self):
        self.frames[1].set_frame(0)
        self.frames[0].disable()

    def crear_sprite(self, name):
        sp = MySprite()
        sp.set_strip(stripes[name])
        sp.set_perspective(0)
        sp.set_x(0)
        sp.set_y(255)
        sp.set_frame(0)
        return sp


class ScoreVidas():

    def __init__(self, score=0, vidas=MAX_VIDAS):
        self.score = score
        self.vidas = vidas

        self.crear_cartel()
        self.actualizar()

    def puntuar(self):
        self.score += 1
        self.actualizar()

    def perder(self):
        self.vidas -= 1
        self.actualizar()
        return (self.vidas <= 0)

    def actualizar(self):
        print(f"Score: {self.score} - Vidas: {self.vidas}")

        # Score    
        for n, l in enumerate("%05d" % self.score):
            v = ord(l) - 0x30
            self.chars[n].set_frame(v)

        # Vidas
        for n in range(MAX_VIDAS):
            self.chars[6+n].set_frame(10 + int(self.vidas > n))
    
    def crear_cartel(self):
        print("crear_cartel")
        self.chars = []
        for n in range(9):
            s = MySprite()
            s.set_strip(stripes["numerals.png"])
            s.set_x(110 + n * 4)
            s.set_y(0)
            s.set_frame(10)
            s.set_perspective(2)
            self.chars.append(s)

# Scenes

class GameOver(Scene):

    def set_score(self, score=0):
        self.score = score
        return self

    def on_enter(self):
        super(GameOver, self).on_enter()

        self.sc = ScoreVidas(self.score, 0)

        sp = MySprite()
        sp.set_strip(stripes["gameover.png"])
        sp.set_perspective(0)
        sp.set_x(0)
        sp.set_y(255)
        sp.set_frame(0)

        director.music_play("peronjam/estatizacion")
    
    def step(self):
        if director.was_pressed(director.BUTTON_D) or director.was_pressed(director.BUTTON_A):
            self.finished()
    
    def finished(self):
        director.pop()
        director.pop()
        raise StopIteration()

class PeronJam(Scene):
    stripes_rom = "peronjam"

    def on_enter(self):
        super(PeronJam, self).on_enter()

        self.cosito = cosito()

        self.manod = crear_mano(DER)
        self.manoi = crear_mano(IZQ)

        self.peron = Peron()
        self.score = ScoreVidas()

        self.speed = SPEED_0

        director.music_play("peronjam/marcha")

    def step(self):
        
        dx = director.is_pressed(director.JOY_LEFT) - director.is_pressed(director.JOY_RIGHT)
        dy = director.is_pressed(director.JOY_UP) - director.is_pressed(director.JOY_DOWN)
        
        self.manoi.set_x(self.manoi.x() - dy * SPEED)
        self.manod.set_x(self.manod.x() + dy * SPEED)

        if self.cosito.y() > 250:
            self.cosito.set_x(randrange(255))

        self.cosito.set_y(self.cosito.y() - int(self.speed))

        if self.cosito.y() < LIMIT and self.cosito.collision([self.manoi,self.manod]):
            self.score.puntuar()
            self.peron.feliz()

            director.sound_play("peronjam/fx0"+str(randrange(1,6)))

            self.cosito.set_y(255)
            self.speed += ACC
            return
        
        if self.cosito.y() < 5:
            self.cosito.set_y(255)
            self.peron.triste()
            director.sound_play("peronjam/traidor")
            if self.score.perder():
                director.push(GameOver().set_score(self.score.score))
                raise StopIteration()

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()        
        raise StopIteration()


def main():
    return PeronJam()