import os
import pathlib
import sys
import tempfile
import time
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "micropython"))

# native_apps imports the scene/director layer, whose production runtime uses
# MicroPython's uos/utime modules.  Supply their small compatible surface for
# this CPython unit test.
sys.modules.setdefault("uos", os)
if "utime" not in sys.modules:
    utime = types.ModuleType("utime")
    utime.ticks_ms = lambda: int(time.monotonic() * 1000)
    utime.ticks_add = lambda value, delta: value + delta
    utime.ticks_diff = lambda value, other: value - other
    utime.sleep_ms = lambda value: time.sleep(value / 1000)
    sys.modules["utime"] = utime

from ventilastation.director import configure_runtime, reset_runtime
from ventilastation import native_apps


class NativeAppsTests(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        configure_runtime("headless")

    def tearDown(self):
        reset_runtime()

    def test_rom_library_filters_sorts_and_labels_basename(self):
        with tempfile.TemporaryDirectory() as root:
            rom_dir = pathlib.Path(root) / "nes"
            rom_dir.mkdir()
            for name in (
                "Zelda.nes",
                "A very long title that exceeds the line width.nes",
                "ignore.txt",
                "archive.zip",
            ):
                (rom_dir / name).write_bytes(b"rom")
            os.mkdir(rom_dir / "folder.nes")

            entries = native_apps.list_roms("native.nes", root)

        self.assertEqual([entry["filename"] for entry in entries], [
            "A very long title that exceeds the line width.nes",
            "Zelda.nes",
            "archive.zip",
        ])
        self.assertEqual(entries[0]["label"], "A very long title ...")
        self.assertEqual(entries[1]["label"], "Zelda")
        self.assertEqual(entries[2]["path"], "/vfs/roms/nes/archive.zip")

    def test_game_boy_and_msx_libraries_exist_while_empty(self):
        self.assertTrue(native_apps.has_rom_library("native.gb"))
        self.assertTrue(native_apps.has_rom_library("native.msx"))
        self.assertEqual(native_apps.list_roms("native.gb", "/missing"), [])
        self.assertEqual(native_apps.list_roms("native.msx", "/missing"), [])

    def test_msx_compressed_rom_keeps_a_clean_label(self):
        with tempfile.TemporaryDirectory() as root:
            rom_dir = pathlib.Path(root) / "msx"
            rom_dir.mkdir()
            (rom_dir / "Metal Gear.rom.gz").write_bytes(b"rom")

            entries = native_apps.list_roms("native.msx", root)

        self.assertEqual(entries, [{
            "filename": "Metal Gear.rom.gz",
            "label": "Metal Gear",
            "path": "/vfs/roms/msx/Metal Gear.rom.gz",
        }])

    def test_native_return_restores_last_submenu_and_rom(self):
        rom_path = "/vfs/roms/sms/Out Run.sms"
        native_apps.remember_rom_selection("native.sms", rom_path)
        native_apps.write_boot_intent(native_apps.build_boot_intent("native.sms", rom_path))
        native_apps.leave_rom_menu("native.nes")

        restored = native_apps.consume_native_return()

        self.assertEqual(restored, {
            "main_slug": "native.sms",
            "submenu_slug": "native.sms",
            "rom_path": rom_path,
        })
        self.assertEqual(native_apps.read_boot_intent(), {"mode": "micropython"})
        self.assertEqual(native_apps.read_last_exit()["rom"], rom_path)

    def test_d_back_state_keeps_the_emulator_selected_after_reboot(self):
        native_apps.remember_rom_selection("native.gb", "/vfs/roms/gb/Tetris.gb")

        native_apps.leave_rom_menu("native.gb")

        self.assertEqual(native_apps.read_launcher_state(), {
            "main_slug": "native.gb",
            "submenu_slug": None,
            "rom_path": None,
        })

    def test_label_truncation_is_one_third_of_the_display(self):
        self.assertEqual(native_apps.trim_rom_label("x" * 21), "x" * 21)
        self.assertEqual(native_apps.trim_rom_label("x" * 22), "x" * 18 + "...")


if __name__ == "__main__":
    unittest.main()
