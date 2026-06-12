from ventilastation.director import director, PIXELS, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
from ventilastation import povdisplay


char_width = 9
char_height = 12
display_len = 12

class TextDisplay:
    def __init__(self, y):
        self.chars = []
        for n in range(display_len):
            s = Sprite()
            s.set_strip(stripes["vga_cp437.png"])
            s.set_x((256 -n * char_width + (display_len * char_width) // 2) % 256)
            s.set_y(y)
            s.set_frame(10)
            s.set_perspective(2)
            self.chars.append(s)

        self.set_value("")

    def set_value(self, value):
        for n in range(len(self.chars)):
            self.chars[n].set_frame(0)
        for n, l in enumerate(value):
            v = ord(l)# - 0x30
            self.chars[n].set_frame(v)


from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
import uctypes

def make_me_a_planet(strip_name):
    planet = Sprite()
    planet.set_strip(stripes[strip_name])
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet

def build_sprites(strips):
    return [make_me_a_planet(s) for s in strips]

def build_animation(sprites, order):
    return [sprites[n] for n in order]

class Calibrate(Scene):
    stripes_rom = "laupalav"

    def on_enter(self):
        super(Calibrate, self).on_enter()
        self.display = TextDisplay(0)
        self.display.set_value("Calibrate!")

        self.animation_frames = 0

        frente_sprites = build_sprites([
            "frenteA00.png",
            "frenteB01.png",
            "frenteC02.png",
            "frenteD03.png",
            "frenteA04.png",
            "frenteB05.png",
            "frenteC06.png",
            "frenteD07.png",
            "frenteA08.png",
            "frenteB09.png",
            "frenteC10.png",
            "frenteD11.png",
            "frenteA12.png",
            "frenteB13.png",
            "frenteC14.png",
            "frenteD15.png",
        ])

        frente_anim = build_animation(frente_sprites, range(16))
        self.frente = lambda frame: frente_anim[(frame // 5) % len(frente_anim)]

        bambi_sprites = build_sprites([
            "bambi01b.png",
            "bambi02b.png",
            "bambi03b.png",
            "bambi04b.png",
        ])

        bambi_anim = build_animation(bambi_sprites, [0, 0, 1, 1, 2, 2, 3, 3])
        self.bambi = lambda frame: bambi_anim[(frame // 4) % len(bambi_anim)]

        fondo_sprites = build_sprites([
            "fondoA00.png",
            "fondoB01.png",
            "fondoC02.png",
            "fondoD03.png",
            "fondoA04.png",
            "fondoB05.png",
            "fondoC06.png",
            "fondoD07.png",
            "fondoA08.png",
            "fondoB09.png",
            "fondoC10.png",
            "fondoD11.png",
            "fondoA12.png",
            "fondoB13.png",
            "fondoC14.png",
            "fondoD15.png",
            "fondoA16.png",
            "fondoB17.png",
            "fondoC18.png",
            "fondoD19.png",
            "fondoA20.png",
            "fondoB21.png",
            "fondoC22.png",
            "fondoD23.png",
        ])

        fondo_anim = build_animation(fondo_sprites, range(24))
        self.fondo = lambda frame: fondo_anim[(frame // 6) % len(fondo_anim)]

        self.animations = [
                [self.frente, self.bambi, self.fondo],
        ]

        self.current_animation = -1
        self.current_sprites = []
        self.next_animation()
        #director.music_play(b"other/piostart")

        self.brillos = uctypes.bytearray_at(povdisplay.getaddress(997), PIXELS)
        self.intensidades_por_led = uctypes.bytearray_at(povdisplay.getaddress(998), PIXELS)
        self.ring = 0
        povdisplay.set_gamma_mode(1)

    def next_animation(self):
        for s in self.current_sprites:
            s.disable()
        self.current_animation = (self.current_animation + 1) % len(self.animations)

    def step(self):
        self.animation_frames += 1

        new_sprites = [] 
        for anim in self.animations[self.current_animation]:
            ns = anim(self.animation_frames)
            ns.set_frame(0)
            new_sprites.append(ns)
        for s in self.current_sprites:
            if s not in new_sprites:
                s.disable()
        self.current_sprites = new_sprites

        if director.was_pressed(director.BUTTON_D):
            self.finished()

         # brillo
        up = director.was_pressed(director.JOY_UP)
        down = director.was_pressed(director.JOY_DOWN)

        if up or down:
            new_brillo = (self.brillos[self.ring] - down + up) % 32
            self.brillos[self.ring] = new_brillo
            self.display.set_value("brillo = %d" % new_brillo)

        # curva

        left = director.was_pressed(director.JOY_LEFT)
        right = director.was_pressed(director.JOY_RIGHT)

        if left or right:
            new_int = (self.intensidades_por_led[self.ring] - left + right) % PIXELS
            self.intensidades_por_led[self.ring] = new_int
            self.display.set_value("ipl = %d" % new_int)

        # ring

        back = director.was_pressed(director.BUTTON_B)
        forth = director.was_pressed(director.BUTTON_C)

        if back or forth:
            self.ring = (self.ring - back + forth) % PIXELS
            self.display.set_value(
                "%d %d %d" % (
                    self.ring, 
                    self.intensidades_por_led[self.ring], 
                    self.brillos[self.ring]
                )
            )



    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Calibrate()