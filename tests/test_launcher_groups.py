"""Checks for the vs2-based launcher (system/launcher/code): group/tile
construction, ListMenu's on_select/on_back navigation and state-saving, and
main()/setup()'s restore-after-reboot logic.

on_select()/on_back() are tested directly against a constructed-but-not-
built scene instance (no on_enter()/build() involved) -- they only touch
plain attributes (self.entries, self.group_id, self.slug, self.selected_index)
and vs2.Scene.push()/pop(), which just record a pending transition rather
than touching any drawable or rom. That keeps these tests fast and immune to
asset-pack faking. One end-to-end test exercises setup()'s real
director.push() chain, following tests/test_input_demo.py's pattern for a
vs2.Scene under the headless platform.
"""

import os
import pathlib
import sys
import time
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "micropython"))
sys.path.insert(0, str(ROOT))

sys.modules.setdefault("uos", os)
sys.modules.setdefault("urandom", __import__("random"))
if "utime" not in sys.modules:
    utime = types.ModuleType("utime")
    utime.ticks_ms = lambda: int(time.monotonic() * 1000)
    utime.ticks_add = lambda value, delta: value + delta
    utime.ticks_diff = lambda value, other: value - other
    utime.sleep_ms = lambda value: time.sleep(value / 1000)
    sys.modules["utime"] = utime

from ventilastation.director import configure_runtime, director, reset_runtime, stripes
from ventilastation import api_guard
from ventilastation import native_apps

# vs2 (imported by system.launcher.code) resolves the active platform lazily,
# not at import time, but configuring up front matches every other vs2 test
# in this tree and keeps this file safe to run standalone or as part of the
# suite in any order.
configure_runtime("headless")
from system.launcher.code import (
    GROUP_ICONS,
    GROUP_MEMBERS,
    GROUP_PREFIX,
    GROUP_TILES,
    ICON_ANIM_RATE,
    MAIN_MENU_OPTIONS,
    MORE_APPS_ID,
    MORE_APPS_MENU_OPTIONS,
    DebugMenu,
    GroupMenu,
    GroupsMenu,
    HighlightsMenu,
    RomLibraryMenu,
    SYS_MENU_OPTIONS,
    group_tile_id,
    is_group_tile,
    main,
    setup,
)


class MainMenuOptionsTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        configure_runtime("headless")

    def tearDown(self):
        reset_runtime()

    def test_every_top_level_tile_has_a_readable_title(self):
        for slug, _strip, _frame, title in MAIN_MENU_OPTIONS:
            self.assertTrue(title, "missing title for %r" % (slug,))

    def test_curated_root_only_holds_hand_picked_groups(self):
        # The curated root (HIGHLIGHT_ENTRIES) is a handful of hand-picked
        # slugs plus the MORE_APPS_ID tile into GroupsMenu. Every
        # games/<group>/ tile lives one level down, in MORE_APPS_MENU_OPTIONS
        # (see test_more_apps_* below); Circular Arcade is the one group also
        # curated on the root.
        top_level_slugs = [slug for slug, _s, _f, _t in MAIN_MENU_OPTIONS]
        self.assertEqual([slug for slug in top_level_slugs if is_group_tile(slug)],
                         [group_tile_id("ld60")])
        self.assertIn(MORE_APPS_ID, top_level_slugs)

    def test_circular_arcade_is_first_on_the_root_and_in_more_apps(self):
        group_id = group_tile_id("ld60")
        self.assertEqual(MAIN_MENU_OPTIONS[0][0], group_id)
        for options in (MAIN_MENU_OPTIONS, MORE_APPS_MENU_OPTIONS):
            entry = [option for option in options if option[0] == group_id]
            self.assertEqual(entry, [(group_id, "circular_arcade.png", 0, "Circular Arcade")])
        members = [slug for slug, _s, _f, _t in GROUP_MEMBERS[group_id]]
        self.assertEqual(members, [
            "ld60.spiral_tunnel", "ld60.catch_the_robots", "ld60.rim_runner",
            "ld60.dodge_em", "ld60.defender",
        ])

    def test_more_apps_group_tiles_have_members(self):
        group_ids = [slug for slug, _s, _f, _t in MORE_APPS_MENU_OPTIONS if is_group_tile(slug)]
        # Emulators keeps its member list (used by the debug menu) but is
        # deliberately excluded from "Más aplicaciones" -- see
        # test_emulators_group_has_no_more_apps_tile below.
        self.assertEqual(set(group_ids), set(GROUP_MEMBERS) - {group_tile_id("emulators")})
        for group_id, options in GROUP_MEMBERS.items():
            self.assertTrue(options, "%r has no members" % (group_id,))

    def test_group_tiles_use_their_own_theme_badge_not_a_borrowed_icon(self):
        # See make_menu_icons.py: every group with an entry in GROUP_ICONS
        # gets its own badge, sized like every other menu icon; one without
        # an entry there (a brand-new games/<group> folder) still falls back
        # to a plain label rather than borrowing another tile's art.
        for _order, slug, strip, _frame, _title in GROUP_TILES:
            group_name = slug[len(GROUP_PREFIX):]
            self.assertEqual(strip, GROUP_ICONS.get(group_name),
                             "%r should use its own GROUP_ICONS entry" % (slug,))

    def test_emulators_group_keeps_its_real_icons(self):
        emulators = dict((slug, (strip, title)) for slug, strip, _f, title in GROUP_MEMBERS[group_tile_id("emulators")])
        self.assertEqual(set(emulators), set(native_apps.APP_REGISTRY))
        self.assertEqual(emulators["emulators.nes"], ("nes.png", "NES"))

    def test_emulators_group_has_no_more_apps_tile(self):
        # Moved to the debug menu (SYS_MENU_OPTIONS) -- not shown on the
        # curated root or "Más aplicaciones", only reachable from there.
        more_apps_slugs = [slug for slug, _s, _f, _t in MORE_APPS_MENU_OPTIONS]
        self.assertNotIn(group_tile_id("emulators"), more_apps_slugs)
        debug_slugs = [slug for slug, _s, _f, _t in SYS_MENU_OPTIONS]
        self.assertIn(group_tile_id("emulators"), debug_slugs)

    def test_a_native_slug_can_be_a_curated_highlight(self):
        # Voom sits directly on the curated root now, not nested under a
        # group tile -- see HighlightsMenu.on_select()'s use of _dispatch_app.
        top_level_slugs = [slug for slug, _s, _f, _t in MAIN_MENU_OPTIONS]
        self.assertIn("emulators.voom", top_level_slugs)

    def test_tech_demos_group_includes_the_hardware_test(self):
        tech_demos = [slug for slug, _s, _f, _t in GROUP_MEMBERS[group_tile_id("tech_demos")]]
        self.assertIn("demos.input_demo", tech_demos)
        self.assertIn("vs2_hardware", tech_demos)

    def test_alecu_group_includes_the_curated_ventilagon(self):
        # Un-hidden (meta.json's "hidden": true removed) so it shows up in
        # its normal games/<group> listing, in addition to being curated
        # separately as "Super Ventilagon" on the root.
        alecu = [slug for slug, _s, _f, _t in GROUP_MEMBERS[group_tile_id("alecu")]]
        self.assertIn("alecu.vyruss", alecu)
        self.assertIn("alecu.ventilagon_game", alecu)


class NavigationTests(unittest.TestCase):
    """on_select()/on_back() against constructed-but-unbuilt scenes."""

    def setUp(self):
        reset_runtime()
        configure_runtime("headless")
        api_guard.reset()

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def test_selecting_a_group_tile_pushes_that_group_and_saves_state(self):
        root = GroupsMenu()
        group_id = group_tile_id("alecu")
        root.on_select((group_id, None, 0, "Alecu"))

        kind, target = root._pending_transition
        self.assertEqual(kind, "push")
        self.assertIsInstance(target, GroupMenu)
        self.assertEqual(target.group_id, group_id)
        self.assertEqual(native_apps.read_launcher_state(), {
            "group_id": group_id, "slug": None, "rom_path": None,
        })

    def test_selecting_a_group_tile_on_the_root_pushes_that_group(self):
        root = HighlightsMenu()
        group_id = group_tile_id("ld60")
        root.on_select((group_id, "circular_arcade.png", 0, "Circular Arcade"))

        kind, target = root._pending_transition
        self.assertEqual(kind, "push")
        self.assertIsInstance(target, GroupMenu)
        self.assertEqual(target.group_id, group_id)
        self.assertEqual(target.heading, "Circular Arcade")
        self.assertEqual(native_apps.read_launcher_state(), {
            "group_id": group_id, "slug": None, "rom_path": None,
        })

    def test_selecting_a_game_writes_state_then_loads_it(self):
        import system.launcher.code as launcher_module

        loaded = []
        original_load_app = launcher_module.load_app
        launcher_module.load_app = lambda slug: loaded.append(slug)
        try:
            group_id = group_tile_id("alecu")
            group_menu = GroupMenu(group_id)
            group_menu.on_select(("alecu.vyruss", "alecu/vyruss/menu.png", 0, "Vyruss"))
        finally:
            launcher_module.load_app = original_load_app

        self.assertEqual(loaded, ["alecu.vyruss"])
        self.assertIsNone(group_menu._pending_transition)
        self.assertEqual(native_apps.read_launcher_state(), {
            "group_id": group_id, "slug": "alecu.vyruss", "rom_path": None,
        })

    def test_selecting_an_emulator_with_a_rom_library_pushes_rom_library(self):
        group_id = group_tile_id("emulators")
        group_menu = GroupMenu(group_id)
        group_menu.on_select(("emulators.nes", "nes.png", 0, "NES"))

        kind, target = group_menu._pending_transition
        self.assertEqual(kind, "push")
        self.assertIsInstance(target, RomLibraryMenu)
        self.assertEqual(target.slug, "emulators.nes")
        self.assertEqual(native_apps.read_launcher_state(), {
            "group_id": group_id, "slug": "emulators.nes", "rom_path": None,
        })

    def test_group_back_clears_state_to_the_top_level(self):
        native_apps.write_launcher_state({
            "group_id": group_tile_id("alecu"), "slug": "alecu.vyruss", "rom_path": None,
        })
        GroupMenu(group_tile_id("alecu")).on_back()

        self.assertEqual(native_apps.read_launcher_state(), {
            "group_id": None, "slug": None, "rom_path": None,
        })

    def test_rom_library_back_keeps_the_emulator_selected(self):
        slug = "emulators.gb"
        RomLibraryMenu(slug).on_back()

        self.assertEqual(native_apps.read_launcher_state(), {
            "group_id": group_tile_id("emulators"), "slug": slug, "rom_path": None,
        })

    def test_debug_menu_entries_match_sys_menu_options(self):
        debug_menu = DebugMenu()
        self.assertEqual([entry[0] for entry in debug_menu.entries],
                          [entry[0] for entry in SYS_MENU_OPTIONS])
        self.assertTrue(debug_menu.enable_back)  # default True: back pops to root


class MainRestoreTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        configure_runtime("headless")

    def tearDown(self):
        reset_runtime()

    def test_fresh_boot_lands_on_the_first_top_level_tile(self):
        scene = main({"group_id": None, "slug": None, "rom_path": None})

        self.assertIsInstance(scene, HighlightsMenu)
        self.assertEqual(scene.entries, MAIN_MENU_OPTIONS)
        self.assertEqual(scene.selected_index, 0)

    def test_restoring_a_group_id_selects_more_apps_on_the_root(self):
        # The root itself has no tile for any individual group any more --
        # setup() pushes GroupsMenu/GroupMenu on top of this selection.
        group_id = group_tile_id("emulators")
        scene = main({"group_id": group_id, "slug": "emulators.nes", "rom_path": None})

        self.assertEqual(scene.entries[scene.selected_index][0], MORE_APPS_ID)

    def test_restoring_a_group_curated_on_the_root_selects_its_own_tile(self):
        group_id = group_tile_id("ld60")
        scene = main({"group_id": group_id, "slug": "ld60.defender", "rom_path": None})

        self.assertEqual(scene.entries[scene.selected_index][0], group_id)

    def test_restoring_a_standalone_slug_selects_it_directly(self):
        scene = main({"group_id": None, "slug": "gallery", "rom_path": None})

        self.assertEqual(scene.entries[scene.selected_index][0], "gallery")


class SetupIntegrationTests(unittest.TestCase):
    """One end-to-end check that setup() really reconstructs a multi-level
    stack via real director.push() calls, following test_input_demo.py's
    pattern for exercising a vs2.Scene under the headless platform."""

    def setUp(self):
        reset_runtime()
        api_guard.reset()
        self.runtime_director = configure_runtime("headless")
        stripes.clear()

        # Mirrors system/menu/images/__images__.yaml: every strip the launcher
        # resolves during build(), with the real ROM's metadata. favalli is a
        # `fullscreen:` entry, so it arrives reprojected to 256x54 rather than
        # at its 320x320 source size. Tests add icons with _add_strip().
        self.fake_strips = [
            ("menu.png", 64, 30, 16, 0),
            ("vslogo.png", 84, 11, 1, 0),
            ("loviejo-3.png", 84, 11, 1, 0),
            ("favalli.png", 256, 54, 1, 0),
            ("tinyfont_menu.png", 4, 6, 255, 1),
            ("rainbow8x8.png", 8, 8, 256, 2),
        ]

        def fake_load_rom(_filename):
            for index, (name, width, height, frames, palette) in enumerate(self.fake_strips):
                stripes[name] = index
                self.runtime_director.platform.sprites.stripes[index] = {
                    "width": width, "height": height,
                    "frames": frames, "palette": palette,
                }

        self.runtime_director.load_rom = fake_load_rom

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

    def _build(self, scene):
        director.push(scene)
        return scene

    def _add_strip(self, name, width, height, frames):
        """Put one more strip in the fake ROM. It has to go through
        fake_load_rom: a strip registered by hand before the scene loads its
        ROM gets its index's metadata overwritten by whichever fake strip
        shares that index."""
        self.fake_strips.append((name, width, height, frames, 0))

    def _roms(self, roms):
        """Stand in for a real ROM directory while a menu is constructed."""
        import contextlib

        @contextlib.contextmanager
        def patched():
            original = native_apps.list_roms
            native_apps.list_roms = lambda slug: roms
            try:
                yield
            finally:
                native_apps.list_roms = original

        return patched()

    def _input_tick(self, player1=0, player2=0, extra=0):
        self.runtime_director.buttons = player1
        self.runtime_director.buttons2 = player2
        self.runtime_director.extra_buttons = extra
        director.step_once()

    def test_either_player_can_navigate_without_repeating_held_keys(self):
        from vs2.controls import UP, DOWN
        menu = self._build(HighlightsMenu(selected_index=2))
        for player in ("player1", "player2"):
            self._input_tick(**{player: UP})
            self.assertEqual(menu.selected_index, 3)
            self._input_tick(**{player: UP})
            self.assertEqual(menu.selected_index, 3)
            self._input_tick()
            self._input_tick(**{player: DOWN})
            self.assertEqual(menu.selected_index, 2)
            self._input_tick()

    def test_shared_direction_moves_once_but_each_player_has_their_own_edge(self):
        from vs2.controls import UP
        menu = self._build(HighlightsMenu(selected_index=2))
        self._input_tick(player1=UP, player2=UP)
        self.assertEqual(menu.selected_index, 3)
        self._input_tick()
        self._input_tick(player1=UP)
        self.assertEqual(menu.selected_index, 4)
        self._input_tick(player1=UP, player2=UP)
        self.assertEqual(menu.selected_index, 5)
        self._input_tick(player1=UP, player2=UP)
        self.assertEqual(menu.selected_index, 5)

    def test_player2_can_open_more_apps_and_a_group(self):
        from vs2.controls import A
        index = [entry[0] for entry in MAIN_MENU_OPTIONS].index(MORE_APPS_ID)
        self._build(HighlightsMenu(index))
        self._input_tick(player2=A)
        groups = director.scene_stack[-1]
        self.assertIsInstance(groups, GroupsMenu)
        self._input_tick(player2=A)
        self.assertIs(director.scene_stack[-1], groups)
        self._input_tick()
        group_id = group_tile_id("alecu")
        groups.selected_index = [entry[0] for entry in groups.entries].index(group_id)
        self._input_tick(player2=A)
        self.assertIsInstance(director.scene_stack[-1], GroupMenu)
        self.assertEqual(director.scene_stack[-1].group_id, group_id)

    def test_player2_can_launch_a_game(self):
        from unittest.mock import patch
        from vs2.controls import A
        menu = self._build(GroupMenu(group_tile_id("alecu"), "alecu.vyruss"))
        with patch("system.launcher.code.load_app") as load:
            self._input_tick(player2=A)
            load.assert_called_once_with("alecu.vyruss")
        self.assertEqual(native_apps.read_launcher_state()["slug"], "alecu.vyruss")

    def test_player2_back_and_y_pop_submenus_and_clear_saved_group(self):
        self._build(HighlightsMenu())
        groups = self._build(GroupsMenu())
        for extra in (0x02, 0x20):  # Player 2 Y and Back.
            self._build(GroupMenu(group_tile_id("alecu")))
            native_apps.write_launcher_state({"group_id": group_tile_id("alecu"),
                                              "slug": "alecu.vyruss", "rom_path": None})
            self._input_tick(extra=extra)
            self.assertIs(director.scene_stack[-1], groups)
            self.assertIsNone(native_apps.read_launcher_state()["group_id"])
            self._input_tick()

    def test_player2_back_and_y_keep_the_root_open(self):
        root = self._build(HighlightsMenu())
        for extra in (0x02, 0x20):
            self._input_tick(extra=extra)
            self.assertIs(director.scene_stack[-1], root)
            self._input_tick()

    def test_either_player_can_open_debug_without_combining_players_chords(self):
        from vs2.controls import UP, LEFT, RIGHT, A
        root = self._build(HighlightsMenu())
        self.runtime_director.buttons = UP
        self.runtime_director.buttons2 = LEFT | RIGHT | A
        self.assertFalse(root._check_debug_combo())
        self._input_tick(player2=UP | LEFT | RIGHT | A)
        self.assertIsInstance(director.scene_stack[-1], DebugMenu)

    def test_root_menu_draws_its_backdrop_wordmark_and_byline(self):
        # Lost in the vs2 port and restored: the disc should not come up as a
        # bare list of tiles. Now HighlightsMenu's job -- GroupsMenu ("Más
        # aplicaciones") is one level down and has a plain text heading
        # instead (see test_more_apps_menu_is_headed below).
        root = self._build(HighlightsMenu())

        backdrop = root.backdrop.sprites
        self.assertEqual([sprite.image.name for sprite in backdrop], ["favalli.png"])
        branding = [sprite.image.name for sprite in root.branding.sprites]
        self.assertEqual(branding, ["vslogo.png", "loviejo-3.png"])

    def test_root_backdrop_matches_the_legacy_planet_size(self):
        # FULLSCREEN y is depth, 0 nearest, shrinking to a single LED by 255.
        # The old make_me_a_planet() indexed deepspace[255 - y], so its
        # set_y(220) spanned 40 of the 54 LEDs; vs2_deepspace[21] + 1 is the
        # same 40. Carrying the raw 220 across would render a 1-LED speck.
        root = self._build(HighlightsMenu())

        self.assertEqual(root.backdrop.sprites[0].y, 21)

    def test_root_backdrop_paints_behind_the_list_and_branding_in_front(self):
        root = self._build(HighlightsMenu())
        order = [layer.name for layer in root.layers]

        self.assertLess(order.index("backdrop"), order.index("world"))
        self.assertLess(order.index("world"), order.index("branding"))

    def test_root_menu_has_no_text_heading(self):
        self.assertIsNone(self._build(HighlightsMenu()).heading)

    def test_more_apps_menu_is_headed(self):
        menu = self._build(GroupsMenu())

        self.assertEqual(menu.heading, "Más aplicaciones")
        self.assertEqual(menu.heading_label.text, "Más aplicaciones")

    def test_pollitos_icon_animates(self):
        # Regression test for a bug in the animation fix itself: it must be
        # driven off ANIMATED_ICON_STRIPS, not "the image has >1 frames" --
        # see the next test for the strip that distinction exists for.
        self._add_strip("pollitos.png", 51, 19, 5)
        gallery_index = [slug for slug, _s, _f, _t in MAIN_MENU_OPTIONS].index("gallery")
        root = self._build(HighlightsMenu(gallery_index))

        frames_seen = set()
        for _ in range(ICON_ANIM_RATE * 6):
            root._animate_icons()
            frames_seen.add(root.selected_sprite.frame)

        self.assertGreater(len(frames_seen), 1)

    def test_circular_arcade_marquee_plays_all_ten_frames_slowly(self):
        # Its bulbs alternate at 10 ticks a frame, much slower than
        # pollitos, and the last frame (the failing bulb) must come round too.
        self._add_strip("circular_arcade.png", 64, 30, 10)
        root = self._build(HighlightsMenu())
        self.assertEqual(root.selected_sprite.image.name, "circular_arcade.png")
        self.assertEqual(root.selected_sprite.image.frames, 10)

        frames = []
        for _ in range(100):
            root._animate_icons()
            frames.append(root.selected_sprite.frame)

        self.assertEqual(frames[:9], [0] * 9)
        self.assertEqual(frames[9], 1)
        self.assertEqual(sorted(set(frames)), list(range(10)))

    def test_a_shared_menu_png_frame_does_not_animate(self):
        # tutorial_vs2 pins frame 10 of the generic 16-frame menu.png --
        # that strip packs several unrelated static icons (Credits, Tutorial,
        # Debug Mode, ...), one fixed frame each, and must never be swept up
        # by the animation loop just because it happens to have many frames.
        tutorial_index = [slug for slug, _s, _f, _t in MORE_APPS_MENU_OPTIONS].index("tutorial_vs2")
        menu = self._build(GroupsMenu(tutorial_index))

        for _ in range(ICON_ANIM_RATE * 6):
            menu._animate_icons()

        self.assertEqual(menu.selected_sprite.frame, 10)

    def test_group_menu_is_headed_by_its_group_label(self):
        menu = self._build(GroupMenu(group_tile_id("emulators")))

        self.assertEqual(menu.heading, "Emulators")
        self.assertEqual(menu.heading_label.text, "Emulators")
        self.assertEqual(menu.heading_label.image.name, "rainbow8x8.png")

    def test_heading_is_centred_on_the_top_of_the_disc(self):
        menu = self._build(GroupMenu(group_tile_id("emulators")))
        label = menu.heading_label

        # 9 characters of an 8-wide font, centred on x=128.
        self.assertEqual(label.x, 128 - 9 * 8 // 2)
        self.assertEqual(label.y, 0)
        # The disc shows the naive mapping rotated 180 degrees.
        self.assertTrue(label.flip_x)
        self.assertTrue(label.flip_y)

    def test_rom_library_is_headed_by_its_emulator(self):
        menu = self._build(RomLibraryMenu("emulators.nes"))

        self.assertEqual(menu.heading, native_apps.APP_REGISTRY["emulators.nes"]["title"])
        self.assertEqual(menu.heading_label.text, menu.heading)

    def test_debug_menu_is_headed(self):
        self.assertEqual(self._build(DebugMenu()).heading_label.text, "Debug")

    def _shown_slot_entries(self, menu):
        return [slot["entry_index"] for slot in menu.slots
                if slot["sprite"].visible or slot["label"].visible]

    def test_selected_entry_is_drawn_on_a_hud_layer(self):
        # menu.py gave the selected option perspective 2 and everything else
        # perspective 1; that projection is what makes it legible.
        menu = self._build(GroupsMenu())

        self.assertEqual(menu.selection.projection, 2)  # vs2.HUD
        self.assertEqual(menu.selected_sprite.y, 0)
        self.assertTrue(menu.selected_sprite.visible or menu.selected_label.visible)

    def test_selected_entry_is_not_also_drawn_in_the_tunnel(self):
        menu = self._build(GroupsMenu())

        self.assertNotIn(menu.selected_index, self._shown_slot_entries(menu))

    def test_moving_the_selection_swaps_which_row_is_hud_projected(self):
        menu = self._build(GroupsMenu())
        first = menu.selected_index

        menu._move(1)

        self.assertNotEqual(menu.selected_index, first)
        shown = self._shown_slot_entries(menu)
        self.assertIn(first, shown)                      # the old row comes back
        self.assertNotIn(menu.selected_index, shown)     # the new one leaves
        # ...and the HUD pair is showing the new selection, one way or another.
        self.assertNotEqual(menu.selected_sprite.visible, menu.selected_label.visible)

    def _label_frames(self, label, count):
        # Tile storage runs counter-clockwise; read it back in writing order.
        return [label.cells[label.columns - 1 - index] for index in range(count)]

    def test_rom_library_marks_the_selection_in_red(self):
        # menu.py's RomTextRow set bit 7 on the current row's glyphs;
        # tinyfont_menu packs the red half of the font at +0x80.
        with self._roms([{"path": "/a.nes", "label": "ALPHA"},
                         {"path": "/b.nes", "label": "BETA"}]):
            menu = self._build(RomLibraryMenu("emulators.nes"))

            self.assertEqual(self._label_frames(menu.selected_label, 5),
                             [ord(char) | 0x80 for char in "ALPHA"])
            row = [slot for slot in menu.slots if slot["entry_index"] == 1][0]
            self.assertEqual(self._label_frames(row["label"], 4),
                             [ord(char) for char in "BETA"])

    def test_other_menus_leave_their_selection_uncoloured(self):
        self.assertEqual(self._build(GroupsMenu()).selected_frame_offset, 0)

    def test_no_roms_notice_is_drawn_like_a_selected_option(self):
        with self._roms([]):
            menu = self._build(RomLibraryMenu("emulators.nes"))

            self.assertTrue(menu.selected_label.visible)
            self.assertEqual(menu.selected_label.y, 0)
            self.assertEqual(menu.selection.projection, 2)  # vs2.HUD
            self.assertFalse(any(slot["label"].visible or slot["sprite"].visible
                                 for slot in menu.slots))
            self.assertEqual(self._label_frames(menu.selected_label, 2),
                             [ord(char) | 0x80 for char in "NO"])

    def test_rom_libraries_pack_their_rows_closer(self):
        # The 4x6 list font is tiny next to the icons the default step suits.
        rom_menu = RomLibraryMenu("emulators.nes")
        self.assertLess(rom_menu.y_step, GroupsMenu().y_step)

    def test_restores_emulators_and_rom_library_via_the_debug_menu(self):
        # Emulators has no "Más aplicaciones" tile any more (see
        # test_emulators_group_has_no_more_apps_tile) -- resuming into it
        # goes through DebugMenu instead of GroupsMenu.
        native_apps.write_launcher_state({
            "group_id": group_tile_id("emulators"), "slug": "emulators.gb", "rom_path": None,
        })

        setup()

        stack = director.scene_stack
        self.assertEqual(len(stack), 3)
        self.assertIsInstance(stack[0], HighlightsMenu)
        self.assertIsInstance(stack[1], DebugMenu)
        self.assertIsInstance(stack[2], GroupMenu)
        self.assertEqual(stack[2].group_id, group_tile_id("emulators"))
        self.assertEqual(stack[2].entries[stack[2].selected_index][0], "emulators.gb")

    def test_restores_an_ordinary_group_via_more_apps(self):
        native_apps.write_launcher_state({
            "group_id": group_tile_id("alecu"), "slug": "alecu.vyruss", "rom_path": None,
        })

        setup()

        stack = director.scene_stack
        self.assertEqual(len(stack), 3)
        self.assertIsInstance(stack[0], HighlightsMenu)
        self.assertIsInstance(stack[1], GroupsMenu)
        self.assertIsInstance(stack[2], GroupMenu)
        self.assertEqual(stack[1].entries[stack[1].selected_index][0], group_tile_id("alecu"))
        self.assertEqual(stack[2].group_id, group_tile_id("alecu"))
        self.assertEqual(stack[2].entries[stack[2].selected_index][0], "alecu.vyruss")

    def test_restores_a_group_curated_on_the_root_straight_from_the_root(self):
        # Circular Arcade has its own tile on the root, so back from it
        # should land there, not in a "Más aplicaciones" it was never opened
        # from.
        group_id = group_tile_id("ld60")
        native_apps.write_launcher_state({
            "group_id": group_id, "slug": "ld60.rim_runner", "rom_path": None,
        })

        setup()

        stack = director.scene_stack
        self.assertEqual(len(stack), 2)
        self.assertIsInstance(stack[0], HighlightsMenu)
        self.assertEqual(stack[0].entries[stack[0].selected_index][0], group_id)
        self.assertIsInstance(stack[1], GroupMenu)
        self.assertEqual(stack[1].group_id, group_id)
        self.assertEqual(stack[1].entries[stack[1].selected_index][0], "ld60.rim_runner")


if __name__ == "__main__":
    unittest.main()
