import vs2
from vs2.controls import A, B, BACK, DOWN, LEFT, RIGHT, UP, X, Y, joy1, joy2

from ventilastation import catalog
from ventilastation import native_apps
from ventilastation.app_loader import load_app
from ventilastation.director import director, stripes

def game_menu_strip(game_slug):
    return game_slug.replace(".", "/") + "/menu.png"

GROUP_PREFIX = "group:"

# The curated root (see HighlightsMenu): a handful of "greatest hits" plus
# a way into everything else, rather than every group and system scene at
# once. Titles here are deliberately shorter/punchier than a game's own
# meta.json title (e.g. "Sencom" vs "Senile Command") -- this is the one
# screen everybody sees first, not the full catalog entry. A hit can be a
# whole group (Circular Arcade's five games), which opens like it does from
# "Más aplicaciones".
MORE_APPS_ID = "more_apps"
HIGHLIGHT_ENTRIES = [
    (5, GROUP_PREFIX + "ld60", "circular_arcade.png", 0, "Circular Arcade"),
    (10, "alecu.ventilagon_game", game_menu_strip("alecu.ventilagon_game"), 0, "Super Ventilagon"),
    (20, "alecu.vyruss_vs2", game_menu_strip("alecu.vyruss_vs2"), 0, "Vyruss VS2"),
    (40, "vsjam-oct25.2bam_sencom", game_menu_strip("vsjam-oct25.2bam_sencom"), 0, "Sencom"),
    (50, "vsjam-may25.vasura_espacial", game_menu_strip("vsjam-may25.vasura_espacial"), 0, "Vasura Espacial"),
    (60, "gallery", "pollitos.png", 0, "Gallery"),
    (9999, MORE_APPS_ID, "more_apps.png", 0, "Más aplicaciones"),
]

# What used to be the whole root before the curated highlights screen took
# over: the two standalone system entries that don't belong to any
# games/<group>/ folder. Every actual group tile is added in
# _build_groups_and_tiles() below (emulators excepted -- see SYS_MENU_OPTIONS).
MORE_APPS_STATIC_ENTRIES = [
    (2, "tutorial_vs2", "menu.png", 10, "Tutorial"),
    (240, "credits", "menu.png", 3, "Credits"),
]

# Order and label for each games/<group>/ folder's top-level tile. A folder
# not listed here (a new group added later) still gets a tile -- just at the
# end of the menu, labelled from its folder name (see _build_groups_and_tiles).
FOLDER_GROUP_ORDER = {
    "alecu": 30,
    "other": 35,
    "vsjam-may25": 40,
    "vsjam-oct25": 50,
    "pycamp-mar25": 60,
    "ld60": 70,
}
GROUP_LABELS = {
    "emulators": "Emulators",
    "alecu": "Alecu",
    "other": "Other",
    "vsjam-may25": "VS Jam May 25",
    "vsjam-oct25": "VS Jam Oct 25",
    "pycamp-mar25": "PyCamp Mar 25",
    "ld60": "Circular Arcade",
    "tech_demos": "Tech Demos",
}
# See system/menu/images/src/make_menu_icons.py -- a group holds many
# unrelated games, so these are theme badges (a jam badge, a console badge,
# ...), not any one game's own art. A group without an entry here still gets
# a tile -- just as a plain label, like before this existed.
GROUP_ICONS = {
    "alecu": "alecu.png",
    "other": "other.png",
    "vsjam-may25": "vsjam_may25.png",
    "vsjam-oct25": "vsjam_oct25.png",
    "pycamp-mar25": "pycamp_mar25.png",
    "ld60": "circular_arcade.png",
    "tech_demos": "tech_demos.png",
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

# The secret debug menu (see HighlightsMenu's button-combo check). Two
# entries borrow real game icons; the rest fall back to a label like a group
# tile -- including "Emulators" itself, a real group tile id so DebugMenu's
# on_select() pushes GroupMenu for it exactly like any other group.
SYS_MENU_OPTIONS = [
    ("debugmode", "menu.png", 9, "Debug Mode"),
    ("tutorial", "menu.png", 10, "Tutorial"),
    ("tutorial_vs2", "menu.png", 10, "Tutorial VS2"),
    ("settings", "menu.png", 8, "Settings"),
    (GROUP_PREFIX + "emulators", "emulators_group.png", 0, "Emulators"),
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
    opening/closing a group never re-walks the filesystem. A group with no
    entry in GROUP_ICONS falls back to a plain label -- there's no dedicated
    art for "a folder of games" in general, only for the specific ones a
    theme badge was made for (see make_menu_icons.py)."""
    tiles = []
    members = {}

    # Emulators intentionally gets no top-level tile any more -- reachable
    # only through the debug menu (SYS_MENU_OPTIONS), not "Más aplicaciones".
    # Its member list stays available for that.
    members[group_tile_id("emulators")] = _emulator_options()

    for group_name, entries in catalog.discover_groups():
        tile_id = group_tile_id(group_name)
        members[tile_id] = catalog.build_menu_options([], entries)
        order = FOLDER_GROUP_ORDER.get(group_name, catalog.DEFAULT_ORDER)
        strip = GROUP_ICONS.get(group_name)
        tiles.append((order, tile_id, strip, 0, _group_label(group_name)))

    # Voom is a native app (see EMULATOR_ICONS) that hands off to the
    # prboom-go partition and reboots the rotor on the way back, which
    # reopened the root with its tile pre-selected: one press from a loop
    # at a festival. For Overkill it lives inside Alecu's group instead of
    # on the curated root (and stays in the debug menu's Emulators group).
    alecu_id = group_tile_id("alecu")
    if alecu_id in members:
        members[alecu_id].append(("emulators.voom", EMULATOR_ICONS["emulators.voom"], 0, "Voom"))

    tech_demos_id = group_tile_id("tech_demos")
    members[tech_demos_id] = catalog.build_menu_options(
        TECH_DEMO_STATIC_ENTRIES, catalog.discover_tech_demo_entries())
    tiles.append((80, tech_demos_id, GROUP_ICONS.get("tech_demos"), 0, _group_label("tech_demos")))

    return tiles, members


GROUP_TILES, GROUP_MEMBERS = _build_groups_and_tiles()
MAIN_MENU_OPTIONS = catalog.build_menu_options([], HIGHLIGHT_ENTRIES)
MORE_APPS_MENU_OPTIONS = catalog.build_menu_options(MORE_APPS_STATIC_ENTRIES, GROUP_TILES)


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
# Ticks per animation-frame advance. The pre-vs2 menu hand-picked a rate per
# icon (4 for pollitos, 6 for tincho); one shared rate is close enough for
# those two.
ICON_ANIM_RATE = 4
# Strips that hold real animation frames for one icon, and the ticks each
# frame stays up -- restoring the pre-vs2 menu's pollitos/tincho animation,
# see ListMenu._animate_icons(). NOT "any multi-frame strip": menu.png alone
# packs 16 unrelated static icons (Credits, Tutorial, Debug Mode, ...), one
# fixed frame per entry -- animating on frame count alone would cycle
# through all of those instead.
ANIMATED_ICON_STRIPS = {
    "pollitos.png": ICON_ANIM_RATE,
    game_menu_strip("vsjam-oct25.tincho_vrunner"): ICON_ANIM_RATE,
    # A marquee's bulbs alternate slowly: 300 ms a frame, so its failing
    # bulbs flicker out once every 3 seconds.
    "circular_arcade.png": 10,
}
# ROM libraries are always label-only, and the 4x6 list font is tiny next to
# the ~30-LED icons the 20-step spacing was picked for. Packing those rows
# closer puts more of them on the disc and reads as one list rather than a
# scatter of unrelated words.
ROM_Y_STEP = 10
# tinyfont_menu packs white ASCII at frames 0..127 and the matching red
# glyphs at 128..254, so +0x80 recolours a line without a second strip.
# menu.py's RomTextRow used exactly this to mark the current ROM.
RED_GLYPH_OFFSET = 0x80
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
# On a FULLSCREEN layer y is depth, and 0 is nearest -- the image spans the
# whole disc there and shrinks to a single LED by 255. The launcher's old
# make_me_a_planet() used the opposite convention: its perspective-0 path
# indexed deepspace[255 - y], so set_y(220) meant deepspace[35], spanning 40
# of the 54 LEDs. vs2_deepspace[21] + 1 is the same 40, and it is the only
# value that matches exactly.
BACKDROP_Y = 21
LOGO_IMAGE = "vslogo.png"
LOGO_Y = 0
BYLINE_IMAGE = "loviejo-3.png"
BYLINE_Y = 11

# Overkill (Enschede, Nov 2026) root-menu branding, replacing the wordmark,
# byline and favalli backdrop while the fan is at the festival. Assets and
# their generators live in docs/overkill/logo-tests of the parent repo.
OVERKILL_BRANDING = True
# Title wrapped as a curved banner around the top arc, a little in from the rim.
# 80x24 (was 100x30) so "Dream" below it can sit further out: near the hub a
# LED covers few columns and the legacy intensity table dims the inner LEDs,
# so the subtitle was unreadable on the spinning fan (2026-11-07 spin test).
OVERKILL_BANNER_IMAGE = "overkill_banner.png"
OVERKILL_BANNER_Y = 2
# "Dream" subtitle, reprojected flat across the whole disc (FULLSCREEN y=0 is
# nearest: the image spans every LED, like the old perspective-0 set_y(255)).
# Variant y5-ccw5 of docs/overkill/logo-tests/make_dream_up.py: 130 px wide,
# top at LED 29 from the hub, arched 14 px, tilted 5 degrees so the gap to
# the banner is even on both sides.
OVERKILL_DREAM_IMAGE = "overkill_dream_flat.png"
OVERKILL_DREAM_Y = 0
# Carousel spinning in place on the left: 36 frames (10 degrees each),
# pre-distorted for the HUD projection, advanced every 4 ticks. Centred 8
# columns below the 9 o'clock horizon (column 56, strip is 49 wide): halfway
# between the logo above and the menu tiles below on the real fan (the
# original spot, 17 below, sat on the tiles; on the horizon it crowded Dream).
OVERKILL_CAROUSEL_IMAGE = "overkill_carousel.png"
OVERKILL_CAROUSEL_X = 32
OVERKILL_CAROUSEL_Y = 8
OVERKILL_CAROUSEL_RATE = 4
# Hand reaching in from the right rim and back: 13 frames pushed 0..12 LEDs
# outward, played with a sine ease (6 - 6*cos over 60 ticks). Axis 8 columns
# below the 3 o'clock horizon (column 200, strip is 41 wide), mirroring the
# carousel, so it reaches in slightly tilted; the frames are radial, so
# moving the sprite needs no regeneration.
OVERKILL_HAND_IMAGE = "overkill_hand.png"
OVERKILL_HAND_X = 180
OVERKILL_HAND_Y = 0
OVERKILL_HAND_EASE = bytes((0,0,0,0,1,1,1,2,2,2,3,4,4,5,5,6,7,7,8,8,9,10,10,10,11,11,11,12,12,12,
                            12,12,12,12,11,11,11,10,10,10,9,8,8,7,7,6,5,5,4,4,3,2,2,2,1,1,1,0,0,0))
OVERKILL_IMAGES = (OVERKILL_BANNER_IMAGE, OVERKILL_DREAM_IMAGE,
                   OVERKILL_CAROUSEL_IMAGE, OVERKILL_HAND_IMAGE)


def _overkill_branding_available():
    """The festival art is used only when the switch is on AND the menu ROM
    carries all four strips; a build without them (or the test fixtures)
    keeps the stock wordmark, byline and favalli backdrop."""
    if not OVERKILL_BRANDING:
        return False
    return all(name in stripes for name in OVERKILL_IMAGES)

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

    # The menus keep the drifting stars behind the icons.
    starfield = True

    asset_pack = "menu"
    back_button = False
    enable_back = True
    empty_message = None
    #: Stops the exit command unwinding past this scene (see
    #: Director.return_to_menu): a game exits back into the menu it was
    #: launched from, and only reaches the root on a further press.
    is_menu_scene = True
    #: Depth between consecutive entries in the tunnel cascade.
    y_step = Y_STEP
    #: Frame offset for the selected entry's label, and for
    #: :attr:`empty_message`. See :data:`RED_GLYPH_OFFSET`.
    selected_frame_offset = 0
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
        # Icons with more than one frame (pollitos.png, tincho_vrunner's
        # menu.png, ...) cycle on their own -- see _animate_icons(). One
        # shared clock for every animated sprite on screen, rather than a
        # per-sprite counter, so a slot recycled mid-cycle by the cascade
        # (see _update_positions) never has to guess where to resume from.
        self._icon_anim_tick = 0

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

    def _show_entry(self, sprite, label, entry, frame_offset=0):
        """Draw one entry as its icon, or as a text label when it has none."""
        icon = self._entry_icon(entry)
        if icon:
            sprite.image = icon
            sprite.frame = entry[2] or 0
            sprite.show()
            label.hide()
        else:
            label.write(0, 0, entry[3], frame_offset=frame_offset)
            label.show()
            sprite.hide()

    def _render_slot(self, slot):
        entry_index = slot["entry_index"]
        sprite, label = slot["sprite"], slot["label"]
        if not self.entries:
            # The empty notice is drawn by _render_selection() instead: it is
            # the screen's only line, so it belongs where a selected entry
            # would be rather than at the back of the tunnel.
            sprite.hide()
            label.hide()
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
            if self.empty_message:
                self.selected_label.write(0, 0, self.empty_message,
                                          frame_offset=self.selected_frame_offset)
                self.selected_label.show()
            else:
                self.selected_label.hide()
            return
        self._show_entry(self.selected_sprite, self.selected_label,
                         self.entries[self.selected_index],
                         self.selected_frame_offset)

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

    def _animate_sprite(self, sprite):
        if not sprite.visible:
            return
        rate = ANIMATED_ICON_STRIPS.get(sprite.image.name)
        if rate is None:
            return
        frames = sprite.image.frames
        if frames > 1:
            sprite.frame = (self._icon_anim_tick // rate) % frames

    def _animate_icons(self):
        """Cycle pollitos/tincho -- regression fix: the vs2 port always
        showed a strip's static idle frame (entry[2]) and dropped the
        pre-vs2 menu's hand-picked animation for these two entirely.
        Gated on ANIMATED_ICON_STRIPS, not just "image has >1 frames": most
        multi-frame strips (menu.png above all) pack several unrelated
        static icons, one fixed frame per entry, and would cycle through
        each other's icons if animated on frame count alone."""
        self._icon_anim_tick += 1
        for slot in self.slots:
            self._animate_sprite(slot["sprite"])
        self._animate_sprite(self.selected_sprite)

    def update(self):
        if joy1.just_pressed(A) or joy2.just_pressed(A):
            self._select()
            return
        if self.enable_back and (joy1.just_pressed(Y) or joy1.just_pressed(BACK)
                                 or joy2.just_pressed(Y) or joy2.just_pressed(BACK)):
            self.on_back()
            return self.pop()
        if joy1.just_pressed(UP) or joy2.just_pressed(UP):
            self._move(1)
        if joy1.just_pressed(DOWN) or joy2.just_pressed(DOWN):
            self._move(-1)
        self._update_positions()
        self._animate_icons()

    def on_idle(self):
        if self.enable_back:
            self.on_back()
        self.pop()

    def on_select(self, entry):
        """Called with the selected (id, strip, frame, title) entry."""

    def on_back(self):
        """Called just before popping back one level."""


def _dispatch_app(scene, slug, group_id):
    """Launch slug from a menu screen: push a ROM library, hand off to a
    native app, or load a MicroPython game. Shared by HighlightsMenu (a
    curated entry like Voom can itself be a native app, not just a group
    member) and GroupMenu, so both get the same three-way dispatch."""
    native_apps.write_launcher_state({"group_id": group_id, "slug": slug, "rom_path": None})
    if native_apps.has_rom_library(slug):
        scene.push(RomLibraryMenu(slug))
    elif native_apps.is_native_app(slug):
        native_apps.launch_native_scene(slug)
    else:
        load_app(slug)


class HighlightsMenu(ListMenu):
    """Root: a curated set of Ventilastation's greatest hits (see
    HIGHLIGHT_ENTRIES) -- games, or whole groups -- plus a "Más
    aplicaciones" tile into everything else (GroupsMenu)."""

    enable_back = False
    idle_timeout = None

    def __init__(self, selected_index=0):
        super().__init__(MAIN_MENU_OPTIONS, selected_index)

    def build_backdrop(self):
        self.backdrop = self.layer("backdrop", projection=vs2.FULLSCREEN)
        if _overkill_branding_available():
            self.backdrop.sprite(OVERKILL_DREAM_IMAGE, x=0, y=OVERKILL_DREAM_Y)
        else:
            self.backdrop.sprite(BACKDROP_IMAGE, x=0, y=BACKDROP_Y)

    def build_overlay(self):
        """The wordmark and byline, in the places the pre-vs2 menu had them.

        The root gets these instead of a text heading: it is the one screen
        whose name everybody already knows. With OVERKILL_BRANDING the
        festival art takes their place: curved title banner, spinning
        carousel on the left and a hand reaching in from the right.
        """
        self.branding = self.layer("branding", projection=vs2.HUD)
        self._overkill_tick = 0
        self.overkill_carousel = None
        self.overkill_hand = None
        if not _overkill_branding_available():
            for name, y in ((LOGO_IMAGE, LOGO_Y), (BYLINE_IMAGE, BYLINE_Y)):
                image = self.image(name)
                self.branding.sprite(image, x=DISC_TOP - image.width // 2, y=y)
            return
        banner = self.image(OVERKILL_BANNER_IMAGE)
        self.branding.sprite(banner, x=DISC_TOP - banner.width // 2, y=OVERKILL_BANNER_Y)
        self.overkill_carousel = self.branding.sprite(
            OVERKILL_CAROUSEL_IMAGE, x=OVERKILL_CAROUSEL_X, y=OVERKILL_CAROUSEL_Y)
        self.overkill_hand = self.branding.sprite(
            OVERKILL_HAND_IMAGE, x=OVERKILL_HAND_X, y=OVERKILL_HAND_Y)

    def _animate_overkill(self):
        if self.overkill_carousel is None:
            return
        tick = self._overkill_tick
        carousel_frames = self.overkill_carousel.image.frames
        self.overkill_carousel.frame = (tick // OVERKILL_CAROUSEL_RATE) % carousel_frames
        self.overkill_hand.frame = OVERKILL_HAND_EASE[tick % len(OVERKILL_HAND_EASE)]
        self._overkill_tick = tick + 1

    def on_select(self, entry):
        option_id = entry[0]
        if option_id == MORE_APPS_ID:
            self.push(GroupsMenu())
            return
        if is_group_tile(option_id):
            native_apps.write_launcher_state({"group_id": option_id, "slug": None, "rom_path": None})
            self.push(GroupMenu(option_id))
            return
        _dispatch_app(self, option_id, None)

    def update(self):
        if self._check_debug_combo():
            return
        self._animate_overkill()
        super().update()

    def _check_debug_combo(self):
        # Hidden debug menu: hold B + X + Left (accel + decel + left on the
        # cabinet stick). The old UP+LEFT+RIGHT+A chord needed a 4-way hold
        # that most joysticks can't physically make.
        if ((joy1.held(B) and joy1.held(X) and joy1.held(LEFT))
                or (joy2.held(B) and joy2.held(X) and joy2.held(LEFT))):
            vs2.audio.sound("ventilagon/audio/es/superventilagon")
            self.push(DebugMenu())
            return True
        return False


class GroupsMenu(ListMenu):
    """Más aplicaciones: one tile per group (minus emulators -- see
    SYS_MENU_OPTIONS) plus the standalone system entries, reached from the
    curated root's own tile of the same name."""

    heading = "Más aplicaciones"

    def __init__(self, selected_index=0):
        super().__init__(MORE_APPS_MENU_OPTIONS, selected_index)

    def on_select(self, entry):
        option_id = entry[0]
        if is_group_tile(option_id):
            native_apps.write_launcher_state({"group_id": option_id, "slug": None, "rom_path": None})
            self.push(GroupMenu(option_id))
            return
        native_apps.write_launcher_state({"group_id": None, "slug": option_id, "rom_path": None})
        load_app(option_id)


class GroupMenu(ListMenu):
    """One group's members: real games, or the five native emulator apps."""

    def __init__(self, group_id, selected_slug=None):
        self.group_id = group_id
        entries = GROUP_MEMBERS.get(group_id, [])
        index = _option_index(entries, selected_slug) if selected_slug else 0
        super().__init__(entries, index)
        self.heading = _group_label(group_id[len(GROUP_PREFIX):])

    def on_select(self, entry):
        _dispatch_app(self, entry[0], self.group_id)

    def on_back(self):
        native_apps.write_launcher_state({"group_id": None, "slug": None, "rom_path": None})


class RomLibraryMenu(ListMenu):
    """Files within one emulator's ROM directory -- always label-only,
    ROM files never had icons."""

    empty_message = "NO ROMS"
    y_step = ROM_Y_STEP
    selected_frame_offset = RED_GLYPH_OFFSET

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
    HighlightsMenu. Not part of the group hierarchy, so back always returns
    to the root without touching launcher_state.json. Also where Emulators
    lives now (a real group tile id, so it pushes GroupMenu like any other
    group) -- it isn't shown on the curated root or "Más aplicaciones"."""

    heading = "Debug"

    def __init__(self):
        super().__init__(SYS_MENU_OPTIONS)

    def on_select(self, entry):
        option_id = entry[0]
        if is_group_tile(option_id):
            self.push(GroupMenu(option_id))
            return
        load_app(option_id)

    def on_back(self):
        pass


def _on_root(option_id):
    return any(option[0] == option_id for option in MAIN_MENU_OPTIONS)


def main(launcher_state=None):
    launcher_state = launcher_state or native_apps.read_launcher_state()
    group_id = launcher_state.get("group_id")
    slug = launcher_state.get("slug")
    # Resuming into a group means the curated root should show the tile it
    # was opened from pre-selected -- its own tile when the group is one of
    # the root's hits, "Más aplicaciones" otherwise -- and setup() pushes the
    # real group screens on top of it. Resuming into one of the root's own
    # curated slugs (no group) highlights that tile directly instead.
    if group_id and _on_root(group_id):
        target = group_id
    elif group_id:
        target = MORE_APPS_ID
    elif slug:
        target = slug
    else:
        target = None
    index = _option_index(MAIN_MENU_OPTIONS, target) if target else 0
    return HighlightsMenu(index)


def setup():
    launcher_state = native_apps.consume_native_return()
    root = main(launcher_state)
    director.push(root)

    group_id = launcher_state.get("group_id")
    slug = launcher_state.get("slug")
    if not group_id:
        return

    if group_id == GROUP_PREFIX + "emulators":
        # Emulators moved off "Más aplicaciones" into the debug menu (see
        # SYS_MENU_OPTIONS) -- resuming into it goes through there instead.
        director.push(DebugMenu())
    elif not _on_root(group_id):
        director.push(GroupsMenu(_option_index(MORE_APPS_MENU_OPTIONS, group_id)))
    director.push(GroupMenu(group_id, selected_slug=slug))

    rom_path = launcher_state.get("rom_path")
    if rom_path and slug and native_apps.has_rom_library(slug):
        director.push(RomLibraryMenu(slug, selected_rom=rom_path))
