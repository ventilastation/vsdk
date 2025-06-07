# -*- coding: cp437 -*-

from urandom import randrange
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
import utime, gc

# este valor depende del tamaño de la letra
STEP = 9
RESERVED_SPRITES = 90
WARMUP_STEPS = 500

def quitar_newlines(texto):
    # Quita los saltos de línea y los espacios dobles del texto
    texto = " ".join(texto.split()).replace("  ", " ")
 
    # Reemplaza caracteres de UTF-8 con sus equivalentes en CP437
    # Esto es necesario porque Micropython solo soporta UTF-8
    # mientras que el font que usamos es del CP437 de MS-DOS.
    texto = texto.replace("ñ", "\xa4")
    texto = texto.replace("á", "\xa0")
    texto = texto.replace("é", "\x82")
    texto = texto.replace("í", "\xa1")
    texto = texto.replace("ó", "\xa2")
    texto = texto.replace("ú", "\xa4")
    return texto

texto1 = quitar_newlines("""
La oscuridad detrás de tus párpados es de una profundidad abismal.
Cerrás los ojos y esperás ver la luz del sol a través de esa lamina finita de piel,
roja, difuminada, intensa, pero te encontrás con el vacío. En esos pocos milímetros
de membrana se esconde la inmensidad del cielo nocturno. La sensación de vértigo te
recorre el cuerpo y es como que cayeras hacia arriba, hacia adentro, hacia ese infinito
hueco que se abre desde el centro de tu ser y que amenaza con devorar al mundo. Ya no
podés volver a abrir los ojos, es demasiado tarde. A lo lejos, en la oscuridad, aparecen
puntos de luz pálida, rojos, amarillos, verdes, blancos, y con el tiempo se acercan y se
esparcen, entrelazandose en constelaciones y nebulas qué crecen y pasan por encima de tu
vista en esa unánime noche.
""")

texto2a = quitar_newlines("""
Los pétalos blancos de la rosa que sostenés entre tus dedos crecen
en espiral desde su centro,
""")

texto2b = quitar_newlines("""
yendo de pequeños a grandes, una corona fractal de dientes, como la boca de una lamprea
de mar, qué hunde sus colmillos en un tiburón dejando en su piel una rosa de sangre,
roja como los pétalos de la rosa que sostenés entre tus dedos que crecen en espiral
desde su centro, yendo de grandes a pequeños, un anillo de llamas qué arden en la 
oscuridad de la noche, un fuego que consume deltas y montes lanzando sus cenizas
blancas al viento, blancas como los pétalos de la rosa que sostenés entre tus dedos
que crecen en espiral desde su centro,
""")

def uzugen1():
    while True:
        for c in texto1:
            yield c

def uzugen2():
    for c in texto2a:
        yield c
    while True:
        for c in texto2b:
            yield c

class Letter(Sprite):
    def __init__(self):
        super().__init__()
        self.disable()
        self.set_perspective(1)
        self.set_strip(stripes["vga_cp437.png"])
    
    def reset_char(self, char):
        self.disable()
        self.position = RESERVED_SPRITES * STEP
        self.update_screenpos()
        self.set_frame(ord(char))

    def update_screenpos(self):
        self.set_x(-(self.position - 64) % 256)
        dest_y = self.position // 4
        self.set_y(dest_y)

    def step_out(self):
        self.position -= 1
        self.update_screenpos()

    def finished(self):
        return self.position <= 15


class Vzumaki(Scene):
    stripes_rom = "vzumaki"
    phrase = texto1

    def on_enter(self):
        super().on_enter()
        self.phrase_generator = uzugen2() if randrange(2) else uzugen1()

        self.letters = []
        self.unused_letters = []
        for n in range(RESERVED_SPRITES):
            letter = Letter()
            self.unused_letters.append(letter)

        self.counter = 0

        for n in range(WARMUP_STEPS):
            self.step_letters()

    def step(self):
        super().step()

        velocity = 1

        if director.is_pressed(director.BUTTON_A) or director.is_pressed(director.JOY_DOWN):
            velocity = 4

        for n in range(velocity):
            self.step_letters()

        if director.was_pressed(director.BUTTON_D):
            self.finished()
        
        gc.collect()

    def step_letters(self):
        if self.counter % STEP == 0:
            c = next(self.phrase_generator)
            l = self.unused_letters.pop()
            l.reset_char(c)
            self.letters.append(l)
            # print(len(self.unused_letters), len(self.letters))

        self.counter += 1

        for l in self.letters:
            l.step_out()
            if l.finished():
                self.unused_letters.append(l)
                self.letters.remove(l)

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Vzumaki()