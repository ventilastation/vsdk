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

            entries = native_apps.list_roms("emulators.nes", root)

        self.assertEqual([entry["filename"] for entry in entries], [
            "A very long title that exceeds the line width.nes",
            "Zelda.nes",
            "archive.zip",
        ])
        self.assertEqual(entries[0]["label"], "A very long title ...")
        self.assertEqual(entries[1]["label"], "Zelda")
        self.assertEqual(entries[2]["path"], "/vfs/roms/nes/archive.zip")

    def test_game_boy_and_msx_libraries_exist_while_empty(self):
        self.assertTrue(native_apps.has_rom_library("emulators.gb"))
        self.assertTrue(native_apps.has_rom_library("emulators.msx"))
        self.assertEqual(native_apps.list_roms("emulators.gb", "/missing"), [])
        self.assertEqual(native_apps.list_roms("emulators.msx", "/missing"), [])

    def test_msx_compressed_rom_keeps_a_clean_label(self):
        with tempfile.TemporaryDirectory() as root:
            rom_dir = pathlib.Path(root) / "msx"
            rom_dir.mkdir()
            (rom_dir / "Metal Gear.rom.gz").write_bytes(b"rom")

            entries = native_apps.list_roms("emulators.msx", root)

        self.assertEqual(entries, [{
            "filename": "Metal Gear.rom.gz",
            "label": "Metal Gear",
            "path": "/vfs/roms/msx/Metal Gear.rom.gz",
        }])

    def test_write_and_read_launcher_state_round_trips(self):
        rom_path = "/vfs/roms/sms/Out Run.sms"
        native_apps.write_launcher_state({
            "group_id": "group:emulators", "slug": "emulators.sms", "rom_path": rom_path,
        })

        self.assertEqual(native_apps.read_launcher_state(), {
            "group_id": "group:emulators",
            "slug": "emulators.sms",
            "rom_path": rom_path,
        })

    def test_read_launcher_state_drops_rom_path_for_a_slug_without_a_library(self):
        native_apps.write_launcher_state({
            "group_id": "group:alecu", "slug": "alecu.vyruss", "rom_path": "stale",
        })

        # write_launcher_state stores whatever it's given; read_launcher_state
        # is where a rom_path that no longer makes sense (this slug has no
        # ROM library) gets dropped, since that's the boundary every restore
        # path actually goes through.
        self.assertEqual(native_apps.read_launcher_state(), {
            "group_id": "group:alecu",
            "slug": "alecu.vyruss",
            "rom_path": None,
        })

    def test_default_launcher_state_when_nothing_saved_yet(self):
        self.assertEqual(native_apps.read_launcher_state(), {
            "group_id": None,
            "slug": None,
            "rom_path": None,
        })

    def test_native_return_restores_last_group_and_rom(self):
        rom_path = "/vfs/roms/sms/Out Run.sms"
        native_apps.write_launcher_state({
            "group_id": "group:emulators", "slug": "emulators.sms", "rom_path": rom_path,
        })
        native_apps.write_boot_intent(native_apps.build_boot_intent("emulators.sms", rom_path))

        restored = native_apps.consume_native_return()

        self.assertEqual(restored, {
            "group_id": "group:emulators",
            "slug": "emulators.sms",
            "rom_path": rom_path,
        })
        self.assertEqual(native_apps.read_boot_intent(), {"mode": "micropython"})
        self.assertEqual(native_apps.read_last_exit()["rom"], rom_path)

    def test_label_truncation_is_one_third_of_the_display(self):
        self.assertEqual(native_apps.trim_rom_label("x" * 21), "x" * 21)
        self.assertEqual(native_apps.trim_rom_label("x" * 22), "x" * 18 + "...")


if __name__ == "__main__":
    unittest.main()
