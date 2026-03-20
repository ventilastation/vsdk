import os
import sys
import uctypes

from ventilastation.runtime import FileStorage, MemoryStorage


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

    def receive(self, _bufsize):
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
        self.events.append(event)

    def set_buttons(self, buttons):
        self.buttons = buttons & 0xFF
        self.input_sequence += 1
        self.input_updates.append({
            "sequence": self.input_sequence,
            "buttons": self.buttons,
        })

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
        self.gamma_mode = 1
        self.frame = 0
        self.sprite_data = bytearray(b"\0\0\0\xff\xff" * 100)
        self._frame_export = {
            "frame": 0,
            "buttons": 0,
            "column_offset": 0,
            "gamma_mode": 1,
            "assets": [],
            "events": [],
        }

    def set_gamma_mode(self, mode):
        self.gamma_mode = mode

    def set_palettes(self, palette):
        palette = bytes(palette)
        self.comms.send(b"palette %d" % (len(palette) // 1024), palette)

    def getaddress(self, sprite_num):
        return uctypes.addressof(self.sprite_data) + sprite_num * 5

    def set_imagestrip(self, number, stripmap):
        self.comms.send(b"imagestrip %d %d" % (number, len(stripmap)), stripmap)

    def update(self):
        self.frame += 1
        self.comms.send(b"sprites", self.sprite_data)

    def export_frame(self, full=False):
        exported = self._frame_export
        exported["frame"] = self.frame
        exported["buttons"] = self.comms.buttons
        exported["column_offset"] = self.column_offset
        exported["gamma_mode"] = self.gamma_mode
        exported["events"] = self.comms.drain_events()
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
