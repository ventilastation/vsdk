from ventilastation.director import director
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from ventilastation.imagenes import strips

def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(strip)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet

class LauraPalavecino(Scene):

    def on_enter(self):
        self.animation_frames = 0

        self.frente = []
        self.frente.append(make_me_a_planet(strips.laupalav.frenteA00))
        self.frente.append(make_me_a_planet(strips.laupalav.frenteB01))
        self.frente.append(make_me_a_planet(strips.laupalav.frenteC02))
        self.frente.append(make_me_a_planet(strips.laupalav.frenteD03))
        self.frente.append(make_me_a_planet(strips.laupalav.frenteA04))
        self.frente.append(make_me_a_planet(strips.laupalav.frenteB05))
        self.frente.append(make_me_a_planet(strips.laupalav.frenteC06))
        self.frente.append(make_me_a_planet(strips.laupalav.frenteD07))
        self.frente.append(make_me_a_planet(strips.laupalav.frenteA08))
        self.frente.append(make_me_a_planet(strips.laupalav.frenteB09))
        self.frente.append(make_me_a_planet(strips.laupalav.frenteC10))
        self.frente.append(make_me_a_planet(strips.laupalav.frenteD11))

        self.bambi = []
        self.bambi.append(make_me_a_planet(strips.laupalav.bambi01b))
        self.bambi.append(self.bambi[-1])
        self.bambi.append(make_me_a_planet(strips.laupalav.bambi02b))
        self.bambi.append(self.bambi[-1])
        self.bambi.append(make_me_a_planet(strips.laupalav.bambi03b))
        self.bambi.append(self.bambi[-1])
        self.bambi.append(make_me_a_planet(strips.laupalav.bambi04b))
        self.bambi.append(self.bambi[-1])

        self.fondo = []
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoA00))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoB01))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoC02))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoD03))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoA04))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoB05))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoC06))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoD07))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoA08))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoB09))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoC10))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoD11))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoA12))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoB13))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoC14))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoD15))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoA16))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoB17))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoC18))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoD19))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoA20))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoB21))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoC22))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondoD23))

        self.rose = []
        self.rose.append(make_me_a_planet(strips.laupalav.rose01))
        self.rose.append(self.rose[-1])
        self.rose.append(make_me_a_planet(strips.laupalav.rose02))
        self.rose.append(self.rose[-1])
        self.rose.append(make_me_a_planet(strips.laupalav.rose03))
        self.rose.append(self.rose[-1])
        self.rose.append(make_me_a_planet(strips.laupalav.rose04))
        self.rose.append(self.rose[-1])
        self.rose.append(make_me_a_planet(strips.laupalav.rose05))
        self.rose.append(self.rose[-1])
        self.rose.append(make_me_a_planet(strips.laupalav.rose06))
        self.rose.append(self.rose[-1])

        self.animations = [
                [self.rose],
                [self.frente, self.bambi, self.fondo],
        ]

        self.current_animation = -1
        self.current_sprites = []
        self.next_animation()
        #director.music_play(b"other/piostart")

    def next_animation(self):
        for s in self.current_sprites:
            s.disable()
        self.current_animation = (self.current_animation + 1) % len(self.animations)

    def step(self):
        self.animation_frames += 1

        new_sprites = [] 
        for s in self.current_sprites:
            s.disable()
        for anim in self.animations[self.current_animation]:
            af = (self.animation_frames // 3) % len(anim)
            ns = anim[af]
            ns.set_frame(0)
            new_sprites.append(ns)
        self.current_sprites = new_sprites

        if director.was_pressed(director.BUTTON_A):
            self.next_animation()

        if director.was_pressed(director.BUTTON_D) or director.timedout:
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()
