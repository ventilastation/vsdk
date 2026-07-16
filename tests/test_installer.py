import gzip
import os
import sys
import tempfile
import unittest
import unittest.mock
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from ventilastation import installer
from test_menurom import build_rom, build_palette, icon_fixture, menu_fixture, inventory

SLUG = "alecu.testgame"
PREFIX = "games/alecu/testgame"


def game_rom_gz():
    rom = build_rom([("ship.png", 8, 8, 2, 0, 5)], [build_palette(20)])
    return gzip.compress(rom, 9, mtime=0)


def write_stripped_package(path, extra_members=(), icon=True):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(PREFIX + "/meta.json", b'{"api": "vs2", "order": 5}')
        archive.writestr(PREFIX + "/code/testgame.py", b"def main():\n    return None\n")
        archive.writestr(PREFIX + "/code/helpers/util.py", b"VALUE = 1\n")
        info = zipfile.ZipInfo("roms/%s.rom.gz" % SLUG)
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, game_rom_gz())
        if icon:
            archive.writestr("menu-icon.rom", icon_fixture(name="alecu/testgame/menu.png"))
        for name, data in extra_members:
            archive.writestr(name, data)
    return path


class InstallFromFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        os.makedirs(os.path.join(self.root, "roms"))
        with open(os.path.join(self.root, "roms", "menu.rom"), "wb") as f:
            f.write(menu_fixture())
        self.package_path = write_stripped_package(
            os.path.join(self.root, "%s.no-sound.vs2" % SLUG))

    def tearDown(self):
        self._tmp.cleanup()

    def _read(self, rel_path):
        with open(os.path.join(self.root, rel_path), "rb") as f:
            return f.read()

    def test_fresh_install(self):
        slug = installer.install_from_file(self.package_path, root=self.root)

        self.assertEqual(slug, SLUG)
        self.assertEqual(self._read(PREFIX + "/meta.json"),
                         b'{"api": "vs2", "order": 5}')
        self.assertEqual(self._read(PREFIX + "/code/helpers/util.py"), b"VALUE = 1\n")
        self.assertEqual(self._read("roms/%s.rom.gz" % SLUG), game_rom_gz())
        strip_names = [s[0] for s in inventory(self._read("roms/menu.rom"))[0]]
        self.assertIn("alecu/testgame/menu.png", strip_names)
        # No staging leftovers where the catalog could discover them.
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "games", "alecu"))),
                         ["testgame"])

    def test_upgrade_removes_previous_version(self):
        old_dir = os.path.join(self.root, PREFIX)
        os.makedirs(os.path.join(old_dir, "code"))
        with open(os.path.join(old_dir, "code", "stale.py"), "w") as f:
            f.write("OLD = True\n")
        # A previous scheme left a plain rom; it would shadow nothing itself,
        # but the fresh .rom.gz must not coexist with a stale sibling.
        with open(os.path.join(self.root, "roms", "%s.rom" % SLUG), "wb") as f:
            f.write(b"stale plain rom")

        installer.install_from_file(self.package_path, root=self.root)

        self.assertFalse(os.path.exists(os.path.join(old_dir, "code", "stale.py")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "roms", "%s.rom" % SLUG)))
        self.assertTrue(os.path.exists(os.path.join(self.root, "roms", "%s.rom.gz" % SLUG)))
        self.assertEqual(self._read(PREFIX + "/code/testgame.py"),
                         b"def main():\n    return None\n")

    def test_interrupted_stage_is_cleaned_on_retry(self):
        staging = os.path.join(self.root, "games", "alecu", ".testgame.new")
        os.makedirs(staging)
        with open(os.path.join(staging, "leftover.py"), "w") as f:
            f.write("junk\n")

        installer.install_from_file(self.package_path, root=self.root)

        self.assertFalse(os.path.exists(staging))
        self.assertTrue(os.path.exists(os.path.join(self.root, PREFIX, "meta.json")))

    def test_missing_icon_member_is_fine(self):
        package = write_stripped_package(
            os.path.join(self.root, "noicon.no-sound.vs2"), icon=False)
        slug = installer.install_from_file(package, root=self.root)
        self.assertEqual(slug, SLUG)
        strip_names = [s[0] for s in inventory(self._read("roms/menu.rom"))[0]]
        self.assertNotIn("alecu/testgame/menu.png", strip_names)

    def test_rejects_package_with_two_games(self):
        package = write_stripped_package(
            os.path.join(self.root, "twogames.no-sound.vs2"),
            extra_members=[("games/alecu/other/meta.json", b"{}")])
        with self.assertRaises(ValueError):
            installer.install_from_file(package, root=self.root)

    def test_rejects_traversal_member(self):
        package = write_stripped_package(
            os.path.join(self.root, "evil.no-sound.vs2"),
            extra_members=[("games/alecu/testgame/../../../evil.py", b"boom")])
        with self.assertRaises(ValueError):
            installer.install_from_file(package, root=self.root)

    def test_rejects_package_without_game_files(self):
        path = os.path.join(self.root, "empty.no-sound.vs2")
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("menu-icon.rom", icon_fixture())
        with self.assertRaises(ValueError):
            installer.install_from_file(path, root=self.root)

    def test_no_space_aborts_before_touching_anything(self):
        fake_statvfs = lambda path: (4096, 4096, 100, 4, 4, 0, 0, 0, 0, 255)
        with unittest.mock.patch.object(installer.os, "statvfs", fake_statvfs):
            with self.assertRaises(OSError) as ctx:
                installer.install_from_file(self.package_path, root=self.root)
        self.assertIn("no_space", str(ctx.exception))
        self.assertFalse(os.path.exists(os.path.join(self.root, PREFIX)))


if __name__ == "__main__":
    unittest.main()
