import os
import sys
import time
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
sys.modules.setdefault("uos", os)
if "utime" not in sys.modules:
    class _Utime:
        @staticmethod
        def ticks_ms():
            return int(time.time() * 1000)

        @staticmethod
        def ticks_add(value, delta):
            return value + delta

        @staticmethod
        def ticks_diff(end, start):
            return end - start

        @staticmethod
        def sleep_ms(ms):
            time.sleep(ms / 1000.0)

    sys.modules["utime"] = _Utime

import vsdk_logo_strip as logo_strip


class _FakeReset(Exception):
    """Raised by the fake machine.reset() so tests can observe it fired
    without the process actually resetting (there's nothing to reset here)."""


class FakeDisplay:
    def __init__(self):
        self.palette = None
        self.inited_with = None
        self.gamma_mode = None

    def init(self, pixels, *hw_config):
        self.inited_with = (pixels, hw_config)

    def set_gamma_mode(self, mode):
        self.gamma_mode = mode

    def set_palettes(self, palette):
        self.palette = palette


class FakeSprite:
    def __init__(self):
        self.strip = None
        self.perspective = None
        self.x = None
        self.y = None
        self.frame = None

    def set_strip(self, value):
        self.strip = value

    def set_perspective(self, value):
        self.perspective = value

    def set_x(self, value):
        self.x = value

    def set_y(self, value):
        self.y = value

    def set_frame(self, value):
        self.frame = value


class FakeSprites:
    def __init__(self):
        self.stripes = {}
        self.last_sprite = None

    def set_imagestrip(self, number, stripmap):
        self.stripes[number] = stripmap

    def Sprite(self):
        self.last_sprite = FakeSprite()
        return self.last_sprite


def _install_fakes(nvs_values=None, partitions=()):
    """Install minimal esp32/machine/vshw_povdisplay/vshw_sprites stand-ins.
    `partitions` is what esp32.Partition.find() returns for label="micropython".
    `nvs_values` seeds the "vs_board" NVS namespace (default: all present)."""
    if nvs_values is None:
        nvs_values = {
            "hall_gpio": 7, "irdiode_gpio": 7, "led_spi_host": 2,
            "led_clk": 12, "led_mosi": 13, "led_cs": 14, "led_freq": 20000000,
        }

    machine = types.ModuleType("machine")
    machine.reset_calls = []

    def _reset():
        machine.reset_calls.append(True)
        raise _FakeReset()
    machine.reset = _reset

    class FakeWDT:
        def __init__(self, timeout_ms=None):
            self.timeout_ms = timeout_ms
            self.feed_count = 0

        def feed(self):
            self.feed_count += 1

    machine.WDT = FakeWDT
    sys.modules["machine"] = machine

    esp32 = types.ModuleType("esp32")

    class FakeNVS:
        def __init__(self, namespace):
            self.namespace = namespace

        def get_i32(self, key):
            if self.namespace != "vs_board" or key not in nvs_values:
                raise OSError("no such key")
            return nvs_values[key]

    class FakePartition:
        TYPE_APP = 0

        @staticmethod
        def find(type_, label=None):
            if label == "micropython":
                return list(partitions)
            return []

    esp32.NVS = FakeNVS
    esp32.Partition = FakePartition
    sys.modules["esp32"] = esp32

    display = FakeDisplay()
    sprites = FakeSprites()
    povdisplay_module = types.ModuleType("vshw_povdisplay")
    povdisplay_module.init = display.init
    povdisplay_module.set_gamma_mode = display.set_gamma_mode
    povdisplay_module.set_palettes = display.set_palettes
    sys.modules["vshw_povdisplay"] = povdisplay_module

    sprites_module = types.ModuleType("vshw_sprites")
    sprites_module.set_imagestrip = sprites.set_imagestrip
    sprites_module.Sprite = sprites.Sprite
    sys.modules["vshw_sprites"] = sprites_module

    return machine, esp32, display, sprites


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        for name in ("machine", "esp32", "vshw_povdisplay", "vshw_sprites", "updater", "vsdk_recovery"):
            sys.modules.pop(name, None)

    def tearDown(self):
        for name in ("machine", "esp32", "vshw_povdisplay", "vshw_sprites"):
            sys.modules.pop(name, None)

    def test_make_sprite_installs_logo_strip_and_starts_at_boot_frame(self):
        machine, esp32, display, sprites = _install_fakes()
        import vsdk_recovery as recovery

        sprite = recovery._make_sprite()

        self.assertIs(sprite, sprites.last_sprite)
        self.assertEqual(sprite.frame, logo_strip.FRAME_BOOT)
        self.assertEqual(sprite.perspective, recovery._PERSPECTIVE_HUD)
        self.assertEqual(display.inited_with, (54, (7, 7, 2, 12, 13, 14, 20000000)))
        self.assertEqual(display.palette, logo_strip.PALETTE)
        self.assertEqual(sprites.stripes[0], logo_strip.STRIP)

    def test_make_sprite_returns_none_when_board_not_provisioned(self):
        _install_fakes(nvs_values={})
        import vsdk_recovery as recovery

        sprite = recovery._make_sprite()

        self.assertIsNone(sprite)

    def test_progress_handler_transitions_frames_and_records_outcome(self):
        _install_fakes()
        import vsdk_recovery as recovery

        sprite = recovery._make_sprite()
        handle, outcome = recovery._make_progress_handler(sprite, wdt=None)

        handle(b"ota_progress start fetching_manifest 0\n")
        self.assertEqual(sprite.frame, logo_strip.FRAME_WIFI)
        self.assertIsNone(outcome["ok"])

        handle(b"ota_progress file some_file 10\n")
        self.assertEqual(sprite.frame, logo_strip.FRAME_DOWNLOADING)

        handle(b"ota_progress partition micropython 50\n")
        self.assertEqual(sprite.frame, logo_strip.FRAME_DOWNLOADING)

        handle(b"ota_error manifest_fetch_failed: timeout\n")
        self.assertEqual(sprite.frame, logo_strip.FRAME_ERROR)
        self.assertFalse(outcome["ok"])

    def test_progress_handler_success_sets_success_frame(self):
        _install_fakes()
        import vsdk_recovery as recovery

        sprite = recovery._make_sprite()
        handle, outcome = recovery._make_progress_handler(sprite, wdt=None)

        handle(b"ota_done ok\n")

        self.assertEqual(sprite.frame, logo_strip.FRAME_SUCCESS)
        self.assertTrue(outcome["ok"])

    def test_progress_handler_feeds_wdt_on_every_line(self):
        machine, _esp32, _display, _sprites = _install_fakes()
        import vsdk_recovery as recovery

        wdt = machine.WDT(timeout_ms=30000)
        sprite = recovery._make_sprite()
        handle, _outcome = recovery._make_progress_handler(sprite, wdt)

        handle(b"ota_progress start fetching_manifest 0\n")
        handle(b"ota_progress file a 10\n")

        self.assertEqual(wdt.feed_count, 2)

    def test_progress_handler_tolerates_no_sprite(self):
        _install_fakes()
        import vsdk_recovery as recovery

        handle, outcome = recovery._make_progress_handler(None, wdt=None)
        handle(b"ota_done ok\n")  # must not raise

        self.assertTrue(outcome["ok"])

    def test_boot_into_micropython_hands_off_when_partition_exists(self):
        set_boot_calls = []
        fake_partition = types.SimpleNamespace(set_boot=lambda: set_boot_calls.append(True))
        machine, esp32, _display, _sprites = _install_fakes(partitions=[fake_partition])
        import vsdk_recovery as recovery

        with self.assertRaises(_FakeReset):
            recovery._boot_into_micropython_if_ready()

        self.assertEqual(machine.reset_calls, [True])
        self.assertEqual(set_boot_calls, [True])

    def test_boot_into_micropython_noop_when_no_partition(self):
        machine, esp32, _display, _sprites = _install_fakes(partitions=[])
        import vsdk_recovery as recovery

        result = recovery._boot_into_micropython_if_ready()

        self.assertFalse(result)
        self.assertEqual(machine.reset_calls, [])

    def test_run_resets_on_fatal_error_before_any_backoff_sleep(self):
        _install_fakes(partitions=[])
        import vsdk_recovery as recovery
        import updater

        def _boom(url, send_fn):
            raise RuntimeError("network stack exploded")
        original_run = updater.run
        updater.run = _boom
        try:
            with self.assertRaises(_FakeReset):
                recovery.run()
        finally:
            updater.run = original_run


class LogoStripTests(unittest.TestCase):
    def test_strip_header_matches_declared_dimensions(self):
        header = logo_strip.STRIP[0:4]
        self.assertEqual(header[0], 255)  # width byte: "actually 256"
        self.assertEqual(header[1], logo_strip.HEIGHT)
        self.assertEqual(header[2], logo_strip.TOTAL_FRAMES)
        self.assertEqual(header[3], logo_strip.PALETTE_GROUP)

    def test_strip_data_length_matches_full_circle_all_frames(self):
        expected = 4 + logo_strip.WIDTH * logo_strip.HEIGHT * logo_strip.TOTAL_FRAMES
        self.assertEqual(len(logo_strip.STRIP), expected)

    def test_each_frame_is_solid_colored_by_its_own_frame_index(self):
        frame_size = logo_strip.WIDTH * logo_strip.HEIGHT
        for frame in range(logo_strip.TOTAL_FRAMES):
            start = 4 + frame * frame_size
            block = logo_strip.STRIP[start:start + frame_size]
            self.assertEqual(len(set(block)), 1, "frame %d is not solid" % frame)
            self.assertEqual(block[0], frame)

    def test_palette_has_256_entries_of_4_bytes(self):
        self.assertEqual(len(logo_strip.PALETTE), 1024)

    def test_named_frame_colors_are_present_at_their_palette_index(self):
        for frame in range(logo_strip.TOTAL_FRAMES):
            entry = logo_strip.PALETTE[frame * 4:frame * 4 + 4]
            self.assertEqual(entry[0], 255)  # alpha/reserved byte

    def test_install_wires_palette_and_strip_into_native_modules(self):
        display = FakeDisplay()
        sprites = FakeSprites()

        strip_number = logo_strip.install(display, sprites, strip_number=3)

        self.assertEqual(strip_number, 3)
        self.assertEqual(display.palette, logo_strip.PALETTE)
        self.assertEqual(sprites.stripes[3], logo_strip.STRIP)


if __name__ == "__main__":
    unittest.main()
