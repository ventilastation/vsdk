import gzip
import os
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from ventilastation import menurom
from test_rom_format import parse_rom


def build_palette(shade):
    return (bytes([0xFF]) + bytes([shade]) * 3) * 256


def build_rom(strips, palettes):
    """strips: (name, width, height, frames, palette_index, fill_byte)."""
    blobs = []
    for name, width, height, frames, palette, fill in strips:
        encoded = name.encode()
        real_width = 256 if width == 255 else width
        pixels = bytes([fill]) * (real_width * height * frames)
        blobs.append(bytes([len(encoded)]) + encoded
                     + bytes([width, height, frames, palette]) + pixels)
    return menurom.serialize(
        [[name.encode(), palette, blob]
         for (name, _w, _h, _f, palette, _fill), blob in zip(strips, blobs)],
        palettes)


def menu_fixture():
    """A tree-style menu rom: two strips sharing one palette."""
    return build_rom(
        [("menu.png", 16, 16, 16, 0, 1),
         ("alecu/vyruss_vs2/menu.png", 32, 32, 2, 0, 2)],
        [build_palette(10)])


def icon_fixture(name="alecu/newgame/menu.png", fill=3, shade=99):
    return build_rom([(name, 32, 32, 4, 0, fill)], [build_palette(shade)])


def inventory(data):
    strips, palettes = parse_rom(data)
    return ([(s["name"], s["width"], s["height"], s["frames"], s["palette"])
             for s in strips], len(palettes))


class MergeIconTests(unittest.TestCase):
    def test_appends_new_strip_with_its_palette(self):
        merged = menurom.merge_icon(menu_fixture(), icon_fixture())
        strips, palette_count = inventory(merged)
        self.assertEqual(strips, [
            ("menu.png", 16, 16, 16, 0),
            ("alecu/vyruss_vs2/menu.png", 32, 32, 2, 0),
            ("alecu/newgame/menu.png", 32, 32, 4, 1),
        ])
        self.assertEqual(palette_count, 2)
        _, palettes = parse_rom(merged)
        self.assertEqual(bytes(palettes[1]), build_palette(99))

    def test_replaces_strip_on_reinstall_without_growing(self):
        merged = menurom.merge_icon(menu_fixture(), icon_fixture())
        again = menurom.merge_icon(
            merged, icon_fixture(fill=7, shade=55))
        strips, palette_count = inventory(again)
        self.assertEqual(len(strips), 3)
        self.assertEqual(palette_count, 2)
        _, palettes = parse_rom(again)
        self.assertEqual(bytes(palettes[1]), build_palette(55))

    def test_replacing_a_shared_palette_strip_keeps_the_shared_palette(self):
        merged = menurom.merge_icon(
            menu_fixture(), icon_fixture(name="alecu/vyruss_vs2/menu.png", shade=77))
        strips, palette_count = inventory(merged)
        self.assertEqual(strips, [
            ("menu.png", 16, 16, 16, 0),
            ("alecu/vyruss_vs2/menu.png", 32, 32, 4, 1),
        ])
        self.assertEqual(palette_count, 2)
        _, palettes = parse_rom(merged)
        self.assertEqual(bytes(palettes[0]), build_palette(10))
        self.assertEqual(bytes(palettes[1]), build_palette(77))

    def test_pixel_data_survives_the_merge(self):
        merged = menurom.merge_icon(menu_fixture(), icon_fixture(fill=3))
        strips, _ = parse_rom(merged)
        added = next(s for s in strips if s["name"] == "alecu/newgame/menu.png")
        pixels = merged[added["pixels_start"]:added["pixels_start"] + added["pixels_len"]]
        self.assertEqual(bytes(pixels), bytes([3]) * added["pixels_len"])

    def test_icon_rom_without_strips_is_rejected(self):
        empty = menurom.serialize([], [build_palette(0)])
        with self.assertRaises(ValueError):
            menurom.merge_icon(menu_fixture(), empty)


class MenuRomFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.roms_dir = os.path.join(self._tmp.name, "roms")
        self.packages_dir = os.path.join(self._tmp.name, "packages")
        os.makedirs(self.roms_dir)
        os.makedirs(self.packages_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_gz(self, data):
        with open(os.path.join(self.roms_dir, "menu.rom.gz"), "wb") as f:
            f.write(gzip.compress(data, 9, mtime=0))

    def _write_plain(self, data):
        with open(os.path.join(self.roms_dir, "menu.rom"), "wb") as f:
            f.write(data)

    def _read_plain(self):
        with open(os.path.join(self.roms_dir, "menu.rom"), "rb") as f:
            return f.read()

    def _write_package(self, filename, icon_data):
        path = os.path.join(self.packages_dir, filename)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("games/alecu/newgame/meta.json", b"{}")
            archive.writestr("menu-icon.rom", icon_data)

    def test_merge_into_gz_writes_plain_and_drops_gz(self):
        self._write_gz(menu_fixture())
        menurom.merge_icon_into_menu(icon_fixture(), roms_dir=self.roms_dir)
        self.assertFalse(os.path.exists(os.path.join(self.roms_dir, "menu.rom.gz")))
        strips, _ = inventory(self._read_plain())
        self.assertEqual(len(strips), 3)

    def test_merge_into_plain_updates_in_place(self):
        self._write_plain(menu_fixture())
        menurom.merge_icon_into_menu(icon_fixture(), roms_dir=self.roms_dir)
        strips, _ = inventory(self._read_plain())
        self.assertEqual(len(strips), 3)

    def test_refresh_remerges_stored_packages_after_ota(self):
        self._write_gz(menu_fixture())
        self._write_plain(b"stale merged rom from before the OTA")
        self._write_package("alecu.newgame.no-sound.vs2", icon_fixture())

        refreshed = menurom.refresh_from_packages(
            packages_dir=self.packages_dir, roms_dir=self.roms_dir)

        self.assertTrue(refreshed)
        self.assertFalse(os.path.exists(os.path.join(self.roms_dir, "menu.rom.gz")))
        strips, _ = inventory(self._read_plain())
        self.assertEqual(len(strips), 3)

    def test_refresh_is_a_noop_without_gz_or_packages(self):
        self._write_plain(menu_fixture())
        self.assertFalse(menurom.refresh_from_packages(
            packages_dir=self.packages_dir, roms_dir=self.roms_dir))

        self._write_gz(menu_fixture())
        self.assertFalse(menurom.refresh_from_packages(
            packages_dir=self.packages_dir, roms_dir=self.roms_dir))
        # No packages stored: the tree .gz stays authoritative.
        self.assertTrue(os.path.exists(os.path.join(self.roms_dir, "menu.rom.gz")))


if __name__ == "__main__":
    unittest.main()
