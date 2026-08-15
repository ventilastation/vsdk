"""Checks for the vs2-based launcher (system/launcher/code): group/tile
construction, ListMenu's on_select/on_back navigation and state-saving, and
main()/setup()'s restore-after-reboot logic.

on_select()/on_back() are tested directly against a constructed-but-not-
built scene instance (no on_enter()/build() involved) -- they only touch
plain attributes (self.entries, self.group_id, self.slug, self.selected_index)
and vs2.Scene.push()/pop(), which just record a pending transition rather
than touching any drawable or rom. That keeps these tests fast and immune to
asset-pack faking. One end-to-end test exercises setup()'s real
director.push() chain, following tests/test_mapdemo_vs2.py's pattern for a
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
    GROUP_MEMBERS,
    GROUP_TILES,
    MAIN_MENU_OPTIONS,
    DebugMenu,
    GroupMenu,
    GroupsMenu,
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

    def test_group_tiles_are_flagged_have_members_and_no_borrowed_icon(self):
        group_ids = [slug for slug, _s, _f, _t in MAIN_MENU_OPTIONS if is_group_tile(slug)]
        self.assertEqual(set(group_ids), set(GROUP_MEMBERS))
        for _order, slug, strip, _frame, _title in GROUP_TILES:
            self.assertIsNone(strip, "%r should have no icon of its own" % (slug,))
        for group_id, options in GROUP_MEMBERS.items():
            self.assertTrue(options, "%r has no members" % (group_id,))

    def test_emulators_group_keeps_its_real_icons(self):
        emulators = dict((slug, (strip, title)) for slug, strip, _f, title in GROUP_MEMBERS[group_tile_id("emulators")])
        self.assertEqual(set(emulators), set(native_apps.APP_REGISTRY))
        self.assertEqual(emulators["emulators.nes"], ("nes.png", "NES"))

    def test_no_native_slug_survives_at_the_top_level(self):
        top_level_slugs = [slug for slug, _s, _f, _t in MAIN_MENU_OPTIONS]
        self.assertNotIn("emulators.voom", top_level_slugs)
        self.assertIn(group_tile_id("emulators"), top_level_slugs)

    def test_tech_demos_group_includes_hidden_games_and_hardware_test(self):
        tech_demos = [slug for slug, _s, _f, _t in GROUP_MEMBERS[group_tile_id("tech_demos")]]
        self.assertIn("demos.input_demo", tech_demos)
        self.assertIn("alecu.ventilagon_game", tech_demos)
        self.assertIn("vs2_hardware", tech_demos)

    def test_alecu_group_excludes_its_hidden_game(self):
        alecu = [slug for slug, _s, _f, _t in GROUP_MEMBERS[group_tile_id("alecu")]]
        self.assertIn("alecu.vyruss", alecu)
        self.assertNotIn("alecu.ventilagon_game", alecu)


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

        self.assertEqual(scene.entries, MAIN_MENU_OPTIONS)
        self.assertEqual(scene.selected_index, 0)

    def test_restoring_a_group_id_selects_its_tile(self):
        group_id = group_tile_id("emulators")
        scene = main({"group_id": group_id, "slug": "emulators.nes", "rom_path": None})

        self.assertEqual(scene.entries[scene.selected_index][0], group_id)

    def test_restoring_a_standalone_slug_selects_it_directly(self):
        scene = main({"group_id": None, "slug": "gallery", "rom_path": None})

        self.assertEqual(scene.entries[scene.selected_index][0], "gallery")


class SetupIntegrationTests(unittest.TestCase):
    """One end-to-end check that setup() really reconstructs a multi-level
    stack via real director.push() calls, following test_mapdemo_vs2.py's
    pattern for exercising a vs2.Scene under the headless platform."""

    def setUp(self):
        reset_runtime()
        api_guard.reset()
        self.runtime_director = configure_runtime("headless")
        stripes.clear()

        # Mirrors system/menu/images/__images__.yaml: every strip the launcher
        # resolves during build(), with the real ROM's metadata. favalli is a
        # `fullscreen:` entry, so it arrives reprojected to 256x54 rather than
        # at its 320x320 source size.
        fake_strips = [
            ("menu.png", 64, 30, 16, 0),
            ("vslogo.png", 84, 11, 1, 0),
            ("loviejo-3.png", 84, 11, 1, 0),
            ("favalli.png", 256, 54, 1, 0),
            ("tinyfont_menu.png", 4, 6, 255, 1),
            ("rainbow8x8.png", 8, 8, 256, 2),
        ]

        def fake_load_rom(_filename):
            for index, (name, width, height, frames, palette) in enumerate(fake_strips):
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

    def test_root_menu_draws_its_backdrop_wordmark_and_byline(self):
        # Lost in the vs2 port and restored: the disc should not come up as a
        # bare list of tiles.
        root = self._build(GroupsMenu())

        backdrop = root.backdrop.sprites
        self.assertEqual([sprite.image.name for sprite in backdrop], ["favalli.png"])
        branding = [sprite.image.name for sprite in root.branding.sprites]
        self.assertEqual(branding, ["vslogo.png", "loviejo-3.png"])

    def test_root_backdrop_paints_behind_the_list_and_branding_in_front(self):
        root = self._build(GroupsMenu())
        order = [layer.name for layer in root.layers]

        self.assertLess(order.index("backdrop"), order.index("world"))
        self.assertLess(order.index("world"), order.index("branding"))

    def test_root_menu_has_no_text_heading(self):
        self.assertIsNone(self._build(GroupsMenu()).heading)

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

    def test_rom_libraries_pack_their_rows_closer(self):
        # The 4x6 list font is tiny next to the icons the default step suits.
        rom_menu = RomLibraryMenu("emulators.nes")
        self.assertLess(rom_menu.y_step, GroupsMenu().y_step)

    def test_restores_group_and_rom_library_on_top_of_root(self):
        native_apps.write_launcher_state({
            "group_id": group_tile_id("emulators"), "slug": "emulators.gb", "rom_path": None,
        })

        setup()

        stack = director.scene_stack
        self.assertEqual(len(stack), 2)
        self.assertIsInstance(stack[0], GroupsMenu)
        self.assertIsInstance(stack[1], GroupMenu)
        self.assertEqual(stack[1].group_id, group_tile_id("emulators"))
        self.assertEqual(stack[1].entries[stack[1].selected_index][0], "emulators.gb")


if __name__ == "__main__":
    unittest.main()
