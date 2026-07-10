import utime

from ventilastation import menu
from ventilastation import sprites
from ventilastation.app_loader import load_app
from ventilastation.catalog import build_menu_options
from ventilastation.director import director, stripes
from ventilastation.shuffler import shuffled

def game_menu_strip(game_slug):
    return game_slug.replace(".", "/") + "/menu.png"

# Games are discovered from games/<group>/<name>/ and positioned by the
# "order" field in each game's meta.json (see ventilastation/catalog.py).
# Only the non-game entries -- native apps and system scenes -- are listed
# here, with the order values that interleave them among the games.
STATIC_MENU_ENTRIES = [
    (2, "tutorial_vs2", "menu.png", 10),
    (20, "native.voom", "voom.png", 0),
    (30, "native.nes", "megadrive.png", 0),   # Super Mario Bros (NES); placeholder icon
    (40, "native.sms", "megadrive.png", 0),   # Out Run (Master System); placeholder icon
    (70, "gallery", "pollitos.png", 0),
    (240, "credits", "menu.png", 3),
]

MAIN_MENU_OPTIONS = build_menu_options(STATIC_MENU_ENTRIES)

SYS_MENU_OPTIONS = [
    # Retro-Go launcher disabled for now — its on-screen text is unreadable at the
    # POV display's resolution. Emulators are launched directly (see native.genesis).
    # ("native.launcher", "voom.png", 0),
    ("debugmode", "menu.png", 9),
    # ("calibrate", "menu.png", 8),
    ("tutorial", "menu.png", 10),
    ("tutorial_vs2", "menu.png", 10),
    ("settings", "menu.png", 8),
    ("alecu.vyruss", game_menu_strip("alecu.vyruss"), 0),
    ("alecu.ventilagon_game", game_menu_strip("alecu.ventilagon_game"), 0),
    ("credits", "menu.png", 3),
]


def make_me_a_planet(strip):
    planet = sprites.Sprite()
    planet.set_strip(stripes[strip])
    planet.set_perspective(0)
    planet.set_x(0)
    planet.set_y(220)
    return planet


class SystemMenu(menu.Menu):
    stripes_rom = "menu"

    def on_enter(self):
        self.garbage_collect()
        super().on_enter()

    def garbage_collect(self):
        import gc

        gc.collect()
        self.call_later(60000, self.garbage_collect)

    def on_option_pressed(self, option_index):
        app_chosen = self.options[option_index][0]
        load_app(app_chosen)
        raise StopIteration()

    def step(self):
        super().step()
        if director.was_pressed(director.BUTTON_D):
            self.finished()

    def finished(self):
        director.pop()
        raise StopIteration()


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
        super().on_enter()
        director.music_off()

        self.animation_frames = 0
        self.tincho_frames = 0
        try:
            pollitos_index = [m[1] for m in self.options].index("pollitos.png")
            self.pollitos = self.sprites[pollitos_index]
        except ValueError:
            self.pollitos = None
        try:
            tincho_index = [m[1] for m in self.options].index(game_menu_strip("vsjam-oct25.tincho_vrunner"))
            self.es_tincho = self.sprites[tincho_index]
        except ValueError:
            self.es_tincho = None

        self.vslogo = sprites.Sprite()
        self.vslogo.set_strip(stripes["vslogo.png"])
        self.vslogo.set_perspective(2)
        self.vslogo.set_x(128 - self.vslogo.width() // 2)
        self.vslogo.set_y(0)
        self.vslogo.set_frame(0)

        self.loviejo = sprites.Sprite()
        self.loviejo.set_strip(stripes["loviejo-3.png"])
        self.loviejo.set_perspective(2)
        self.loviejo.set_x(128 - self.loviejo.width() // 2)
        self.loviejo.set_y(11)
        self.loviejo.set_frame(0)

        self.fondo = make_me_a_planet("favalli.png")
        self.fondo.set_frame(0)
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
        if (
            director.is_pressed(director.JOY_UP)
            and director.is_pressed(director.JOY_LEFT)
            and director.is_pressed(director.JOY_RIGHT)
            and director.is_pressed(director.BUTTON_A)
        ):
            director.sound_play("ventilagon/audio/es/superventilagon")
            director.push(SystemMenu(SYS_MENU_OPTIONS))
            return True

        if (
            director.is_pressed(director.BUTTON_B)
            and director.is_pressed(director.BUTTON_C)
            and director.is_pressed(director.BUTTON_A)
        ):
            return True

    def step(self):
        if not self.check_debugmode():
            super().step()

            if (
                director.is_pressed(director.BUTTON_D)
                and director.is_pressed(director.BUTTON_B)
                and director.is_pressed(director.BUTTON_C)
            ):
                pass

            if self.pollitos and self.pollitos.frame() != 255:
                self.animation_frames += 1
                pf = (self.animation_frames // 4) % 5
                self.pollitos.set_frame(pf)

            if self.es_tincho and self.es_tincho.frame() != 255:
                self.tincho_frames += 1
                pf = (self.tincho_frames // 6) % 2
                self.es_tincho.set_frame(pf)


def main():
    return GamesMenu(MAIN_MENU_OPTIONS)


def setup():
    launcher = main()
    launcher.call_later(700, launcher.load_images)
    director.push(launcher)
