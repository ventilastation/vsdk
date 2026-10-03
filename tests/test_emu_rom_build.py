"""emulator/emu.py brings the sprite ROMs up to date before it starts the
local MicroPython, and skips that when there is no local MicroPython."""

import importlib.util
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location("emu_under_test", ROOT / "emulator" / "emu.py")
emu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(emu)


class StopBeforeEmulating(Exception):
    pass


class RomBuildTests(unittest.TestCase):
    def setUp(self):
        self.rom_builds = 0

        def build_roms():
            self.rom_builds += 1

        self.saved_build_roms = emu._build_roms
        emu._build_roms = build_roms
        # main() imports config right after the ROM step; stop there.
        self.saved_config = sys.modules.get("config")
        fake_config = types.ModuleType("config")

        def configure(_args):
            raise StopBeforeEmulating()

        fake_config.configure = configure
        sys.modules["config"] = fake_config

    def tearDown(self):
        emu._build_roms = self.saved_build_roms
        if self.saved_config is None:
            sys.modules.pop("config", None)
        else:
            sys.modules["config"] = self.saved_config

    def run_main(self, *argv):
        with self.assertRaises(StopBeforeEmulating):
            emu.main(list(argv))

    def test_local_simulation_builds_roms(self):
        self.run_main()
        self.assertEqual(self.rom_builds, 1)

    def test_remote_and_no_display_modes_do_not(self):
        self.run_main("--remote")
        self.run_main("--no-display")
        self.assertEqual(self.rom_builds, 0)


if __name__ == "__main__":
    unittest.main()
