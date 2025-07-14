# == Iterando por imágenes ==
# - rosedew
# - Laura P
# - bambi de fuego
# - placa de bambi
# - Laura P
# - vlad farty
# - Mer G
# - animchau
# - chame
# - bembi + pollitos
# - paula w
import utime
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite, reset_sprites

vibratto = [20, 20, 20, 20, 20, 21, 21, 22, 22, 23, 24, 25, 26, 26, 27, 27, 28, 28, 28, 28, 28, 27, 27, 26, 26, 25, 24, 23, 22, 22, 21, 21]
tablelen = len(vibratto)

def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(stripes[strip])
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet


class TimedScene(Scene):
    keep_music = True

    def __init__(self):
        super().__init__()
        self.scene_start = utime.ticks_ms()
        if self.duration:
            self.call_later(self.duration, self.finish_scene)

    def scene_step(self):
        super().scene_step()
        b = director.is_pressed(director.BUTTON_B)
        c = director.is_pressed(director.BUTTON_C)
        if director.was_pressed(director.BUTTON_A) and b and c:
            director.pop()

        left = director.is_pressed(director.JOY_LEFT)
        right = director.is_pressed(director.JOY_RIGHT)
        if left and right:
            director.pop()
            from apps import ventilagon_game
            director.push(ventilagon_game.VentilagonGame())
            Gallery.farty_step = 0
            
        if director.was_pressed(director.BUTTON_D):
            director.pop()
            raise StopIteration()

    def finish_scene(self):
        director.pop()


class Gallery(Scene):
    def __init__(self):
        super().__init__()
        Gallery.farty_step = 0

    def on_enter(self):
        super(Gallery, self).on_enter()
        if not director.was_pressed(director.BUTTON_D):
            self.next_scene()
        else:
            director.pop()
            raise StopIteration()

    def step(self):
        if director.was_pressed(director.BUTTON_D):
            director.pop()
            raise StopIteration()

    def next_scene(self):
        new_scene_class = scenes[Gallery.farty_step]
        if new_scene_class:
            director.push(new_scene_class())
            Gallery.farty_step = (Gallery.farty_step + 1) % len(scenes)
        else:
            director.pop()
            raise StopIteration()



class Chanimation(TimedScene):
    stripes_rom = "vladfarty"
    duration = 15000
    CHAMEPICS = 7
    ANIMATE_SPEED = 15

    def on_enter(self):
        super(Chanimation, self).on_enter()
        self.chame_pics = []
        for f in chanimation_frames:
            chp = make_me_a_planet(stripes[f])
            self.chame_pics.append(chp)
            chp.set_y(255)
        self.n = 0
        self.current_pic = 0
        self.update_pic()

    def update_pic(self):
        numpic = self.n // self.ANIMATE_SPEED
        if numpic < len(self.chame_pics):
            self.chame_pics[self.current_pic].disable()
            self.current_pic = numpic
            self.chame_pics[self.current_pic].set_frame(0)
        else:
            director.pop()
            raise StopIteration()

    def step(self):
        self.n += 1
        self.update_pic()


chanimation_frames = [
    "chanime01.png",
    "chanime02.png",
    "chanime03.png",
    "chanime04.png",
    "chanime05.png",
    "chanime06.png",
    "chanime07.png",
]

chanijump_frames = [
    "salto01.png",
    "salto02.png",
    "salto03.png",
    "salto04.png",
    "salto05.png",
    "salto06.png",
]

class Chanijump(TimedScene):
    stripes_rom = "vladfarty"
    duration = 5000
    CHAMEPICS = 6
    ANIMATE_SPEED = 5
    order = [0, 1, 2, 3, 4, 5, 5, 4, 3, 2, 1, 0]

    def on_enter(self):
        super(Chanijump, self).on_enter()
        self.chame_pics = []
        for f in chanijump_frames:
            chp = make_me_a_planet(f)
            self.chame_pics.append(chp)
            chp.set_y(255)
        self.n = 0
        self.current_pic = 0
        self.update_pic()

    def update_pic(self):
        numpic = self.order[ (self.n // self.ANIMATE_SPEED) % len(self.order) ]
        self.chame_pics[self.current_pic].disable()
        self.current_pic = numpic
        self.chame_pics[self.current_pic].set_frame(0)

    def step(self):
        self.n += 1
        self.update_pic()

class DancingLions(TimedScene):
    stripes_rom = "vladfarty"
    duration = 5000 + 1500

    def on_enter(self):
        super(DancingLions, self).on_enter()
        self.farty_lionhead = make_me_a_planet("farty_lionhead.png")
        self.farty_lionhead.set_y(0)
        self.farty_lionhead.disable()
        self.farty_lion = make_me_a_planet("farty_lion.png")
        self.farty_lion.set_y(100)
        self.farty_lion.set_frame(0)
        self.n = 0
        self.call_later(self.duration - 1500, self.start_lionhead)
        self.increment = 2

    def start_lionhead(self):
        self.increment = -5
        self.farty_lionhead.set_y(100)
        self.farty_lionhead.set_frame(0)

    def step(self):
        new_y = self.farty_lion.y() + self.increment
        if 0 < new_y < 256:
            self.farty_lion.set_y(new_y)
        self.farty_lion.set_x(vibratto[self.n % tablelen]-24)
        self.n += 1
        lionhead_size = self.farty_lionhead.y()
        if 10 < lionhead_size < 200:
            self.farty_lionhead.set_y(lionhead_size + 10)



def build_sprites(strips):
    return [make_me_a_planet(s) for s in strips]

def build_animation(sprites, order):
    return [sprites[n] for n in order]

class Bambi(TimedScene):
    stripes_rom = "laupalav"
    duration = 15000

    def on_enter(self):
        super(Bambi, self).on_enter()
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

        frente_anim = build_animation(frente_sprites, range(len(frente_sprites)))
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

        fondo_anim = build_animation(fondo_sprites, range(len(fondo_sprites)))
        self.fondo = lambda frame: fondo_anim[(frame // 6) % len(fondo_anim)]

        self.animations = [
                [self.frente, self.bambi, self.fondo],
        ]

        self.current_animation = -1
        self.current_sprites = []
        self.next_animation()

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


class PlacaBambi(TimedScene):
    stripes_rom = "laupalav"
    duration = 3000

    def on_enter(self):
        super(PlacaBambi, self).on_enter()
        self.animation_frames = 0

        placa_sprites = build_sprites([
            "placa.png"
        ])
        placa_anim = build_animation(placa_sprites, [0])
        self.placa = lambda _: placa_anim[0]

        self.animations = [
                [self.placa],
        ]

        self.current_animation = -1
        self.current_sprites = []
        self.next_animation()

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

class Rose(TimedScene):
    stripes_rom = "laupalav"
    duration = 10000

    def on_enter(self):
        super(Rose, self).on_enter()
        self.animation_frames = 0

        rose_sprites = build_sprites([
            "rose01.png",
            "rose02.png",
            "rose03.png",
            "rose04.png",
            "rose05.png",
            "rose06.png",
        ])
        rose_anim = build_animation(rose_sprites, [0, 1, 2, 3, 4, 5, 5, 5, 5, 5, 5, 4, 3, 2, 1, 0, 0, 0])
        self.rose = lambda frame: rose_anim[(frame // 4) % len(rose_anim)]

        self.animations = [
                [self.rose],
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
        for anim in self.animations[self.current_animation]:
            ns = anim(self.animation_frames)
            ns.set_frame(0)
            new_sprites.append(ns)
        for s in self.current_sprites:
            if s not in new_sprites:
                s.disable()
        self.current_sprites = new_sprites


class MilaLHHL(TimedScene):
    stripes_rom = "milalhhl"
    duration = 15000

    def on_enter(self):
        super(MilaLHHL, self).on_enter()
        self.animation_frames = 0

        carcer_sprites = build_sprites([
            "patru1.png",
            "patru2.png",
            "fiat1.png",
            "fiat2.png",
            "mix1.png",
            "peugeot1.png",
        ])
        carcer_anim = build_animation(carcer_sprites, [
            0, 1, 2,
            3, 4, 5
         ])
        self.carcer = lambda frame: carcer_anim[(frame // 120) % len(carcer_anim)]

        self.animations = [
                [self.carcer],
        ]

        self.current_animation = -1
        self.current_sprites = []
        self.next_animation()

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


class Bembidiona(TimedScene):
    stripes_rom = "other"
    duration = 10000

    def on_enter(self):
        super(Bembidiona, self).on_enter()
        self.pollitos = Sprite()
        self.pollitos.set_x(-32)
        self.pollitos.set_y(0)
        self.pollitos.set_strip(stripes["pollitos.png"])
        self.pollitos.set_frame(0)
        self.pollitos.set_perspective(2)
        self.animation_frames = 0

        self.jere = make_me_a_planet("bembi.png")
        self.jere.set_y(255)
        self.jere.set_frame(0)

    def step(self):
        self.animation_frames += 1
        pf = (self.animation_frames // 4) % 5
        self.pollitos.set_frame(pf)


char_width = 9
char_height = 12
display_len = 12

class TextDisplay:
    def __init__(self, y):
        self.chars = []
        for n in range(display_len):
            s = Sprite()
            s.set_strip(stripes["vga_cp437.png"])
            s.set_x((256 -n * char_width) % 256)
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




class Label(TimedScene):
    stripes_rom = "vladfarty"
    duration = 1500

    def on_enter(self):
        super(Label, self).on_enter()
        self.label = TextDisplay(2)
        self.label.set_value(self.label_text)


def label(text):
    class TempLabel(Label):
        label_text = text
    return TempLabel


class Pyformances(TimedScene):
    stripes_rom = "other"
    duration = 4000 + 3000

    def on_enter(self):
        super(Pyformances, self).on_enter()
        self.n0 = make_me_a_planet("pyformances_n0.png")
        self.n0.set_y(0)
        self.n0.disable()
        self.title = make_me_a_planet("pyformances_py.png")
        self.title.set_y(100)
        self.title.set_frame(0)
        self.n = 0
        self.call_later(self.duration - 3000, self.start_title)
        self.increment = 2

    def start_title(self):
        self.increment = -5
        self.n0.set_y(100)
        self.n0.set_frame(0)
        self.n0.set_y(255)

    def step(self):
        new_y = self.title.y() + self.increment
        if 0 < new_y < 256:
            self.title.set_y(new_y)
        #self.title.set_x(vibratto[self.n % tablelen]//4-24)
        self.n += 1
        lionhead_size = self.title.y()
        # if 10 < lionhead_size < 200:
        #self.n0.set_y(lionhead_size + 10)


scenes = [
    # Pyformances,
    Bambi,
    PlacaBambi,
    label("Laura P."),
    Rose,
    label("Laura P."),
    MilaLHHL,
    label("Milagros A."),
    DancingLions,
    label("Mer G."),
    # Chanimation,
    # Chanijump,
    # label("Chame"),
    Bembidiona,
    label("Paula W."),
]

def main():
    return Gallery()