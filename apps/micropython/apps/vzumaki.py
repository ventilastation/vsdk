# -*- coding: cp437 -*-

from urandom import choice, randrange, seed
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
from ventilastation.sprites import Sprite
import utime

def quitar_newlines(texto):
    """Quita los saltos de línea y los espacios dobles de un texto."""
    texto = " ".join(texto.split()).replace("  ", " ")
    # Reemplaza caracteres de UTF-8 con sus equivalentes en cp437
    # Esto es necesario porque Micropython no soporta UTF-8.
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
de mar, qué hunde sus colmillos en un tiburón, dejando en su piel una rosa de sangre,
roja como la que sostenés entre tus dedos, sus pétalos crecen en espiral desde su centro,
yendo de grandes a pequeños, un anillo de llamas qué arden en la oscuridad de la noche,
un fuego que consume deltas y montes lanzando sus cenizas blancas al viento,
blancas como los pétalos de rosa que sostenés entre tus dedos
y que crecen en espiral desde su centro,
""")

class Letter(Sprite):
    def __init__(self):
        super().__init__()
        self.disable()
        self.set_perspective(1)
        self.set_strip(stripes["vga_cp437.png"])
    
    def set_char(self, char, n):
        self.disable()
        self.set_x(-n * 9)
        self.set_y(int(n * 2))
        self.set_frame(ord(char))
        self.position = 200 + n * 9

    def step_out(self):
        self.position -= 1
        self.set_x(-(self.position - 64) % 256)
        self.set_y(int(self.position / 4))


class Vzumaki(Scene):
    stripes_rom = "vzumaki"
    phrase = texto1

    def on_enter(self):
        super().on_enter()
        self.letters = []
        for n in range(90):
            letter = Letter()
            letter.set_char(self.phrase[n], n)
            self.letters.append(letter)

    def step(self):
        super().step()
        for l in self.letters:
            l.step_out()

        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


def main():
    return Vzumaki()