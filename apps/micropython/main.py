import io
import sys
import utime

from ventilastation.director import director, stripes
from ventilastation import sprites
from ventilastation import menu
from ventilastation import povdisplay
from ventilastation.shuffler import shuffled

# (rom, image, frame)[] -- see apps/images/menu/stripedefs.py
MAIN_MENU_OPTIONS = [
    ('fanphibious_danger', "fanphibious_danger_2.png", 0),
    ('2bam_sencom', "2bam_sencom.png", 0),
    ('vissile', "domedefander.png", 0),
    ('tincho_vrunner', "tincho_vrunner.png", 0),
    ('peronjam', "peronjam.png", 0),
    ('2bam_demo', "2bam_demo_menu.png", 0),
    ('villalugano_games', "villalugano_games.png", 0),
    # # # 1er Jam 2025
    # ('vortris', "vortris.png", 0),
    ('vailableextreme', "vailableextreme.png", 0),
    # ('vzumaki', "vzumaki.png", 0),
    ('vasura_espacial', "vasura_espacial.png", 0),
    ('vs', "vs.png", 0),
    ('oraculo', "oraculo2.png", 0),
    # ('tvnel', "tvnel.png", 0),
    ('ventrack', "venti808.png", 0),
    # # ('tvnel_alecu', "tvnel_alecu.png", 0),
    # # ('mygame', "mygame.png", 0),
    # # PyCamp 2025
    ('vance', "menu.png", 5),
    # ('vong', "menu.png", 6),
    # ('vugo', "menu.png", 7),
    # # Gallery
    ('gallery', "pollitos.png", 0),
    # # Flash Party 2023
    # ('vladfarty', "menu.png", 2),
    # # Original content
    ('vyruss', "menu.png", 0),
    ('ventilagon_game', "menu.png", 1),
    ('ventap', "menu.png", 4),
    ('debugmode', "menu.png", 9),
    # ('calibrate', "menu.png", 8),
    ('tutorial', "menu.png", 10),
    ('credits', "menu.png", 3),
    ('upgrade', "menu.png", 11),
]

def prepare_uploads():
    import os
    os.remove("main.py")
    import machine
    machine.reset()

def update_over_the_air():
    import ota_update
    director.push(ota_update.Update())

def make_me_a_planet(strip):
    planet = sprites.Sprite()
    planet.set_strip(stripes[strip])
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
    def __init__(self, options, selected_index=0):
        super().__init__(options, selected_index)
        self.last_shuffle = -1
        self.shuffle_options()

    def shuffle_options(self):
        if self.needs_shuffling():
            self.options = shuffled(self.options)
            self.last_shuffle = utime.ticks_ms()

    def needs_shuffling(self):
        return False
        if self.last_shuffle == -1:
            return True
        return utime.ticks_diff(utime.ticks_ms(), self.last_shuffle) > 60000

    def on_enter(self):
        self.shuffle_options()

        super(GamesMenu, self).on_enter()

        self.animation_frames = 0
        self.tincho_frames = 0
        try:
            pollitos_index = [m[1] for m in self.options].index("pollitos.png")
            self.pollitos = self.sprites[pollitos_index]
        except ValueError:
            self.pollitos = None
        try:
            tincho_index = [m[1] for m in self.options].index("tincho_vrunner.png")
            self.es_tincho = self.sprites[tincho_index]
        except ValueError:
            self.es_tincho = None

        # self.boot_screen = make_me_a_planet(strips.other.ventilastation)
        # self.boot_screen.set_frame(0)
        # self.call_later(1500, self.boot_screen.disable)
        self.loviejo = sprites.Sprite()
        self.loviejo.set_strip(stripes["loviejo-3.png"])
        self.loviejo.set_perspective(2)
        self.loviejo.set_x(128 - self.loviejo.width() // 2)
        self.loviejo.set_y(0)
        self.loviejo.set_frame(0)
        self.favalli = make_me_a_planet("favalli.png")
        self.favalli.set_frame(0)
        self.garbage_collect()

    def garbage_collect(self):
        import gc
        gc.collect()
        self.call_later(60000, self.garbage_collect)

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
        # if director.timedout:
        #     load_app("gallery")
        #     raise StopIteration()

        if not self.check_debugmode():
            super(GamesMenu, self).step()

            if director.is_pressed(director.BUTTON_D) \
                and director.is_pressed(director.BUTTON_B)\
                and director.is_pressed(director.BUTTON_C):
                pass
                #update_over_the_air()

            if self.pollitos and self.pollitos.frame() != 255:
                self.animation_frames += 1
                pf = (self.animation_frames // 4) % 5
                self.pollitos.set_frame(pf)

            if self.es_tincho and self.es_tincho.frame() != 255:
                self.tincho_frames += 1
                pf = (self.tincho_frames // 6) % 2
                self.es_tincho.set_frame(pf)

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
        raise
        # buf = io.StringIO()
        # sys.print_exception(e, buf)
        # director.report_traceback(buf.getvalue().encode("utf-8"))
        # print(buf.getvalue())
        # #machine.reset()