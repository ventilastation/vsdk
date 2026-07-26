import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))

_MODULE_NAMES = ("esp32", "vshw_povdisplay", "vshw_sprites", "vshw_vs2", "vsdk_ota_rings")

_VS2_FLAG_VISIBLE = 0x01


class FakeDisplay:
    def __init__(self):
        self.palette = None
        self.inited_with = None
        self.gamma_mode = None
        self.starfield_enabled = None  # None until explicitly set, unlike the real default (True)

    def init(self, pixels, *hw_config):
        self.inited_with = (pixels, hw_config)

    def set_gamma_mode(self, mode):
        self.gamma_mode = mode

    def set_palettes(self, palette):
        self.palette = palette

    def set_starfield_enabled(self, enabled):
        self.starfield_enabled = bool(enabled)


class FakeSprite:
    """Stands in for a vshw_vs2.Sprite: starts invisible (flags=0) and only
    set_flags(_VS2_FLAG_VISIBLE) makes it show, matching vs2_native.c's
    vs2_sprite_make_new() default -- unlike the legacy vshw_sprites.Sprite,
    set_frame() alone doesn't make it visible."""

    def __init__(self):
        self.strip = None
        self.perspective = None
        self.x = None
        self.y = None
        self.frame = None
        self.flags = 0
        self.disabled = True

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

    def set_flags(self, value):
        self.flags = value
        self.disabled = (value & _VS2_FLAG_VISIBLE) == 0

    def disable(self):
        self.flags &= ~_VS2_FLAG_VISIBLE
        self.disabled = True


class FakeSprites:
    """vshw_sprites: only set_imagestrip() is used by vsdk_ota_rings.py --
    image_stripes[] is shared with vshw_vs2, so strip data still registers
    through here even though sprite objects come from vshw_vs2 now."""

    def __init__(self):
        self.stripes = {}

    def set_imagestrip(self, number, stripmap):
        self.stripes[number] = stripmap


class FakeVs2:
    def __init__(self):
        self.created = []
        self.active = None

    def set_active(self, value):
        self.active = bool(value)

    def Sprite(self):
        sprite = FakeSprite()
        self.created.append(sprite)
        return sprite


def _install_fakes(nvs_values=None):
    if nvs_values is None:
        nvs_values = {
            "hall_gpio": 7, "irdiode_gpio": 7, "led_spi_host": 2,
            "led_clk": 12, "led_mosi": 13, "led_cs": 14, "led_freq": 20000000,
        }

    esp32 = types.ModuleType("esp32")

    class FakeNVS:
        def __init__(self, namespace):
            self.namespace = namespace

        def get_i32(self, key):
            if self.namespace != "vs_board" or key not in nvs_values:
                raise OSError("no such key")
            return nvs_values[key]

    esp32.NVS = FakeNVS
    sys.modules["esp32"] = esp32

    display = FakeDisplay()
    sprites = FakeSprites()
    vs2 = FakeVs2()

    povdisplay_module = types.ModuleType("vshw_povdisplay")
    povdisplay_module.init = display.init
    povdisplay_module.set_gamma_mode = display.set_gamma_mode
    povdisplay_module.set_palettes = display.set_palettes
    povdisplay_module.set_starfield_enabled = display.set_starfield_enabled
    sys.modules["vshw_povdisplay"] = povdisplay_module

    sprites_module = types.ModuleType("vshw_sprites")
    sprites_module.set_imagestrip = sprites.set_imagestrip
    sys.modules["vshw_sprites"] = sprites_module

    vs2_module = types.ModuleType("vshw_vs2")
    vs2_module.set_active = vs2.set_active
    vs2_module.Sprite = vs2.Sprite
    sys.modules["vshw_vs2"] = vs2_module

    return esp32, display, sprites, vs2


class NativeUnavailableTests(unittest.TestCase):
    """Without vshw_povdisplay/vshw_sprites/vshw_vs2 (desktop/emulator),
    every public call must be a silent no-op -- this is what lets
    updater.py call these unconditionally regardless of platform."""

    def setUp(self):
        for name in _MODULE_NAMES:
            sys.modules.pop(name, None)

    def test_ensure_started_returns_false_and_every_call_is_a_noop(self):
        import vsdk_ota_rings as rings

        self.assertFalse(rings.ensure_started())
        # None of these may raise.
        rings.show_wifi_connecting()
        rings.hide_wifi()
        rings.set_file_progress(1, 2)
        rings.pulse_file_activity()
        rings.set_partition_progress(1, 2)
        rings.pulse_partition_activity()
        rings.clear()


class StartupTests(unittest.TestCase):
    def setUp(self):
        for name in _MODULE_NAMES:
            sys.modules.pop(name, None)

    def tearDown(self):
        for name in _MODULE_NAMES[:-1]:
            sys.modules.pop(name, None)

    def test_ensure_started_inits_display_and_creates_one_sprite_per_ring(self):
        _esp32, display, _sprites, vs2 = _install_fakes()
        import vsdk_ota_rings as rings

        self.assertTrue(rings.ensure_started())
        self.assertEqual(display.inited_with, (rings.PIXELS, (7, 7, 2, 12, 13, 14, 20000000)))
        self.assertEqual(display.gamma_mode, 1)
        self.assertIs(display.starfield_enabled, False)
        self.assertIs(vs2.active, True)
        self.assertEqual(len(vs2.created), len(rings._Z_ORDER))
        # All start disabled -- nothing shows until a phase actually begins.
        self.assertTrue(all(s.disabled for s in vs2.created))

    def test_ensure_started_is_idempotent(self):
        _esp32, _display, _sprites, vs2 = _install_fakes()
        import vsdk_ota_rings as rings

        self.assertTrue(rings.ensure_started())
        self.assertTrue(rings.ensure_started())
        self.assertEqual(len(vs2.created), len(rings._Z_ORDER))

    def test_ensure_started_returns_false_when_board_not_provisioned(self):
        _install_fakes(nvs_values={})
        import vsdk_ota_rings as rings

        self.assertFalse(rings.ensure_started())

    def test_white_file_progress_ring_created_first_for_top_precedence(self):
        # render()/render_vs2()'s sprite loop draws high-id sprites first,
        # low-id last (on top) -- see gpu.c. The first-created sprite gets
        # the lowest id, so it must be _FILE_PROGRESS (white) per the
        # user's requirement that white always wins a same-LED conflict.
        import vsdk_ota_rings as rings

        self.assertEqual(rings._Z_ORDER[0], rings._FILE_PROGRESS)


class RingPositionTests(unittest.TestCase):
    def setUp(self):
        for name in _MODULE_NAMES:
            sys.modules.pop(name, None)
        _esp32, display, sprites, vs2 = _install_fakes()
        self.display = display
        self.sprites = sprites
        self.vs2 = vs2
        import vsdk_ota_rings as rings
        self.rings = rings

    def tearDown(self):
        for name in _MODULE_NAMES[:-1]:
            sys.modules.pop(name, None)

    def test_row_for_fraction_maps_0pct_to_outermost_row_0(self):
        self.assertEqual(self.rings._row_for_fraction(0, 100), 0)

    def test_row_for_fraction_maps_near_100pct_close_to_innermost(self):
        row = self.rings._row_for_fraction(99, 100)
        self.assertEqual(row, int(0.99 * (self.rings.PIXELS - 1)))

    def test_row_for_fraction_clamps_and_handles_zero_total(self):
        self.assertEqual(self.rings._row_for_fraction(0, 0), 0)
        self.assertEqual(self.rings._row_for_fraction(150, 100), self.rings.PIXELS - 1)
        self.assertEqual(self.rings._row_for_fraction(-5, 100), 0)

    def test_set_file_progress_positions_and_shows_the_white_ring(self):
        self.rings.ensure_started()
        self.rings.set_file_progress(50, 100)
        sprite = self.rings._sprite[self.rings._FILE_PROGRESS]
        self.assertFalse(sprite.disabled)
        self.assertEqual(sprite.frame, 0)  # always frame 0 -- position lives in the re-registered strip

    def test_show_wifi_connecting_lights_only_the_outermost_led(self):
        self.rings.ensure_started()
        self.rings.show_wifi_connecting()

        slot = self.rings._STRIP_SLOT[self.rings._WIFI]
        strip = self.sprites.stripes[slot]
        body = strip[4:]
        for col in range(self.rings.WIDTH):
            self.assertEqual(body[col * self.rings.PIXELS + 0], self.rings._LIT)
            for row in range(1, self.rings.PIXELS):
                self.assertEqual(body[col * self.rings.PIXELS + row], self.rings.TRANSPARENT)

    def test_hide_wifi_disables_the_ring(self):
        self.rings.ensure_started()
        self.rings.show_wifi_connecting()
        self.rings.hide_wifi()
        sprite = self.rings._sprite[self.rings._WIFI]
        self.assertTrue(sprite.disabled)

    def test_clear_disables_every_ring_and_restores_the_starfield(self):
        self.rings.ensure_started()
        self.rings.show_wifi_connecting()
        self.rings.set_file_progress(10, 100)
        self.assertIs(self.display.starfield_enabled, False)

        self.rings.clear()

        self.assertTrue(all(s.disabled for s in self.vs2.created))
        self.assertIs(self.display.starfield_enabled, True)


class ActivityBounceTests(unittest.TestCase):
    def setUp(self):
        for name in _MODULE_NAMES:
            sys.modules.pop(name, None)
        _install_fakes()
        import vsdk_ota_rings as rings
        self.rings = rings
        self.rings.ensure_started()

    def tearDown(self):
        for name in _MODULE_NAMES[:-1]:
            sys.modules.pop(name, None)

    def test_pulses_advance_one_row_per_call(self):
        self.rings.pulse_partition_activity()
        first = self.rings._activity_pos[self.rings._PARTITION_ACTIVITY]
        self.rings.pulse_partition_activity()
        second = self.rings._activity_pos[self.rings._PARTITION_ACTIVITY]
        self.assertEqual(second, first + 1)

    def test_bounces_off_the_innermost_end(self):
        for _ in range(self.rings.PIXELS - 1):  # exactly enough to reach the inner end from 0
            self.rings.pulse_partition_activity()
        self.assertEqual(self.rings._activity_pos[self.rings._PARTITION_ACTIVITY], self.rings.PIXELS - 1)
        # One more pulse must now move back outward, not clamp or overshoot.
        self.rings.pulse_partition_activity()
        self.assertEqual(self.rings._activity_pos[self.rings._PARTITION_ACTIVITY], self.rings.PIXELS - 2)

    def test_file_and_partition_activity_bounce_independently(self):
        self.rings.pulse_partition_activity()
        self.rings.pulse_partition_activity()
        self.rings.pulse_file_activity()
        self.assertEqual(self.rings._activity_pos[self.rings._PARTITION_ACTIVITY], 2)
        self.assertEqual(self.rings._activity_pos[self.rings._FILE_ACTIVITY], 1)


class StripBytesTests(unittest.TestCase):
    def setUp(self):
        sys.modules.pop("vsdk_ota_rings", None)
        import vsdk_ota_rings as rings
        self.rings = rings

    def test_header_encodes_full_width_and_pixel_height_and_one_frame(self):
        strip = self.rings._build_ring_strip(self.rings._WIFI, 5)
        header = strip[:4]
        self.assertEqual(header[0], 255)  # width byte: "actually 256"
        self.assertEqual(header[1], self.rings.PIXELS)
        self.assertEqual(header[2], 1)  # one frame -- position is baked into the data, not selected via frame index
        self.assertEqual(header[3], self.rings._PALETTE_GROUP[self.rings._WIFI])

    def test_every_column_has_exactly_the_target_row_lit(self):
        row = 12
        strip = self.rings._build_ring_strip(self.rings._FILE_PROGRESS, row)
        body = strip[4:]
        for col in range(self.rings.WIDTH):
            for r in range(self.rings.PIXELS):
                value = body[col * self.rings.PIXELS + r]
                if r == row:
                    self.assertEqual(value, self.rings._LIT)
                else:
                    self.assertEqual(value, self.rings.TRANSPARENT)

    def test_none_row_is_fully_transparent(self):
        strip = self.rings._build_ring_strip(self.rings._WIFI, None)
        body = strip[4:]
        self.assertTrue(all(b == self.rings.TRANSPARENT for b in body))

    def test_palette_has_one_group_per_ring_with_color_at_lit_index(self):
        palette = self.rings._build_palette()
        self.assertEqual(len(palette), 256 * 4 * len(self.rings._Z_ORDER))
        for name in self.rings._Z_ORDER:
            group = self.rings._PALETTE_GROUP[name]
            offset = group * 256 * 4 + self.rings._LIT * 4
            b, g, r = self.rings._RING_COLOR[name]
            self.assertEqual(palette[offset:offset + 4], bytes([255, b, g, r]))


if __name__ == "__main__":
    unittest.main()
