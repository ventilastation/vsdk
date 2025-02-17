import io
import sys

from ventilastation.director import director
from ventilastation import imagenes
from ventilastation import sprites
from ventilastation import menu
from ventilastation.imagenes import strips

def update_over_the_air():
    import ota_update
    director.push(ota_update.Update())

class GamesMenu(menu.Menu):
    OPTIONS = [
        ('vyruss', strips.other.menu, 0, 64),
        #('bembi', strips.other.pollitos, 0, 64),
        ('laupalav', strips.other.pollitos, 0, 64),
        ('vladfarty', strips.other.menu, 2, 64),
        #('credits', strips.other.menu, 3, 64),
        #('ventap', strips.other.menu, 4, 64),
        ('ventilagon', strips.other.menu, 1, 64),
    ]

    def on_enter(self):
        super(GamesMenu, self).on_enter()
        self.animation_frames = 0
        self.pollitos = self.sprites[1]

    def on_option_pressed(self, option_index):
        option_pressed = self.options[option_index]
        print(option_pressed)
        if option_pressed[0] == 'vyruss':
            from apps import vyruss
            director.push(vyruss.VyrusGame())
            raise StopIteration()
        if option_pressed[0] == 'credits':
            from apps import credits
            director.push(credits.Credits())
            raise StopIteration()
        if option_pressed[0] == 'bembi':
            from apps import bembi
            director.push(bembi.Bembidiona())
            raise StopIteration()
        if option_pressed[0] == 'laupalav':
            from apps import laupalav
            director.push(laupalav.LauraPalavecino())
            raise StopIteration()
        if option_pressed[0] == 'ventap':
            from apps import ventap
            director.push(ventap.Ventap())
            raise StopIteration()
        if option_pressed[0] == 'vladfarty':
            from apps import vladfarty
            director.push(vladfarty.VladFarty())
            raise StopIteration()
        if option_pressed[0] == 'ventilagon':
            from apps import ventilagon_game
            director.push(ventilagon_game.VentilagonGame())
            raise StopIteration()

    def check_debugmode(self):
        if (director.is_pressed(director.JOY_UP)
            and director.is_pressed(director.JOY_LEFT)
            and director.is_pressed(director.JOY_RIGHT)
            and director.is_pressed(director.BUTTON_A) ):
            from apps.debugmode import DebugMode
            director.push(DebugMode())
            return True
            
    def step(self):
        if not self.check_debugmode():
            super(GamesMenu, self).step()

            if director.is_pressed(director.BUTTON_D) \
                and director.is_pressed(director.BUTTON_B)\
                and director.is_pressed(director.BUTTON_C):
                pass
                #update_over_the_air()

            self.animation_frames += 1
            pf = (self.animation_frames // 4) % 5
            self.pollitos.set_frame(pf)

def main():
    # init images
    for n, strip in enumerate(imagenes.all_strips):
        sprites.set_imagestrip(n, strip)
    director.push(GamesMenu())
    director.run()

if __name__ == '__main__':
    import machine
    try:
        director.sound_play(b"vyruss/shoot3")
        main()
    except Exception as e:
        buf = io.StringIO()
        sys.print_exception(e, buf)
        director.report_traceback(buf.getvalue().encode("utf-8"))
        print(buf.getvalue())
        #machine.reset()
