import os
import sys
import uctypes
try:
    import utime as _time
except ImportError:
    import time as _time

from ventilastation.runtime import FileStorage, MemoryStorage


def _ticks_us():
    ticks_us = getattr(_time, "ticks_us", None)
    if ticks_us is not None:
        return ticks_us()
    perf_counter = getattr(_time, "perf_counter", None)
    if perf_counter is not None:
        return int(perf_counter() * 1000000)
    return 0


def _ticks_diff_us(end, start):
    ticks_diff = getattr(_time, "ticks_diff", None)
    if ticks_diff is not None:
        return ticks_diff(end, start)
    return end - start


class NullComms:
    def __init__(self):
        self.sent = []
        self.incoming = bytearray()

    def receive(self, bufsize):
        if not self.incoming:
            return None
        data = bytes(self.incoming[:bufsize])
        del self.incoming[:bufsize]
        return data

    def send(self, line, data=b""):
        self.sent.append((line, data))

    def push_input(self, data):
        self.incoming.extend(data)


class NullDisplay:
    def __init__(self):
        self.column_offset = 0
        self.palette = b""
        self.stripes = {}

    def init(self, num_pixels, *hw_config):
        self.num_pixels = num_pixels
        self.hw_config = hw_config

    def set_gamma_mode(self, _mode):
        return None

    def set_column_offset(self, offset):
        self.column_offset = offset % 256

    def get_column_offset(self):
        return self.column_offset

    def set_palettes(self, palette):
        self.palette = palette

    def getaddress(self, _sprite_num):
        return 0

    def set_imagestrip(self, number, stripmap):
        self.stripes[number] = stripmap

    def update(self):
        return None

    def last_turn_duration(self):
        return 0


class HeadlessSprite:
    backend = None

    def __init__(self, replacing=None):
        if replacing is not None:
            state = replacing._state
        else:
            state = self.backend.new_state()
        self._state = state
        self.selected_frame = 0

    def disable(self):
        self._state["frame"] = 255

    def x(self):
        return self._state["x"]

    def set_x(self, value):
        self._state["x"] = value

    def y(self):
        return self._state["y"]

    def set_y(self, value):
        self._state["y"] = value

    def width(self):
        strip = self.backend.stripes.get(self._state["image_strip"])
        if strip is None:
            return 0
        if isinstance(strip, dict):
            return strip["width"]
        return strip[0]

    def height(self):
        strip = self.backend.stripes.get(self._state["image_strip"])
        if strip is None:
            return 0
        if isinstance(strip, dict):
            return strip["height"]
        return strip[1]

    def set_strip(self, strip_number):
        self._state["image_strip"] = strip_number

    def frame(self):
        return self._state["frame"]

    def set_frame(self, value):
        self._state["frame"] = value

    def set_perspective(self, value):
        self._state["perspective"] = value

    def perspective(self):
        return self._state["perspective"]

    def collision(self, targets):
        def intersects(x1, w1, x2, w2):
            delta = min(x1, x2)
            x1 = (x1 - delta + 128) % 256
            x2 = (x2 - delta + 128) % 256
            return x1 < x2 + w2 and x1 + w1 > x2

        for target in targets:
            other = target
            if (intersects(self.x(), self.width(), other.x(), other.width()) and
                intersects(self.y(), self.height(), other.y(), other.height())):
                return target
        return None


class HeadlessSprites:
    def __init__(self):
        HeadlessSprite.backend = self
        self.Sprite = HeadlessSprite
        self.stripes = {}
        self._sprites = []

    def new_state(self):
        state = {
            "slot": len(self._sprites) + 1,
            "x": 0,
            "y": 0,
            "image_strip": 0,
            "frame": 255,
            "perspective": 1,
        }
        self._sprites.append(state)
        return state

    def reset_sprites(self):
        self._sprites = []

    def set_imagestrip(self, number, stripmap):
        self.stripes[number] = stripmap[0:4]


class BrowserStorage(MemoryStorage):
    def export_state(self):
        exported = {}
        for filename, content in self.files.items():
            exported[filename] = dict(content)
        return exported

    def import_state(self, files):
        self.files = {}
        for filename, content in files.items():
            self.files[filename] = dict(content)


class BrowserComms:
    def __init__(self):
        self.buttons = 0
        self.input_updates = []
        self.input_sequence = 0
        self.events = []
        self.worker_host = None

    def receive(self, _bufsize):
        if self.worker_host is not None:
            try:
                self.set_buttons(self.worker_host.get_buttons())
            except Exception:
                pass
        return bytes((self.buttons,))

    def send(self, line, data=b""):
        if isinstance(line, str):
            line = line.encode("utf-8")
        line = bytes(line)
        parts = line.split()
        command = parts[0].decode("utf-8") if parts else ""
        args = [p.decode("utf-8") for p in parts[1:]]
        payload = bytes(data) if data else b""

        event = {
            "command": command,
            "args": args,
        }
        if payload:
            event["data"] = payload
        if self.worker_host is not None:
            try:
                self.worker_host.post_command(line.decode("utf-8"), payload)
                return
            except Exception:
                pass
        self.events.append(event)

    def set_buttons(self, buttons):
        normalized = buttons & 0xFF
        if normalized == self.buttons:
            return
        self.buttons = normalized
        self.input_sequence += 1
        self.input_updates.append({
            "sequence": self.input_sequence,
            "buttons": self.buttons,
        })

    def set_worker_host(self, worker_host):
        self.worker_host = worker_host

    def drain_input_updates(self):
        updates = self.input_updates
        self.input_updates = []
        return updates

    def drain_events(self):
        events = self.events
        self.events = []
        return events


class BrowserDisplay(NullDisplay):
    def __init__(self, comms):
        super().__init__()
        self.comms = comms
        self.worker_host = None
        self.gamma_mode = 1
        self.frame = 0
        self.sprite_data = bytearray(b"\0\0\0\xff\xff" * 100)
        self.palette_version = 0
        self.palette_dirty = False
        self.asset_data = {}
        self.assets = {}
        self.dirty_asset_slots = set()
        self._profile_totals = {
            "sampleCount": 0,
            "displayExportUs": 0,
            "displayExportUsMax": 0,
            "paletteAttachUs": 0,
            "paletteAttachUsMax": 0,
            "assetsAssembleUs": 0,
            "assetsAssembleUsMax": 0,
            "eventsDrainUs": 0,
            "eventsDrainUsMax": 0,
            "spritesDecodeUs": 0,
            "spritesDecodeUsMax": 0,
        }
        self._frame_export = {
            "frame": 0,
            "buttons": 0,
            "column_offset": 0,
            "gamma_mode": 1,
            "palette_length": 0,
            "palette_version": 0,
            "palette_dirty": False,
            "palette": None,
            "assets": [],
            "events": [],
            "sprites": [],
            "python_profile": None,
        }

    def set_worker_host(self, worker_host):
        self.worker_host = worker_host

    def _post_command(self, line, data=b""):
        if self.worker_host is None:
            return False
        try:
            self.worker_host.post_command(line, data)
            return True
        except Exception:
            return False

    def set_gamma_mode(self, mode):
        self.gamma_mode = mode

    def set_palettes(self, palette):
        palette = bytes(palette)
        if palette == self.palette:
            return
        self.palette = palette
        self.palette_version += 1
        self.palette_dirty = True
        self._post_command("palette %d %d" % (len(palette), self.palette_version), palette)

    def getaddress(self, sprite_num):
        return uctypes.addressof(self.sprite_data) + sprite_num * 5

    def set_imagestrip(self, number, stripmap):
        stripmap = bytes(stripmap)
        if self.asset_data.get(number) == stripmap:
            return
        asset = self._decode_imagestrip(number, stripmap)
        if asset is None:
            return
        self.asset_data[number] = stripmap
        self.assets[number] = asset
        self.dirty_asset_slots.add(number)
        self._post_command("imagestrip %d %d" % (number, len(stripmap)), stripmap)

    def update(self):
        self.frame += 1
        if self.worker_host is None:
            return
        full = bool(self.worker_host.consume_full_frame_request())
        if full and self.palette:
            self._post_command("palette %d %d" % (len(self.palette), self.palette_version), self.palette)
        asset_slots = sorted(self.assets) if full else sorted(self.dirty_asset_slots)
        for slot in asset_slots:
            stripmap = self.asset_data.get(slot)
            if stripmap is not None:
                self._post_command("imagestrip %d %d" % (slot, len(stripmap)), stripmap)
        self._post_command("sprites", bytes(self.sprite_data))
        self._post_command(
            "frame %d %d %d %d %d %d %d" % (
                self.frame,
                self.comms.buttons,
                self.gamma_mode,
                self.column_offset,
                len(self.palette),
                self.palette_version,
                1 if (full or self.palette_dirty) else 0,
            )
        )
        self.palette_dirty = False
        self.dirty_asset_slots = set()

    def _decode_imagestrip(self, slot, stripmap):
        if len(stripmap) < 4:
            return None
        width = stripmap[0]
        if width == 255:
            width = 256
        return {
            "slot": slot,
            "width": width,
            "height": stripmap[1],
            "frames": stripmap[2] or 1,
            "palette": stripmap[3] or 0,
            "data": stripmap[4:],
        }

    def _decode_sprites(self):
        sprites = []
        sprite_data = self.sprite_data
        for offset in range(0, len(sprite_data), 5):
            frame = sprite_data[offset + 3]
            if frame == 255:
                continue
            perspective = sprite_data[offset + 4]
            if perspective >= 128:
                perspective -= 256
            sprites.append({
                "slot": offset // 5,
                "x": sprite_data[offset],
                "y": sprite_data[offset + 1],
                "image_strip": sprite_data[offset + 2],
                "frame": frame,
                "perspective": perspective,
            })
        return sprites

    def export_frame(self, full=False):
        started_at = _ticks_us()
        exported = self._frame_export
        palette_started_at = _ticks_us()
        exported["frame"] = self.frame
        exported["buttons"] = self.comms.buttons
        exported["column_offset"] = self.column_offset
        exported["gamma_mode"] = self.gamma_mode
        exported["palette_length"] = len(self.palette)
        exported["palette_version"] = self.palette_version
        exported["palette_dirty"] = full or self.palette_dirty
        exported["palette"] = self.palette if (full or self.palette_dirty) else None
        after_palette_at = _ticks_us()
        assets_started_at = after_palette_at
        if full:
            asset_slots = sorted(self.assets)
        else:
            asset_slots = sorted(self.dirty_asset_slots)
        exported["assets"] = [self.assets[slot] for slot in asset_slots if slot in self.assets]
        after_assets_at = _ticks_us()
        exported["events"] = self.comms.drain_events()
        after_events_at = _ticks_us()
        exported["sprites"] = self._decode_sprites()
        finished_at = _ticks_us()
        display_export_us = _ticks_diff_us(finished_at, started_at)
        palette_attach_us = _ticks_diff_us(after_palette_at, palette_started_at)
        assets_assemble_us = _ticks_diff_us(after_assets_at, assets_started_at)
        events_drain_us = _ticks_diff_us(after_events_at, after_assets_at)
        sprites_decode_us = _ticks_diff_us(finished_at, after_events_at)
        profile = self._profile_totals
        profile["sampleCount"] += 1
        profile["displayExportUs"] += display_export_us
        profile["paletteAttachUs"] += palette_attach_us
        profile["assetsAssembleUs"] += assets_assemble_us
        profile["eventsDrainUs"] += events_drain_us
        profile["spritesDecodeUs"] += sprites_decode_us
        if display_export_us > profile["displayExportUsMax"]:
            profile["displayExportUsMax"] = display_export_us
        if palette_attach_us > profile["paletteAttachUsMax"]:
            profile["paletteAttachUsMax"] = palette_attach_us
        if assets_assemble_us > profile["assetsAssembleUsMax"]:
            profile["assetsAssembleUsMax"] = assets_assemble_us
        if events_drain_us > profile["eventsDrainUsMax"]:
            profile["eventsDrainUsMax"] = events_drain_us
        if sprites_decode_us > profile["spritesDecodeUsMax"]:
            profile["spritesDecodeUsMax"] = sprites_decode_us
        sample_count = profile["sampleCount"] or 1
        exported["python_profile"] = {
            "displayExportMs": profile["displayExportUs"] / sample_count / 1000.0,
            "displayExportMsMax": profile["displayExportUsMax"] / 1000.0,
            "paletteAttachMs": profile["paletteAttachUs"] / sample_count / 1000.0,
            "paletteAttachMsMax": profile["paletteAttachUsMax"] / 1000.0,
            "assetsAssembleMs": profile["assetsAssembleUs"] / sample_count / 1000.0,
            "assetsAssembleMsMax": profile["assetsAssembleUsMax"] / 1000.0,
            "eventsDrainMs": profile["eventsDrainUs"] / sample_count / 1000.0,
            "eventsDrainMsMax": profile["eventsDrainUsMax"] / 1000.0,
            "spritesDecodeMs": profile["spritesDecodeUs"] / sample_count / 1000.0,
            "spritesDecodeMsMax": profile["spritesDecodeUsMax"] / 1000.0,
            "sampleCount": sample_count,
            "assetCount": len(exported["assets"]),
            "spriteCount": len(exported["sprites"]),
            "full": bool(full),
        }
        self.palette_dirty = False
        self.dirty_asset_slots = set()
        return exported


class Platform:
    def __init__(self, name, comms, display, sprites_backend, storage, hw_config=None, pixels=54):
        self.name = name
        self.comms = comms
        self.display = display
        self.sprites = sprites_backend
        self.storage = storage
        self.hw_config = hw_config or ()
        self.pixels = pixels
        self.disable_gc = name == "hardware"

    def initialize(self, settings_module):
        settings_module.load()
        self.display.init(self.pixels, *self.hw_config)
        self.display.set_gamma_mode(1)
        self.display.set_column_offset(settings_module.get("pov_column_offset", 0))

    def set_worker_host(self, worker_host):
        if hasattr(self.comms, "set_worker_host"):
            self.comms.set_worker_host(worker_host)
        if hasattr(self.display, "set_worker_host"):
            self.display.set_worker_host(worker_host)


class LazyModule:
    def __init__(self, module_name):
        self.module_name = module_name
        self._module = None

    def _load(self):
        if self._module is None:
            self._module = __import__(self.module_name, None, None, ["*"])
        return self._module

    def __getattr__(self, name):
        return getattr(self._load(), name)


def _load_attr(module_name, attr_name=None):
    if attr_name is None:
        return __import__(module_name, None, None, ["*"])
    module = __import__(module_name, None, None, [attr_name])
    return getattr(module, attr_name)


def _detect_desktop_comms_module():
    if sys.platform == "win32":
        return LazyModule("ventilastation.wincomms")
    return LazyModule("ventilastation.comms")


def create_desktop_platform():
    return Platform(
        name="desktop",
        comms=_detect_desktop_comms_module(),
        display=LazyModule("ventilastation.remotepov"),
        sprites_backend=LazyModule("ventilastation.emu_sprites"),
        storage=FileStorage(),
    )


def create_hardware_platform():
    hw_config = _load_attr("ventilastation.hw_config")
    return Platform(
        name="hardware",
        comms=LazyModule("ventilastation.serialcomms"),
        display=LazyModule("vshw_povdisplay"),
        sprites_backend=LazyModule("vshw_sprites"),
        storage=FileStorage(),
        hw_config=(
            hw_config.hall_gpio,
            hw_config.irdiode_gpio,
            hw_config.led_clk,
            hw_config.led_mosi,
            hw_config.led_freq,
        ),
    )


def create_headless_platform():
    return Platform(
        name="headless",
        comms=NullComms(),
        display=NullDisplay(),
        sprites_backend=HeadlessSprites(),
        storage=MemoryStorage(),
    )


def create_browser_platform():
    comms = BrowserComms()
    sprites_backend = LazyModule("ventilastation.emu_sprites")
    display = BrowserDisplay(comms)
    return Platform(
        name="browser",
        comms=comms,
        display=display,
        sprites_backend=sprites_backend,
        storage=BrowserStorage(),
    )


def resolve_platform_name(platform_name=None, argv=None, environ=None):
    if platform_name:
        return platform_name

    raw_argv = argv if argv is not None else getattr(sys, "argv", ())
    argv = raw_argv[1:] if raw_argv else ()
    environ = environ if environ is not None else getattr(os, "environ", {})

    for arg in argv:
        if arg.startswith("--platform="):
            return arg.split("=", 1)[1]

    env_name = environ.get("VSDK_PLATFORM")
    if env_name:
        return env_name

    return "hardware" if sys.platform == "rp2" else "desktop"


def create_platform(platform_name=None, argv=None, environ=None):
    name = resolve_platform_name(platform_name, argv, environ)
    if name == "desktop":
        return create_desktop_platform()
    if name == "hardware":
        return create_hardware_platform()
    if name == "headless":
        return create_headless_platform()
    if name == "browser":
        return create_browser_platform()
    raise ValueError("Unknown platform: %s" % name)
