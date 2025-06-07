import utime
from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite

def make_me_a_planet(strip):
    planet = Sprite()
    planet.set_strip(stripes[strip])
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet

def build_sprites(strips):
    return [make_me_a_planet(s) for s in strips]

def build_animation(sprites, order):
    return [sprites[n] for n in order]
class TimedScene(Scene):
    keep_music = True
    def __init__(self):
        super().__init__()
        self.scene_start = utime.ticks_ms()
        if self.duration:
            print("Scene starting: ", self.__class__.__name__,
                " starts (ms): ", self.scene_start,
                " will end: ", utime.ticks_add(self.scene_start, self.duration))
            self.call_later(self.duration, self.finish_scene)

    def on_exit(self):
        print("Scene finished: ", self.__class__.__name__,
            " duration (ms): ", utime.ticks_diff(utime.ticks_ms(), self.scene_start),
            " current time: ", utime.ticks_ms())
        pass

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
        # print("Later called to finish scene, current time: ", utime.ticks_ms())
        director.pop()
class FinalScene(TimedScene):
    duration = 4000
    def __init__(self, text):
        super().__init__()
        self.text = text

    def on_enter(self):
        super().on_enter()
        self.textImagen = Sprite()
        self.textImagen.set_strip(stripes[self.text])
        self.textImagen.set_perspective(2)
        self.textImagen.set_x(128 - self.textImagen.width() // 2)
        self.textImagen.set_y(0)
        self.textImagen.set_frame(0)
    
    def step(self):
        super().step()
        if director.was_pressed(director.BUTTON_A) or director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()
class SpriteAnimationScene(TimedScene):
    sprite_files = []
    order = []
    imageText = ""
    soundImage = "oraculo/audio02"

    def on_enter(self):
        super().on_enter()
        director.music_play(b"oraculo/audio02")
        sprites = build_sprites(self.sprite_files)
        anim = build_animation(sprites, self.order)
        self.frente = lambda frame: anim[(frame // len(self.order)) % len(anim)]
        self.animation_frames = 0

    def step(self):
        self.animation_frames += 1
        ns = self.frente(self.animation_frames)
        self.frente(self.animation_frames - 1).disable()
        ns.set_frame(0)
    
    def on_exit(self):
        super().on_exit()
        print("Imagen de texto: ", self.imageText)
        director.push(FinalScene(self.imageText))
class Animation1(SpriteAnimationScene):
    duration = 4000
    imageText = "09CAMINO.png"
    sprite_files = [
        "09camino0000.png",
        "09camino0003.png",
        "09camino0006.png",
        "09camino0008.png",
    ]
    order = list(range(4))
class Animation2(SpriteAnimationScene):
    duration = 4000
    imageText = "08PANUELO.png"
    sprite_files = [
        "08pañuelo0000.png",
        "08pañuelo0003.png",
        "08pañuelo0006.png",
        "08pañuelo0012.png",
        "08pañuelo0014.png",
    ]
    order = list(range(5))
class Animation3(SpriteAnimationScene):
    duration = 4000
    imageText = "07AMOR.png"
    sprite_files = [
        "07amor0000.png",
        "07amor0003.png",
        "07amor0006.png",
        "07amor0009.png",
        "07amor0012.png",
    ]
    order = list(range(5))
class Animation4(SpriteAnimationScene):
    duration = 4000
    imageText = "06AMISTAD.png"
    sprite_files = [
        "06amistad0000.png",
        "06amistad0003.png",
        "06amistad0006.png",
        "06amistad0009.png",
        "06amistad0010.png"
    ]
    order = list(range(5))
class Animation5(SpriteAnimationScene):
    duration = 4000
    imageText = "05COMUNIDAD.png"
    sprite_files = [
        "05comunidad0000.png",
        "05comunidad0002.png",
        "05comunidad0004.png",
        "05comunidad0006.png",
        "05comunidad0008.png",
    ]
    order = list(range(5))
class Animation6(SpriteAnimationScene):
    duration = 4000
    imageText = "04FERNET.png"
    sprite_files = [
        "04fernet0000.png",
        "04fernet0003.png",
        "04fernet0006.png",
        "04fernet0009.png",
        "04fernet0012.png",
        "04fernet0017.png",
    ]
    order = list(range(6))
class Animation7(SpriteAnimationScene):
    duration = 4000
    imageText = "03FUEGO.png"
    sprite_files = [
        "03fuego0000.png",
        "03fuego0003.png",
        "03fuego0006.png",
        "03fuego0009.png",
    ]
    order = list(range(4))
class Animation8(SpriteAnimationScene):
    duration = 4000
    imageText = "02RATIS.png"
    sprite_files = [
        "02ratis0000.png",
        "02ratis0003.png",
        "02ratis0006.png",
        "02ratis0009.png",
    ]
    order = list(range(4))
class Animation9(SpriteAnimationScene):
    duration = 4000
    imageText = "01MUSICA.png"
    sprite_files = [
        "01musica0000.png",
        "01musica0003.png",
        "01musica0006.png",
        "01musica0009.png",
    ]
    order = list(range(4))
class RuletaX:
    def __init__(self, strip_name, x, y):
        self.sprite = Sprite()
        self.sprite.set_strip(stripes[strip_name])
        self.sprite.set_frame(0)
        self.sprite.set_perspective(0)
        self.sprite.set_x(x)
        self.sprite.set_y(y)
        self.velocidad = 0  # <-- inicializa con x, no con 0
        self.x_inicial = x  # <-- guarda la posición inicial
        self.nombre = strip_name

    def set_pos(self, dx):
        self.velocidad += dx
        self.sprite.set_x(self.velocidad)
    
    def reset(self):
        self.velocidad = self.x_inicial
        self.sprite.set_x(self.x_inicial)
    
    def return_element(self):
        return self.nombre
class Oraculo(Scene):
    def on_enter(self):
        super(Oraculo, self).on_enter()
        director.music_play(b"oraculo/ruleta")
        self.bola = Sprite()
        self.bola.set_strip(stripes["ball.png"])
        self.bola.set_x(128 - self.bola.width()//2)
        self.bola.set_y(16)
        self.bola.set_frame(6)
        self.volocidadBola = 0;

        self.ruletas = []
        num_ruletas = 9
        for i in range(num_ruletas):
            nombre = f"{i+1}.png"
            angulo = i * (256 // num_ruletas) 
            self.ruletas.append(RuletaX(nombre, angulo, 255))

        self.nuevaVelocidad = 3;
        self.detener = False
        self.wait_timer = None
        self.seleccionada = None

    def step(self):
        if director.was_pressed(director.JOY_DOWN):
            self.detener = True

        if self.detener and self.nuevaVelocidad > 0:
            self.nuevaVelocidad -= 0.02
            if self.nuevaVelocidad < 0:
                self.nuevaVelocidad = 0
        
        dx = int(self.nuevaVelocidad) if self.nuevaVelocidad > 0 else 0        
        for ruleta in self.ruletas:
            ruleta.set_pos(dx)
        
        if dx == 0 and self.wait_timer is None:
            angulo_bola = 0
            min_diff = 9999
            self.seleccionada = None
            for ruleta in self.ruletas:
                angulo_actual = (ruleta.x_inicial + ruleta.velocidad) % 256
                diff = abs((angulo_actual - angulo_bola + 128) % 256 - 128)
                if diff < min_diff:
                    min_diff = diff
                    self.seleccionada = ruleta
            if self.seleccionada:
                director.sound_play(b"oraculo/click")
                print("Ruleta detenida:", self.seleccionada.nombre)
                self.wait_timer = utime.ticks_ms()

        if self.wait_timer is not None and self.seleccionada is not None:
            if utime.ticks_diff(utime.ticks_ms(), self.wait_timer) > 2000:
                numero = int(self.seleccionada.nombre.split(".")[0])
                new_scene_class = scenes[numero]
                director.push(new_scene_class())
                self.wait_timer = None
        
        if director.was_pressed(director.JOY_UP):
            self.nuevaVelocidad = 3
            self.detener = False
        
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()
class Inicio(TimedScene):
    duration = 4000
    stripes_rom = "oraculo"
    def on_enter(self):
        super(Inicio, self).on_enter()
        self.text = Sprite()
        self.text.set_strip(stripes["titulo.png"])
        self.text.set_perspective(0)
        self.text.set_x(0)
        self.text.set_y(255)
        self.text.set_frame(0)
    
    def step(self):
        super(Inicio, self).step()            
        if director.was_pressed(director.BUTTON_A):
            director.push(Oraculo())
        elif director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()
        
scenes = [
    Inicio,
    Animation1,
    Animation2,
    Animation3,
    Animation4,
    Animation5,
    Animation6,
    Animation7,
    Animation8,
    Animation9,
]      

def main():
    return Inicio()