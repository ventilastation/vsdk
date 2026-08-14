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

        def fake_load_rom(_filename):
            stripes["menu.png"] = 0
            self.runtime_director.platform.sprites.stripes[0] = {
                "width": 64, "height": 30, "frames": 16, "palette": 0,
            }
            stripes["tinyfont_menu.png"] = 1
            self.runtime_director.platform.sprites.stripes[1] = {
                "width": 4, "height": 6, "frames": 255, "palette": 0,
            }

        self.runtime_director.load_rom = fake_load_rom

    def tearDown(self):
        reset_runtime()
        api_guard.reset()

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
