import gzip
import os
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from ventilastation import menurom, romformat
from test_rom_format import parse_rom


def build_palette(shade):
    return (bytes([0xFF]) + bytes([shade]) * 3) * 256


def build_rom(strips, palettes, glyphs=b""):
    """strips: (name, width, height, frames, palette_index, fill_byte)."""
    return menurom.serialize(
        [[name.encode(), palette,
          romformat.encode_record(name.encode(), width, height, frames, palette,
                                  bytes([fill]) * (width * height * frames), glyphs)]
         for name, width, height, frames, palette, fill in strips],
        palettes)


def build_legacy_rom(strips, palettes):
    """A rom as packages built before the current encoding carry it: width
    256 stored as 255, frames as is, no glyph trailer."""
    blobs = []
    for name, width, height, frames, palette, fill in strips:
        encoded = name.encode()
        blobs.append(bytes([len(encoded)]) + encoded
                     + bytes([min(width, 255), height, min(frames, 255), palette])
                     + bytes([fill]) * (width * height * frames))
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

    def test_glyph_trailers_survive_the_merge(self):
        menu = build_rom([("font.png", 8, 8, 4, 0, 1)], [build_palette(10)], glyphs=b"ABCD")
        merged = menurom.merge_icon(menu, icon_fixture())
        strips, _ = parse_rom(merged)
        self.assertEqual(strips[0]["glyphs"], b"ABCD")
        self.assertEqual(strips[1]["glyphs"], b"")

    def test_an_icon_from_an_older_package_is_reencoded(self):
        icon = build_legacy_rom([("alecu/old/menu.png", 32, 30, 2, 0, 4)], [build_palette(33)])
        merged = menurom.merge_icon(menu_fixture(), icon)
        strips, _ = parse_rom(merged)  # record-exact: fails on a legacy record
        added = strips[-1]
        self.assertEqual((added["name"], added["width"], added["height"], added["frames"]),
                         ("alecu/old/menu.png", 32, 30, 2))
        pixels = merged[added["pixels_start"]:added["pixels_start"] + added["pixels_len"]]
        self.assertEqual(bytes(pixels), bytes([4]) * added["pixels_len"])

    def test_an_older_full_circle_icon_keeps_its_width(self):
        icon = build_legacy_rom([("alecu/ring/menu.png", 256, 4, 1, 0, 6)], [build_palette(40)])
        strips, _ = parse_rom(menurom.merge_icon(menu_fixture(), icon))
        self.assertEqual(strips[-1]["width"], 256)

    def test_an_icon_shorter_than_its_header_is_rejected(self):
        # It must not splice a neighbour's bytes into the merged menu rom.
        icon = build_legacy_rom([("alecu/cut/menu.png", 32, 30, 2, 0, 4)], [build_palette(1)])
        name_len = len("alecu/cut/menu.png")
        offset = struct.unpack_from("<L", icon, 4)[0]
        frames_at = offset + 1 + name_len + 2
        cut = bytearray(icon)
        cut[frames_at] = 9  # header now claims 9 frames; the record holds 2
        with self.assertRaises(ValueError):
            menurom.merge_icon(menu_fixture(), bytes(cut))

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
        with open(os.path.join(self.roms_dir, "menu.romz"), "wb") as f:
            f.write(struct.pack("<I", len(data)) + gzip.compress(data, 9, mtime=0))

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
        self.assertFalse(os.path.exists(os.path.join(self.roms_dir, "menu.romz")))
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
        self.assertFalse(os.path.exists(os.path.join(self.roms_dir, "menu.romz")))
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
        self.assertTrue(os.path.exists(os.path.join(self.roms_dir, "menu.romz")))


if __name__ == "__main__":
    unittest.main()
