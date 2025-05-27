import io
import sys

from ventilastation.director import director
from ventilastation import sprites
from ventilastation import menu
from ventilastation import povdisplay

MAIN_MENU_OPTIONS = [
#    ('mygame', "mygame.png", 0),
    ('mijuegui', "mygame.png", 0),
    ('uzumaki', "mygame.png", 0),
    ('vyruss', "menu.png", 0),
    ('gallery', "pollitos.png", 0),
    ('ventilagon_game', "menu.png", 1),
    ('vance', "menu.png", 5),
    ('vladfarty', "menu.png", 2),
    ('vong', "menu.png", 6),
    ('ventap', "menu.png", 4),
    ('vugo', "menu.png", 7),
    ('tutorial', "menu.png", 10),
    ('debugmode', "menu.png", 9),
    ('calibrate', "menu.png", 8),
    ('credits', "menu.png", 3),
]

def update_over_the_air():
    import ota_update
    director.push(ota_update.Update())

def make_me_a_planet(strip):
    planet = sprites.Sprite()
    planet.set_strip(strip)
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(255)
    return planet

def load_app(modulename):
    full_modulename = "apps." + modulename
    module = __import__(full_modulename, globals, locals, [modulename])
    main_scene = module.main()
    director.push(main_scene)
    if full_modulename in sys.modules:
        del sys.modules[full_modulename]

class GamesMenu(menu.Menu):
    stripes_rom = "menu"

    def on_enter(self):
        super(GamesMenu, self).on_enter()
        self.animation_frames = 0
        try:
            pollitos_index = [m[1] for m in MAIN_MENU_OPTIONS].index("pollitos.png")
            self.pollitos = self.sprites[pollitos_index]
        except ValueError:
            self.pollitos = None

        # self.boot_screen = make_me_a_planet(strips.other.ventilastation)
        # self.boot_screen.set_frame(0)
        # self.call_later(1500, self.boot_screen.disable)

    def on_option_pressed(self, option_index):
        app_chosen = self.options[option_index][0]
        load_app(app_chosen)
        raise StopIteration()

    def check_debugmode(self):
        if (director.is_pressed(director.JOY_UP)
            and director.is_pressed(director.JOY_LEFT)
            and director.is_pressed(director.JOY_RIGHT)
            and director.is_pressed(director.BUTTON_A) ):
            from apps.debugmode import DebugMode
            director.push(DebugMode())
            return True

        if (director.is_pressed(director.BUTTON_B)
            and director.is_pressed(director.BUTTON_C)
            and director.is_pressed(director.BUTTON_A) ):
            from apps.calibrate import Calibrate
            director.push(Calibrate())
            return True
            
    def step(self):
        if director.timedout:
            load_app("gallery")
            raise StopIteration()

        if not self.check_debugmode():
            super(GamesMenu, self).step()

            if director.is_pressed(director.BUTTON_D) \
                and director.is_pressed(director.BUTTON_B)\
                and director.is_pressed(director.BUTTON_C):
                pass
                #update_over_the_air()

            if self.pollitos:
                self.animation_frames += 1
                pf = (self.animation_frames // 4) % 5
                self.pollitos.set_frame(pf)

def main():
    # init images
    menu = GamesMenu(MAIN_MENU_OPTIONS)
    menu.call_later(700, menu.load_images)
    director.push(menu)
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
