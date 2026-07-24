import utime

from ventilastation import menu
from ventilastation import native_apps
from ventilastation import sprites
from ventilastation.app_loader import load_app
from ventilastation.catalog import build_menu_options
from ventilastation.director import director, stripes
from ventilastation.scene import Scene
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
    (30, "native.nes", "nes.png", 0),
    (40, "native.sms", "sms.png", 0),
    (50, "native.gb", "gameboy.png", 0),
    (60, "native.msx", "msx.png", 0),
    (70, "gallery", "pollitos.png", 0),
    (240, "credits", "menu.png", 3),
]

# Text rows use one combined 4x6 strip.  Frames 0..127 are white ASCII and
# frames 128..254 are the matching red glyphs.  Four rows x 21 glyphs stay
# within the hardware's 100-sprite limit.
FONT_STRIP = "tinyfont_menu.png"
FONT_WIDTH = 4
FONT_HEIGHT = 6
ROM_LABEL_CHARS = 21
VISIBLE_ROM_ROWS = 4
SELECTED_ROM_Y = FONT_HEIGHT
ROM_ROW_STEP = FONT_HEIGHT * 2

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


class RomTextRow:
    """A fixed-width, one-colour line rendered from the combined tiny font."""

    def __init__(self):
        self.sprites = []
        for index in range(ROM_LABEL_CHARS):
            sprite = sprites.Sprite()
            sprite.set_strip(stripes[FONT_STRIP])
            # Coordinate zero is the display's bottom centre.  Descending x
            # matches the existing font renderer's clockwise POV orientation.
            sprite.set_x((ROM_LABEL_CHARS * FONT_WIDTH // 2 - index * FONT_WIDTH) % 256)
            sprite.set_perspective(2)
            sprite.set_frame(0)
            self.sprites.append(sprite)

    def hide(self):
        for sprite in self.sprites:
            sprite.disable()

    def show(self, text, y, red=False):
        text = text[:ROM_LABEL_CHARS]
        for index, sprite in enumerate(self.sprites):
            sprite.set_y(y)
            if index < len(text):
                code = ord(text[index])
                # The packed strip has ASCII glyphs only.  ROM discovery has
                # already normalised labels, but retain this guard for status
                # strings and future callers.
                if code < 32 or code > 126:
                    code = ord("?")
                if red:
                    code |= 0x80
                sprite.set_frame(code)
            else:
                sprite.set_frame(0)


class RomLibraryMenu(Scene):
    """A virtualised ROM list that keeps the selection at the readable bottom."""

    stripes_rom = "other"

    def __init__(self, slug, selected_rom=None):
        super().__init__()
        self.slug = slug
        self.selected_rom = selected_rom
        self.entries = []
        self.selected_index = 0
        self.rows = []

    def on_enter(self):
        super().on_enter()
        self.entries = native_apps.list_roms(self.slug)
        self.selected_index = self._selected_entry_index()
        self.rows = [RomTextRow() for _ in range(VISIBLE_ROM_ROWS)]
        self._render_rows()

    def _selected_entry_index(self):
        if not self.selected_rom:
            return 0
        for index, entry in enumerate(self.entries):
            if entry["path"] == self.selected_rom:
                return index
        return 0

    def _render_rows(self):
        if not self.entries:
            self.rows[0].show("NO ROMS", SELECTED_ROM_Y, red=True)
            for row in self.rows[1:]:
                row.hide()
            return
        for row_index, row in enumerate(self.rows):
            entry_index = self.selected_index + row_index
            if entry_index >= len(self.entries):
                row.hide()
                continue
            row.show(
                self.entries[entry_index]["label"],
                SELECTED_ROM_Y + row_index * ROM_ROW_STEP,
                red=row_index == 0,
            )

    def _move(self, delta):
        if not self.entries:
            return
        new_index = self.selected_index + delta
        if new_index < 0:
            new_index = 0
        if new_index >= len(self.entries):
            new_index = len(self.entries) - 1
        if new_index != self.selected_index:
            self.selected_index = new_index
            native_apps.remember_rom_selection(
                self.slug, self.entries[self.selected_index]["path"]
            )
            director.sound_play(b"alecu.vyruss/shoot3")
            self._render_rows()

    def _launch_selected(self):
        if not self.entries:
            return
        entry = self.entries[self.selected_index]
        native_apps.remember_rom_selection(self.slug, entry["path"])
        director.sound_play(b"alecu.vyruss/shoot1")
        native_apps.launch_native_scene(self.slug, entry["path"])
        raise StopIteration()

    def step(self):
        # Match the main menu's controller direction convention.
        if director.was_pressed(director.JOY_DOWN):
            self._move(-1)
        if director.was_pressed(director.JOY_UP):
            self._move(1)
        if director.was_pressed(director.BUTTON_A):
            self._launch_selected()
        if director.was_pressed(director.BUTTON_D):
            native_apps.leave_rom_menu(self.slug)
            director.pop()
            raise StopIteration()


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
        if native_apps.has_rom_library(app_chosen):
            native_apps.remember_rom_selection(app_chosen)
            director.push(RomLibraryMenu(app_chosen))
            raise StopIteration()
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


def _main_menu_index(slug):
    for index, option in enumerate(MAIN_MENU_OPTIONS):
        if option[0] == slug:
            return index
    return 0


def main(launcher_state=None):
    launcher_state = launcher_state or native_apps.read_launcher_state()
    return GamesMenu(MAIN_MENU_OPTIONS, _main_menu_index(launcher_state.get("main_slug")))


def setup():
    launcher_state = native_apps.consume_native_return()
    launcher = main(launcher_state)
    # director.push() below calls on_enter() synchronously, which (via
    # Scene.on_enter()) already runs load_images() once. A second, deferred
    # load_images() here used to re-run director.load_rom(), allocating a
    # fresh romdata buffer and overwriting Director._stripe_buffers -- while
    # the sprites this same on_enter() just created were still holding their
    # own cached pointers into the *first* buffer, now unreachable. That
    # buffer sat untouched (MicroPython's GC doesn't compact) until the next
    # gc.collect() actually reclaimed and reused its memory, at which point
    # every sprite still pointing at it started rendering whatever new data
    # landed there -- the menu-sprite-corruption bug. See
    # docs/internals/menu-sprite-corruption.md.
    director.push(launcher)
    submenu_slug = launcher_state.get("submenu_slug")
    if submenu_slug and native_apps.has_rom_library(submenu_slug):
        director.push(RomLibraryMenu(submenu_slug, launcher_state.get("rom_path")))
