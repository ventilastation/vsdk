import os
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

try:
    import package_game
    HAVE_BUILD_DEPS = True
except ImportError as error:
    HAVE_BUILD_DEPS = False
    IMPORT_ERROR = error

from ventilastation import menurom
from test_rom_format import parse_rom

VYRUSS = os.path.join(ROOT, "games", "alecu", "vyruss_vs2")


@unittest.skipUnless(HAVE_BUILD_DEPS,
                     "rom build deps unavailable: %s" % (globals().get("IMPORT_ERROR"),))
class PackageGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.package_path = package_game.build_package(VYRUSS, cls._tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_package_member_set(self):
        with zipfile.ZipFile(self.package_path) as archive:
            names = sorted(archive.namelist())
        self.assertIn("meta.json", names)
        self.assertIn("menu.png", names)
        self.assertIn("code/vyruss_vs2.py", names)
        self.assertIn("roms/alecu.vyruss_vs2.rom", names)
        self.assertIn("menu-icon.rom", names)
        self.assertIn("sounds/shoot1.mp3", names)
        # The rom is the single source of truth: no PNG sources, no yaml,
        # and no generated .wav conversions travel in a package.
        self.assertFalse([n for n in names if n.startswith("images/")])
        self.assertFalse([n for n in names if n.endswith((".yaml", ".wav"))])

    def test_package_filename_and_location(self):
        self.assertEqual(os.path.basename(self.package_path), "alecu.vyruss_vs2.vs2")

    def test_sounds_are_stored_not_deflated(self):
        with zipfile.ZipFile(self.package_path) as archive:
            for info in archive.infolist():
                expected = (zipfile.ZIP_STORED if info.filename.startswith("sounds/")
                            else zipfile.ZIP_DEFLATED)
                self.assertEqual(info.compress_type, expected, info.filename)

    def test_menu_icon_rom_matches_catalog_strip_id(self):
        with zipfile.ZipFile(self.package_path) as archive:
            icon = archive.read("menu-icon.rom")
        strips, palettes = parse_rom(icon)
        self.assertEqual(len(strips), 1)
        self.assertEqual(strips[0]["name"], "alecu/vyruss_vs2/menu.png")
        self.assertEqual(len(palettes), 1)
        # And it merges cleanly into a menu rom.
        from test_menurom import menu_fixture, inventory
        merged = menurom.merge_icon(menu_fixture(), icon)
        names = [s[0] for s in inventory(merged)[0]]
        self.assertIn("alecu/vyruss_vs2/menu.png", names)

    def test_game_rom_parses(self):
        with zipfile.ZipFile(self.package_path) as archive:
            rom = archive.read("roms/alecu.vyruss_vs2.rom")
        strips, palettes = parse_rom(rom)
        self.assertTrue(strips)
        self.assertTrue(palettes)

    def test_rebuild_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as other:
            second = package_game.build_package(VYRUSS, other)
            with open(self.package_path, "rb") as a, open(second, "rb") as b:
                self.assertEqual(a.read(), b.read())

    def test_resolve_game_dir_accepts_slug_forms(self):
        for form in ("alecu/vyruss_vs2", "alecu.vyruss_vs2",
                     "games/alecu/vyruss_vs2", VYRUSS):
            self.assertEqual(str(package_game.resolve_game_dir(form)),
                             os.path.realpath(VYRUSS), form)


if __name__ == "__main__":
    unittest.main()
