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
        self.bambi = []
        self.bambi.append(make_me_a_planet(strips.laupalav.bambi01))
        self.bambi.append(make_me_a_planet(strips.laupalav.bambi02))
        self.bambi.append(make_me_a_planet(strips.laupalav.bambi03))

        self.frente = []
        self.frente.append(make_me_a_planet(strips.laupalav.frente00))
        self.frente.append(make_me_a_planet(strips.laupalav.frente01))
        self.frente.append(make_me_a_planet(strips.laupalav.frente02))
        self.frente.append(make_me_a_planet(strips.laupalav.frente03))
        self.frente.append(make_me_a_planet(strips.laupalav.frente04))
        self.frente.append(make_me_a_planet(strips.laupalav.frente05))
        self.frente.append(make_me_a_planet(strips.laupalav.frente06))
        self.frente.append(make_me_a_planet(strips.laupalav.frente07))
        self.frente.append(make_me_a_planet(strips.laupalav.frente08))
        self.frente.append(make_me_a_planet(strips.laupalav.frente09))
        self.frente.append(make_me_a_planet(strips.laupalav.frente10))
        self.frente.append(make_me_a_planet(strips.laupalav.frente11))

        self.fondo = []
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo00))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo01))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo02))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo03))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo04))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo05))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo06))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo07))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo08))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo09))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo10))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo11))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo12))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo13))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo14))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo15))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo16))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo17))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo18))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo19))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo20))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo21))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo22))
        self.fondo.append(make_me_a_planet(strips.laupalav.fondo23))

        self.rose_black = []
        self.rose_black.append(make_me_a_planet(strips.laupalav.rose_black_00))
        self.rose_black.append(make_me_a_planet(strips.laupalav.rose_black_01))

        self.rose_green = []
        self.rose_green.append(make_me_a_planet(strips.laupalav.rose_green_00))
        self.rose_green.append(make_me_a_planet(strips.laupalav.rose_green_01))

        self.animations = [
                self.rose_black,
                self.bambi,
                self.rose_green,
        ]

        self.current_animation = -1
        self.current_sprite = self.bambi[0]
        self.next_animation()
        #director.music_play(b"other/piostart")

    def next_animation(self):
        self.current_sprite.disable()
        self.current_animation = (self.current_animation + 1) % len(self.animations)

    def step(self):
        self.animation_frames += 1
        af = (self.animation_frames // 7) % len(self.animations[self.current_animation])
        new_sprite = self.animations[self.current_animation][af]
        self.current_sprite.disable()
        new_sprite.set_frame(0)
        self.current_sprite = new_sprite

        if director.was_pressed(director.BUTTON_A):
            self.next_animation()

        if director.was_pressed(director.BUTTON_D) or director.timedout:
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()
