import os
import sys

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
    def __init__(self, sprites_backend, comms):
        super().__init__()
        self.sprites_backend = sprites_backend
        self.comms = comms
        self.gamma_mode = 1
        self.frame = 0
        self.palette_dirty = False

    def set_gamma_mode(self, mode):
        self.gamma_mode = mode

    def set_palettes(self, palette):
        self.palette = bytes(palette)
        self.palette_dirty = True

    def update(self):
        self.frame += 1

    def export_frame(self, full=False):
        exported = {
            "frame": self.frame,
            "buttons": self.comms.buttons,
            "column_offset": self.column_offset,
            "gamma_mode": self.gamma_mode,
            "sprites": self.sprites_backend.export_sprites(),
            "assets": self.sprites_backend.export_assets(full=full),
            "events": self.comms.drain_events(),
        }
        if full or self.palette_dirty:
            exported["palette"] = self.palette
        self.palette_dirty = False
        return exported


class BrowserSprites(HeadlessSprites):
    def __init__(self):
        super().__init__()
        self._dirty_strips = set()

    def set_imagestrip(self, number, stripmap):
        width = stripmap[0]
        height = stripmap[1]
        frames = stripmap[2]
        palette = stripmap[3]
        if width == 255:
            width = 256
        self.stripes[number] = {
            "width": width,
            "height": height,
            "frames": frames,
            "palette": palette,
            "data": bytes(stripmap[4:]),
        }
        self._dirty_strips.add(number)

    def export_assets(self, full=False):
        if full:
            strip_numbers = sorted(self.stripes.keys())
        else:
            strip_numbers = sorted(self._dirty_strips)

        assets = []
        for number in strip_numbers:
            strip = self.stripes[number]
            exported = {
                "slot": number,
                "width": strip["width"],
                "height": strip["height"],
                "frames": strip["frames"],
                "palette": strip["palette"],
                "data": strip["data"],
            }
            assets.append(exported)

        if not full:
            self._dirty_strips.clear()
        return assets

    def export_sprites(self):
        exported = []
        for state in self._sprites:
            if state["frame"] == 255:
                continue
            exported.append({
                "slot": state["slot"],
                "x": state["x"],
                "y": state["y"],
                "image_strip": state["image_strip"],
                "frame": state["frame"],
                "perspective": state["perspective"],
            })
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
    sprites_backend = BrowserSprites()
    display = BrowserDisplay(sprites_backend, comms)
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
