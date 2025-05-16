import io
import sys

from ventilastation.director import director
from ventilastation import sprites
from ventilastation import menu
from ventilastation import povdisplay
from apps import gallery

MAIN_MENU_OPTIONS = [
    ('vyruss', "menu.png", 0, 64),
    ('gallery', "pollitos.png", 0, 64),
    ('ventilagon_game', "menu.png", 1, 64),
    ('vance', "menu.png", 5, 64),
    ('vladfarty', "menu.png", 2, 64),
    ('vugo', "menu.png", 7, 64),
    ('vong', "menu.png", 6, 64),
    ('ventap', "menu.png", 4, 64),
    ('debugmode', "menu.png", 9, 64),
    ('tutorial', "menu.png", 10, 64),
    ('calibrate', "menu.png", 8, 64),
    ('credits', "menu.png", 3, 64),
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
    stripes_rom = "other"

    def on_enter(self):
        super(GamesMenu, self).on_enter()
        print("enter the game menu")
        self.animation_frames = 0
        self.pollitos = self.sprites[1]

        # self.boot_screen = make_me_a_planet(strips.other.ventilastation)
        # self.boot_screen.set_frame(0)
        # self.call_later(1500, self.boot_screen.disable)


    def on_option_pressed(self, option_index):
        option_pressed = self.options[option_index]
        if option_pressed[0] == 'vyruss':
            load_app("vyruss")
            raise StopIteration()
        if option_pressed[0] == 'credits':
            load_app("credits")
            raise StopIteration()
        if option_pressed[0] == 'gallery':
            load_app("gallery")
            raise StopIteration()
        if option_pressed[0] == 'ventap':
            load_app("ventap")
            raise StopIteration()
        if option_pressed[0] == 'vladfarty':
            load_app("vladfarty")
            raise StopIteration()
        if option_pressed[0] == 'ventilagon_game':
            load_app("ventilagon_game")
            raise StopIteration()
        if option_pressed[0] == 'vugo':
            load_app("vugo")
            raise StopIteration()
        if option_pressed[0] == 'vance':
            load_app("vance")
            raise StopIteration()
        if option_pressed[0] == 'vong':
            load_app("vong")
            raise StopIteration()
        if option_pressed[0] == 'calibrate':
            load_app("calibrate")
            raise StopIteration()
        if option_pressed[0] == 'tutorial':
            load_app("tutorial")
            raise StopIteration()
        if option_pressed[0] == 'debugmode':
            load_app("debugmode")
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
            from apps import gallery
            director.push(gallery.Gallery())

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
