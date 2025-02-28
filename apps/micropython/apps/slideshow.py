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
from ventilastation.director import director
from ventilastation.scene import Scene
from ventilastation.imagenes import strips
from ventilastation.sprites import Sprite, reset_sprites

vibratto = [20, 20, 20, 20, 20, 21, 21, 22, 22, 23, 24, 25, 26, 26, 27, 27, 28, 28, 28, 28, 28, 27, 27, 26, 26, 25, 24, 23, 22, 22, 21, 21]
tablelen = len(vibratto)

def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(strip)
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
        left = director.is_pressed(director.JOY_LEFT)
        right = director.is_pressed(director.JOY_RIGHT)
        if director.was_pressed(director.BUTTON_A) and left and right:
            director.pop()
        if director.was_pressed(director.BUTTON_D):
            director.pop()
            raise StopIteration()

    def finish_scene(self):
        director.pop()


class Chanimation(TimedScene):
    duration = 15000
    CHAMEPICS = 7
    ANIMATE_SPEED = 15

    def on_enter(self):
        self.chame_pics = []
        for f in chanimation_frames:
            chp = make_me_a_planet(f)
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


vf = strips.vladfarty
chanimation_frames = [
    vf.chanime01,
    vf.chanime02,
    vf.chanime03,
    vf.chanime04,
    vf.chanime05,
    vf.chanime06,
    vf.chanime07,
]    

chanijump_frames = [
    vf.salto01,
    vf.salto02,
    vf.salto03,
    vf.salto04,
    vf.salto05,
    vf.salto06,
]

class Chanijump(TimedScene):
    duration = 5000
    CHAMEPICS = 6
    ANIMATE_SPEED = 5
    order = [0, 1, 2, 3, 4, 5, 5, 4, 3, 2, 1, 0]

    def on_enter(self):
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


class Slideshow(Scene):
    def __init__(self):
        super().__init__()
        self.farty_step = 0

    def on_enter(self):
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
        new_scene_class = scenes[self.farty_step]
        if new_scene_class:
            director.push(new_scene_class())
            self.farty_step = (self.farty_step + 1) % len(scenes)
        else:
            director.pop()
            raise StopIteration()


class DancingLions(TimedScene):
    duration = 5000 + 1500

    def on_enter(self):
        self.farty_lionhead = make_me_a_planet(strips.vladfarty.farty_lionhead)
        self.farty_lionhead.set_y(0)
        self.farty_lionhead.disable()
        self.farty_lion = make_me_a_planet(strips.vladfarty.farty_lion)
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
    duration = 15000

    def on_enter(self):
        self.animation_frames = 0

        frente_sprites = build_sprites([
            strips.laupalav.frenteA00,
            strips.laupalav.frenteB01,
            strips.laupalav.frenteC02,
            strips.laupalav.frenteD03,
            strips.laupalav.frenteA04,
            strips.laupalav.frenteB05,
            strips.laupalav.frenteC06,
            strips.laupalav.frenteD07,
            strips.laupalav.frenteA08,
            strips.laupalav.frenteB09,
            strips.laupalav.frenteC10,
            strips.laupalav.frenteD11,
            strips.laupalav.frenteA12,
            strips.laupalav.frenteB13,
            strips.laupalav.frenteC14,
            strips.laupalav.frenteD15,
        ])

        frente_anim = build_animation(frente_sprites, range(16))
        self.frente = lambda frame: frente_anim[(frame // 5) % len(frente_anim)]

        bambi_sprites = build_sprites([
            strips.laupalav.bambi01b,
            strips.laupalav.bambi02b,
            strips.laupalav.bambi03b,
            strips.laupalav.bambi04b,
        ])

        bambi_anim = build_animation(bambi_sprites, [0, 0, 1, 1, 2, 2, 3, 3])
        self.bambi = lambda frame: bambi_anim[(frame // 4) % len(bambi_anim)]

        fondo_sprites = build_sprites([
            strips.laupalav.fondoA00,
            strips.laupalav.fondoB01,
            strips.laupalav.fondoC02,
            strips.laupalav.fondoD03,
            strips.laupalav.fondoA04,
            strips.laupalav.fondoB05,
            strips.laupalav.fondoC06,
            strips.laupalav.fondoD07,
            strips.laupalav.fondoA08,
            strips.laupalav.fondoB09,
            strips.laupalav.fondoC10,
            strips.laupalav.fondoD11,
            strips.laupalav.fondoA12,
            strips.laupalav.fondoB13,
            strips.laupalav.fondoC14,
            strips.laupalav.fondoD15,
            strips.laupalav.fondoA16,
            strips.laupalav.fondoB17,
            strips.laupalav.fondoC18,
            strips.laupalav.fondoD19,
            strips.laupalav.fondoA20,
            strips.laupalav.fondoB21,
            strips.laupalav.fondoC22,
            strips.laupalav.fondoD23,
        ])

        fondo_anim = build_animation(fondo_sprites, range(24))
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
    duration = 3000

    def on_enter(self):
        self.animation_frames = 0

        placa_sprites = build_sprites([
            strips.laupalav.placa
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
    duration = 10000

    def on_enter(self):
        self.animation_frames = 0

        rose_sprites = build_sprites([
            strips.laupalav.rose01,
            strips.laupalav.rose02,
            strips.laupalav.rose03,
            strips.laupalav.rose04,
            strips.laupalav.rose05,
            strips.laupalav.rose06,
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


class Bembidiona(TimedScene):
    duration = 10000

    def on_enter(self):
        self.pollitos = Sprite()
        self.pollitos.set_x(-32)
        self.pollitos.set_y(0)
        self.pollitos.set_strip(strips.other.pollitos)
        self.pollitos.set_frame(0)
        self.pollitos.set_perspective(2)
        self.animation_frames = 0

        self.jere = make_me_a_planet(strips.other.bembi)
        self.jere.set_y(255)
        self.jere.set_frame(0)

    def step(self):
        self.animation_frames += 1
        pf = (self.animation_frames // 4) % 5
        self.pollitos.set_frame(pf)


scenes = [
    Bambi,
    PlacaBambi,
    Rose,
    DancingLions,
    Chanimation,
    Chanijump,
    Bembidiona,
]
