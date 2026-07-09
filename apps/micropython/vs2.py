"""Ventilastation API v2.

This module is the game-facing entry point for the next display API. The first
implementation is backed by the existing sprite table so games can start
porting before the v2 renderer lands.
"""

import struct

from ventilastation import api_guard
from ventilastation.director import director, stripes
from ventilastation.scene import Scene as _Scene
from ventilastation.runtime import get_platform

def _claim():
    api_guard.claim("vs2", "vs2")


_claim()

FULLSCREEN = 0
TUNNEL = 1
HUD = 2

TRANSPARENT = 255

PAYLOAD_MAGIC = b"VS2\0"
PAYLOAD_VERSION = 1
PAYLOAD_HEADER_SIZE = 16
PAYLOAD_LAYER_SIZE = 8
PAYLOAD_SPRITE_SIZE = 24

FLAG_VISIBLE = 0x01
FLAG_FLIP_X = 0x02
FLAG_FLIP_Y = 0x04

_live_sprites = []
_active_scene = None
_next_sprite_order = 0


def _render_coord(value, minimum=0, maximum=255):
    try:
        ivalue = int(value)
    except TypeError:
        ivalue = 0
    if ivalue < minimum:
        return minimum
    if ivalue > maximum:
        return maximum
    return ivalue


def _resolve_strip(strip):
    if isinstance(strip, str):
        return stripes[strip]
    return strip


def _fixed_8_8(value):
    try:
        fixed = int(value * 256)
    except TypeError:
        fixed = 0
    if fixed < -0x80000000:
        return -0x80000000
    if fixed > 0x7FFFFFFF:
        return 0x7FFFFFFF
    return fixed


def _strip_number(sprite):
    if sprite._strip is None:
        return 0
    return _render_coord(sprite._strip, 0, 255)


def _sprite_flags(sprite):
    flags = 0
    if sprite.visible:
        flags |= FLAG_VISIBLE
    if sprite.flip_x:
        flags |= FLAG_FLIP_X
    if sprite.flip_y:
        flags |= FLAG_FLIP_Y
    return flags


def _sprite_order(sprite):
    return getattr(sprite, "_vs2_order", 0)


def _register_sprite(sprite):
    global _next_sprite_order
    if sprite not in _live_sprites:
        sprite._vs2_order = _next_sprite_order
        _next_sprite_order += 1
        _live_sprites.append(sprite)


def _scene_sprites(scene):
    sprites = []
    seen = set()
    if scene is not None:
        for layer in getattr(scene, "layers", ()):
            for sprite in layer.sprites:
                if id(sprite) not in seen:
                    seen.add(id(sprite))
                    sprites.append(sprite)
    for sprite in _live_sprites:
        if scene is not None and getattr(sprite, "_scene", None) is not scene:
            continue
        if id(sprite) not in seen:
            seen.add(id(sprite))
            sprites.append(sprite)
    sprites.sort(key=_sprite_order)
    return sprites


def export_scene_payload(scene=None):
    _claim()
    layers = []
    if scene is not None:
        layers = list(getattr(scene, "layers", ()))
    if not layers:
        layers = [Layer(name="default", mode=TUNNEL, visible=True)]
    layer_index = {}
    for index, layer in enumerate(layers):
        layer_index[id(layer)] = index

    sprites = _scene_sprites(scene)
    payload = bytearray(
        PAYLOAD_HEADER_SIZE
        + len(layers) * PAYLOAD_LAYER_SIZE
        + len(sprites) * PAYLOAD_SPRITE_SIZE
    )
    struct.pack_into(
        "<4sBBBBHHHH",
        payload,
        0,
        PAYLOAD_MAGIC,
        PAYLOAD_VERSION,
        len(layers),
        len(sprites),
        0,
        PAYLOAD_HEADER_SIZE,
        PAYLOAD_LAYER_SIZE,
        PAYLOAD_SPRITE_SIZE,
        0,
    )
    offset = PAYLOAD_HEADER_SIZE
    for index, layer in enumerate(layers):
        flags = FLAG_VISIBLE if layer.visible else 0
        struct.pack_into(
            "<BBBBBBBB",
            payload,
            offset,
            index,
            _render_coord(layer.mode, 0, 2),
            flags,
            0, 0, 0, 0, 0,
        )
        offset += PAYLOAD_LAYER_SIZE
    for sprite in sprites:
        layer = getattr(sprite, "layer", None)
        index = layer_index.get(id(layer), 0)
        mode = sprite.mode if layer is None else layer.mode
        struct.pack_into(
            "<BBBBBBhhii",
            payload,
            offset,
            index,
            _strip_number(sprite),
            _render_coord(sprite.frame, 0, 254),
            _render_coord(mode, 0, 2),
            _sprite_flags(sprite),
            0,
            0,
            0,
            _fixed_8_8(sprite.x),
            _fixed_8_8(sprite.y),
        )
        offset += PAYLOAD_SPRITE_SIZE
    return payload


def reset_sprites():
    _claim()
    return get_platform().sprites.reset_sprites()


def set_starfield(enabled):
    _claim()
    display = get_platform().display
    setter = getattr(display, "set_starfield", None)
    if setter is not None:
        return setter(bool(enabled))
    display.starfield_enabled = bool(enabled)
    return None


class Scene(_Scene):
    def __init__(self):
        _claim()
        super().__init__()
        self.layers = []

    def on_enter(self):
        global _active_scene
        _active_scene = self
        super().on_enter()

    def on_exit(self):
        global _active_scene
        if _active_scene is self:
            _active_scene = None
        super().on_exit()

    def layer(self, name=None, mode=TUNNEL, visible=True):
        layer = Layer(name=name, mode=mode, visible=visible)
        layer.scene = self
        self.layers.append(layer)
        return layer


class Layer:
    def __init__(self, name=None, mode=TUNNEL, visible=True):
        _claim()
        self.name = name
        self.scene = None
        self.mode = mode
        self.visible = visible
        self.sprites = []

    def add(self, sprite):
        if sprite not in self.sprites:
            self.sprites.append(sprite)
        sprite.layer = self
        if self.scene is not None:
            sprite._scene = self.scene
        sprite.mode = self.mode
        return sprite

    def remove(self, sprite):
        if sprite in self.sprites:
            self.sprites.remove(sprite)
        if sprite.layer is self:
            sprite.layer = None

    def clear(self):
        for sprite in list(self.sprites):
            self.remove(sprite)


class Sprite:
    def __init__(
        self,
        strip=None,
        x=0,
        y=0,
        frame=None,
        mode=TUNNEL,
        layer=None,
        visible=None,
        flip_x=False,
        flip_y=False,
        replacing=None,
    ):
        _claim()
        backend = get_platform().sprites
        if replacing is not None:
            replacing = replacing._sprite
        self._sprite = backend.Sprite(replacing=replacing)
        self._strip = None
        self._x = x
        self._y = y
        has_frame = frame is not None
        if frame is None:
            frame = 0
        self._frame = frame
        self._mode = mode
        if visible is None:
            visible = has_frame
        self._visible = bool(visible)
        self._flip_x = bool(flip_x)
        self._flip_y = bool(flip_y)
        self.layer = None
        self._scene = _active_scene
        _register_sprite(self)
        if layer is not None:
            layer.add(self)
        if strip is not None:
            self.strip = strip
        self._sync_all()

    def _sync_all(self):
        self._sync_mode()
        self._sync_position()
        self._sync_frame()

    def _sync_position(self):
        # The compatibility renderer cannot represent negative or fractional
        # coordinates yet; keep the real v2 values locally and publish a clipped
        # integer view to the old sprite table.
        self._sprite.set_x(_render_coord(self._x, 0, 255))
        self._sprite.set_y(_render_coord(self._y, 0, 255))

    def _sync_frame(self):
        if self._visible:
            self._sprite.set_frame(_render_coord(self._frame, 0, 254))
        else:
            self._sprite.set_frame(255)

    def _sync_mode(self):
        self._sprite.set_perspective(_render_coord(self._mode, 0, 2))

    @property
    def x(self):
        return self._x

    @x.setter
    def x(self, value):
        self._x = value
        self._sync_position()

    @property
    def y(self):
        return self._y

    @y.setter
    def y(self, value):
        self._y = value
        self._sync_position()

    @property
    def frame(self):
        return self._frame

    @frame.setter
    def frame(self, value):
        self._frame = value
        self._visible = True
        self._sync_frame()

    @property
    def strip(self):
        return self._strip

    @strip.setter
    def strip(self, value):
        resolved = _resolve_strip(value)
        self._strip = resolved
        self._sprite.set_strip(resolved)

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, value):
        self._mode = value
        self._sync_mode()

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value):
        self._visible = bool(value)
        self._sync_frame()

    @property
    def flip_x(self):
        return self._flip_x

    @flip_x.setter
    def flip_x(self, value):
        self._flip_x = bool(value)

    @property
    def flip_y(self):
        return self._flip_y

    @flip_y.setter
    def flip_y(self, value):
        self._flip_y = bool(value)

    @property
    def width(self):
        return self._sprite.width()

    @property
    def height(self):
        return self._sprite.height()

    def hide(self):
        self.visible = False

    def show(self, frame=None):
        if frame is not None:
            self._frame = frame
        self.visible = True

    def collides_with(self, sprites):
        for other in sprites:
            if _intersects(self.x, self.width, other.x, other.width) and _intersects(
                self.y, self.height, other.y, other.height
            ):
                return other
        return None

    # Temporary compatibility helpers for incremental ports from API v1.
    def disable(self):
        self.hide()

    def set_x(self, value):
        self.x = value

    def set_y(self, value):
        self.y = value

    def set_frame(self, value):
        self.frame = value

    def set_strip(self, value):
        self.strip = value

    def set_perspective(self, value):
        self.mode = value

    def collision(self, sprites):
        return self.collides_with(sprites)


def _intersects(x1, w1, x2, w2):
    delta = min(x1, x2)
    x1 = (x1 - delta + 128) % 256
    x2 = (x2 - delta + 128) % 256
    return x1 < x2 + w2 and x1 + w1 > x2
