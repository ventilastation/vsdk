"""Headless platform: no I/O at all, for tests and scripted runs.

The comms/display/sprites backends record what the game did instead of
rendering it, so director and scene logic can be exercised without a
display, a socket, or hardware.
"""

from ventilastation.platforms.base import Platform
from ventilastation.runtime import MemoryStorage


class NullComms:
    def __init__(self):
        self.sent = []
        self.incoming = bytearray()

    def receive(self, bufsize):
        if not self.incoming:
            return None
        # (no `del ba[:n]`: MicroPython bytearrays lack slice deletion)
        data = bytes(self.incoming[:bufsize])
        self.incoming = self.incoming[bufsize:]
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


def create_headless_platform():
    return Platform(
        name="headless",
        comms=NullComms(),
        display=NullDisplay(),
        sprites_backend=HeadlessSprites(),
        storage=MemoryStorage(),
    )
