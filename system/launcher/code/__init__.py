import vs2
from vs2.controls import A, BACK, DOWN, LEFT, RIGHT, UP, Y, joy1

from ventilastation import catalog
from ventilastation import native_apps
from ventilastation.app_loader import load_app
from ventilastation.director import director, stripes

def game_menu_strip(game_slug):
    return game_slug.replace(".", "/") + "/menu.png"

# Entries that aren't part of any games/<group>/ folder -- system scenes
# with no group to move into. Everything else (games, native apps) is
# reached through a group tile built by _build_groups_and_tiles() below.
# These strips are real, dedicated art (a pollitos.png icon, wordmark
# frames inside menu.png) so they render as icons rather than labels.
STATIC_MENU_ENTRIES = [
    (2, "tutorial_vs2", "menu.png", 10, "Tutorial"),
    (70, "gallery", "pollitos.png", 0, "Gallery"),
    (240, "credits", "menu.png", 3, "Credits"),
]

GROUP_PREFIX = "group:"

# Order and label for each games/<group>/ folder's top-level tile. A folder
# not listed here (a new group added later) still gets a tile -- just at the
# end of the menu, labelled from its folder name (see _build_groups_and_tiles).
FOLDER_GROUP_ORDER = {
    "alecu": 30,
    "other": 35,
    "vsjam-may25": 40,
    "vsjam-oct25": 50,
    "pycamp-mar25": 60,
}
GROUP_LABELS = {
    "emulators": "Emulators",
    "alecu": "Alecu",
    "other": "Other",
    "vsjam-may25": "VS Jam May 25",
    "vsjam-oct25": "VS Jam Oct 25",
    "pycamp-mar25": "PyCamp Mar 25",
    "tech_demos": "Tech Demos",
}

# Renamed from the old "native" group -- these are the only slugs that hand
# off to a native (non-MicroPython) partition. Icons predate per-game
# menu.png discovery so they're hand-picked here rather than derived.
EMULATOR_ICONS = {
    "emulators.voom": "voom.png",
    "emulators.nes": "nes.png",
    "emulators.sms": "sms.png",
    "emulators.gb": "gameboy.png",
    "emulators.msx": "msx.png",
}

# VS2 Hardware Acceptance lives under system/, not games/, so it isn't found
# by catalog.discover_tech_demo_entries() -- it's the one hand-added member
# of the synthetic Tech Demos group.
TECH_DEMO_STATIC_ENTRIES = [
    (0, "vs2_hardware", "menu.png", 0, "VS2 Hardware Acceptance"),
]

# The secret debug menu (see GroupsMenu's button-combo check). Two entries
# borrow real game icons; the rest fall back to a label like a group tile.
SYS_MENU_OPTIONS = [
    ("debugmode", "menu.png", 9, "Debug Mode"),
    ("tutorial", "menu.png", 10, "Tutorial"),
    ("tutorial_vs2", "menu.png", 10, "Tutorial VS2"),
    ("settings", "menu.png", 8, "Settings"),
    ("alecu.vyruss", game_menu_strip("alecu.vyruss"), 0, "Vyruss"),
    ("alecu.ventilagon_game", game_menu_strip("alecu.ventilagon_game"), 0, "Ventilagon"),
    ("credits", "menu.png", 3, "Credits"),
]


def group_tile_id(group_name):
    return GROUP_PREFIX + group_name


def is_group_tile(option_id):
    return option_id.startswith(GROUP_PREFIX)


def _group_label(group_name):
    return GROUP_LABELS.get(group_name, catalog.prettify_name(group_name))


def _emulator_options():
    options = []
    for slug, spec in native_apps.APP_REGISTRY.items():
        strip = EMULATOR_ICONS.get(slug)
        options.append((slug, strip, 0, spec["title"]))
    return options


def _build_groups_and_tiles():
    """Return (tiles, members): tiles are (order, id, strip, frame, title)
    entries merged into MAIN_MENU_OPTIONS; members maps each group's tile id
    to its own sorted (slug, strip, frame, title) option list, built once so
    opening/closing a group never re-walks the filesystem. Group tiles get
    strip=None -- there's no dedicated art for "a folder of games", and
    borrowing another image for it is exactly what looked wrong before."""
    tiles = []
    members = {}

    emulators_id = group_tile_id("emulators")
    members[emulators_id] = _emulator_options()
    tiles.append((20, emulators_id, None, 0, _group_label("emulators")))

    for group_name, entries in catalog.discover_groups():
        tile_id = group_tile_id(group_name)
        members[tile_id] = catalog.build_menu_options([], entries)
        order = FOLDER_GROUP_ORDER.get(group_name, catalog.DEFAULT_ORDER)
        tiles.append((order, tile_id, None, 0, _group_label(group_name)))

    tech_demos_id = group_tile_id("tech_demos")
    members[tech_demos_id] = catalog.build_menu_options(
        TECH_DEMO_STATIC_ENTRIES, catalog.discover_tech_demo_entries())
    tiles.append((80, tech_demos_id, None, 0, _group_label("tech_demos")))

    return tiles, members


GROUP_TILES, GROUP_MEMBERS = _build_groups_and_tiles()
MAIN_MENU_OPTIONS = catalog.build_menu_options(STATIC_MENU_ENTRIES, GROUP_TILES)


def _option_index(options, option_id):
    for index, option in enumerate(options):
        if option[0] == option_id:
            return index
    return 0


# Pool size and cascade math below port menu.py's Menu.step() (deleted --
# no callers remain once this file no longer uses it) to vs2: entries are
# no longer capped around 30 games sharing one preloaded rom (a ROM library
# can hold arbitrarily many files), so instead of one drawable per option,
# a fixed pool of slots is reused, each showing whichever entry currently
# sits at that slot's offset from the selection.
POOL_SIZE = 12
Y_STEP = 20
# ROM libraries are always label-only, and the 4x6 list font is tiny next to
# the ~30-LED icons the 20-step spacing was picked for. Packing those rows
# closer puts more of them on the disc and reads as one list rather than a
# scatter of unrelated words.
ROM_Y_STEP = 10
ICON_X = -32
LABEL_COLUMNS = 21
LABEL_FONT_WIDTH = 4
LABEL_X = -(LABEL_COLUMNS * LABEL_FONT_WIDTH // 2)
LABEL_FONT = "tinyfont_menu.png"
PLACEHOLDER_IMAGE = "menu.png"

# X angle of the top of the disc. The wordmark, the byline and every submenu
# heading sit here, opposite the entry list (centred on x=0, the bottom).
DISC_TOP = 128

# Main-menu branding, in the positions the pre-vs2 flat menu used.
BACKDROP_IMAGE = "favalli.png"
LOGO_IMAGE = "vslogo.png"
LOGO_Y = 0
BYLINE_IMAGE = "loviejo-3.png"
BYLINE_Y = 11

# Submenu headings. 8x8 CP437, so a heading is legible from across the room
# where the 4x6 list font is not; 24 columns is 192 of the disc's 256.
HEADING_FONT = "rainbow8x8.png"
HEADING_FONT_WIDTH = 8
# The selected entry sits at the rim, where HUD text is most legible.
SELECTION_Y = 0
HEADING_MAX_COLUMNS = 24


class ListMenu(vs2.Scene):
    """A virtualised, cascading list: entries scroll toward the rim as they
    approach the selection, each slot showing a real icon when the entry has
    one and a text label otherwise. Used for every launcher screen -- the
    top-level groups, a group's members, a ROM library, and the debug menu
    -- so there is exactly one place that owns this animation and the
    icon-or-label decision, instead of a hand-rolled icon wheel plus a
    separate hand-rolled text renderer.
    """

    asset_pack = "menu"
    back_button = False
    enable_back = True
    empty_message = None
    #: Depth between consecutive entries in the tunnel cascade.
    y_step = Y_STEP
    #: Text shown at the top of the disc, in the large font. None draws
    #: nothing, which is what the root uses -- it shows the wordmark instead.
    heading = None

    def __init__(self, entries, selected_index=0):
        super().__init__()
        # app_loader.load_app() is normally what tags a pushed scene with
        # these two attributes (read from the app's meta.json) -- the
        # browser platform's prepare_frame() (platforms/browser.py) only
        # exports a scene's vs2 render payload when _vs_declared_api ==
        # "vs2", so a launcher scene constructed and pushed directly, never
        # going through load_app(), needs to tag itself or it renders
        # nothing at all in the web emulator (desktop/hardware are
        # unaffected -- only the browser's frame export gates on this).
        self._vs_api_slug = "system.launcher"
        self._vs_declared_api = "vs2"
        self.entries = entries
        self.selected_index = 0
        if entries:
            self.selected_index = min(max(selected_index, 0), len(entries) - 1)

    def build(self):
        # Layers paint in creation order, so the backdrop has to be built
        # before the list and the branding/heading after it.
        self.build_backdrop()
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.slots = []
        for index in range(POOL_SIZE):
            sprite = self.world.sprite(PLACEHOLDER_IMAGE, x=ICON_X, y=index * self.y_step)
            sprite.hide()
            label = self.world.label(LABEL_FONT, columns=LABEL_COLUMNS,
                                     x=LABEL_X, y=index * self.y_step)
            label.hide()
            self.slots.append({
                "sprite": sprite,
                "label": label,
                "entry_index": self.selected_index + index,
                "y": float(index * self.y_step),
            })
        # menu.py drew the selected entry with perspective 2 (HUD) and every
        # other one in the tunnel -- that projection is what made the current
        # option legible, and the vs2 port lost it by putting the whole list
        # on one TUNNEL layer. A drawable's layer is fixed for its whole life,
        # so the selection gets its own HUD pair here rather than a slot
        # migrating between layers; the matching tunnel slot stays hidden.
        self.selection = self.layer("selection", projection=vs2.HUD)
        self.selected_sprite = self.selection.sprite(
            PLACEHOLDER_IMAGE, x=ICON_X, y=SELECTION_Y)
        self.selected_sprite.hide()
        self.selected_label = self.selection.label(
            LABEL_FONT, columns=LABEL_COLUMNS, x=LABEL_X, y=SELECTION_Y)
        self.selected_label.hide()
        self.build_overlay()
        self._render_all()
        self._garbage_collect()

    def build_backdrop(self):
        """Create layers that paint behind the entry list. Override freely."""

    def build_overlay(self):
        """Create layers that paint in front of the entry list.

        The default draws :attr:`heading` at the top of the disc; the root
        menu overrides this to draw the wordmark and byline instead.
        """
        if not self.heading:
            return
        text = self.heading[:HEADING_MAX_COLUMNS]
        self.heading_layer = self.layer("heading", projection=vs2.HUD)
        # The disc shows the naive mapping rotated 180 degrees, so a heading
        # placed at the top reads mirrored on both axes unless it is flipped
        # back here (same correction the native POV overlay applies).
        self.heading_label = self.heading_layer.label(
            HEADING_FONT, columns=len(text),
            x=DISC_TOP - len(text) * HEADING_FONT_WIDTH // 2,
            y=0, text=text, flip_x=True, flip_y=True)

    def _garbage_collect(self):
        import gc

        gc.collect()
        self.call_later(60000, self._garbage_collect)

    def _entry_icon(self, entry):
        strip = entry[1]
        if strip and strip in stripes:
            return strip
        return None

    def _show_entry(self, sprite, label, entry):
        """Draw one entry as its icon, or as a text label when it has none."""
        icon = self._entry_icon(entry)
        if icon:
            sprite.image = icon
            sprite.frame = entry[2] or 0
            sprite.show()
            label.hide()
        else:
            label.text = entry[3]
            label.show()
            sprite.hide()

    def _render_slot(self, slot):
        entry_index = slot["entry_index"]
        sprite, label = slot["sprite"], slot["label"]
        if not self.entries:
            if entry_index == 0 and self.empty_message:
                label.text = self.empty_message
                label.show()
            else:
                label.hide()
            sprite.hide()
            return
        if (entry_index is None or not (0 <= entry_index < len(self.entries))
                or entry_index == self.selected_index):
            # The selection is drawn by the HUD pair, so its tunnel slot stays
            # hidden rather than showing the same entry twice.
            sprite.hide()
            label.hide()
            return
        self._show_entry(sprite, label, self.entries[entry_index])

    def _render_selection(self):
        if not self.entries:
            self.selected_sprite.hide()
            self.selected_label.hide()
            return
        self._show_entry(self.selected_sprite, self.selected_label,
                         self.entries[self.selected_index])

    def _render_all(self):
        for slot in self.slots:
            self._render_slot(slot)
        self._render_selection()

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
            vs2.audio.sound("alecu.vyruss/shoot3")
            # Which slot is under the selection changed, and only recycled
            # slots get re-rendered below -- refresh them all so the newly
            # selected one hides and the previous one reappears.
            self._render_all()

    def _select(self):
        if not self.entries:
            return
        vs2.audio.sound("alecu.vyruss/shoot1")
        self.on_select(self.entries[self.selected_index])

    def _update_positions(self):
        for slot in self.slots:
            entry_index = slot["entry_index"]
            offset = entry_index - self.selected_index if entry_index is not None else -1
            if offset < 0:
                # Scrolled past: recycle this slot to the far end of the
                # cascade, same as a legacy sprite jumping straight to
                # y=255/hidden once its entry is behind the selection.
                slot["entry_index"] = self.selected_index + (POOL_SIZE - 1)
                slot["y"] = 255.0
                self._render_slot(slot)
                offset = POOL_SIZE - 1
            elif offset >= POOL_SIZE:
                # Scrolled backward past the near end: this slot becomes the
                # new selection outright, matching the legacy snap-to-front
                # (no easing) for whatever is newly selected.
                slot["entry_index"] = self.selected_index
                slot["y"] = 0.0
                self._render_slot(slot)
                offset = 0

            if offset == 0:
                y = 0.0
            else:
                dest_y = min(offset * self.y_step + 45, 255)
                curr_y = slot["y"]
                y = curr_y - (curr_y - dest_y) / 4
            slot["y"] = y
            slot["sprite"].y = y
            slot["label"].y = y

    def update(self):
        if joy1.just_pressed(A):
            self._select()
            return
        if self.enable_back and (joy1.just_pressed(Y) or joy1.just_pressed(BACK)):
            self.on_back()
            return self.pop()
        if joy1.just_pressed(UP):
            self._move(1)
        if joy1.just_pressed(DOWN):
            self._move(-1)
        self._update_positions()

    def on_idle(self):
        if self.enable_back:
            self.on_back()
        self.pop()

    def on_select(self, entry):
        """Called with the selected (id, strip, frame, title) entry."""

    def on_back(self):
        """Called just before popping back one level."""


class GroupsMenu(ListMenu):
    """Root: one tile per group plus the standalone system entries."""

    enable_back = False
    idle_timeout = None

    def __init__(self, selected_index=0):
        super().__init__(MAIN_MENU_OPTIONS, selected_index)

    def build_backdrop(self):
        self.backdrop = self.layer("backdrop", projection=vs2.FULLSCREEN)
        self.backdrop.sprite(BACKDROP_IMAGE, x=0, y=255)

    def build_overlay(self):
        """The wordmark and byline, in the places the pre-vs2 menu had them.

        The root gets these instead of a text heading: it is the one screen
        whose name everybody already knows.
        """
        self.branding = self.layer("branding", projection=vs2.HUD)
        for name, y in ((LOGO_IMAGE, LOGO_Y), (BYLINE_IMAGE, BYLINE_Y)):
            image = self.image(name)
            self.branding.sprite(image, x=DISC_TOP - image.width // 2, y=y)

    def on_select(self, entry):
        option_id = entry[0]
        if is_group_tile(option_id):
            native_apps.write_launcher_state({"group_id": option_id, "slug": None, "rom_path": None})
            self.push(GroupMenu(option_id))
            return
        native_apps.write_launcher_state({"group_id": None, "slug": option_id, "rom_path": None})
        load_app(option_id)

    def update(self):
        if self._check_debug_combo():
            return
        super().update()

    def _check_debug_combo(self):
        if (
            joy1.held(UP) and joy1.held(LEFT) and joy1.held(RIGHT) and joy1.held(A)
        ):
            vs2.audio.sound("ventilagon/audio/es/superventilagon")
            self.push(DebugMenu())
            return True
        return False


class GroupMenu(ListMenu):
    """One group's members: real games, or the five native emulator apps."""

    def __init__(self, group_id, selected_slug=None):
        self.group_id = group_id
        entries = GROUP_MEMBERS.get(group_id, [])
        index = _option_index(entries, selected_slug) if selected_slug else 0
        super().__init__(entries, index)
        self.heading = _group_label(group_id[len(GROUP_PREFIX):])

    def on_select(self, entry):
        slug = entry[0]
        native_apps.write_launcher_state({"group_id": self.group_id, "slug": slug, "rom_path": None})
        if native_apps.has_rom_library(slug):
            self.push(RomLibraryMenu(slug))
        elif native_apps.is_native_app(slug):
            native_apps.launch_native_scene(slug)
        else:
            load_app(slug)

    def on_back(self):
        native_apps.write_launcher_state({"group_id": None, "slug": None, "rom_path": None})


class RomLibraryMenu(ListMenu):
    """Files within one emulator's ROM directory -- always label-only,
    ROM files never had icons."""

    empty_message = "NO ROMS"
    y_step = ROM_Y_STEP

    def __init__(self, slug, selected_rom=None):
        self.slug = slug
        roms = native_apps.list_roms(slug)
        entries = [(rom["path"], None, 0, rom["label"]) for rom in roms]
        index = 0
        if selected_rom:
            for rom_index, rom in enumerate(roms):
                if rom["path"] == selected_rom:
                    index = rom_index
                    break
        super().__init__(entries, index)
        spec = native_apps.APP_REGISTRY.get(slug) or {}
        self.heading = spec.get("title") or catalog.prettify_name(slug)

    def on_select(self, entry):
        rom_path = entry[0]
        native_apps.write_launcher_state({
            "group_id": group_tile_id("emulators"), "slug": self.slug, "rom_path": rom_path,
        })
        native_apps.launch_native_scene(self.slug, rom_path)

    def on_back(self):
        native_apps.write_launcher_state({
            "group_id": group_tile_id("emulators"), "slug": self.slug, "rom_path": None,
        })


class DebugMenu(ListMenu):
    """The secret developer menu, reached via the button combo in
    GroupsMenu. Not part of the group hierarchy, so back always returns to
    the root without touching launcher_state.json."""

    heading = "Debug"

    def __init__(self):
        super().__init__(SYS_MENU_OPTIONS)

    def on_select(self, entry):
        load_app(entry[0])

    def on_back(self):
        pass


def main(launcher_state=None):
    launcher_state = launcher_state or native_apps.read_launcher_state()
    group_id = launcher_state.get("group_id")
    slug = launcher_state.get("slug")
    target = group_id or slug
    index = _option_index(MAIN_MENU_OPTIONS, target) if target else 0
    return GroupsMenu(index)


def setup():
    launcher_state = native_apps.consume_native_return()
    root = main(launcher_state)
    director.push(root)

    group_id = launcher_state.get("group_id")
    slug = launcher_state.get("slug")
    if not group_id:
        return
    group_menu = GroupMenu(group_id, selected_slug=slug)
    director.push(group_menu)

    rom_path = launcher_state.get("rom_path")
    if rom_path and slug and native_apps.has_rom_library(slug):
        director.push(RomLibraryMenu(slug, selected_rom=rom_path))
