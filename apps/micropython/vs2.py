"""The sealed, scene-owned Ventilastation display API (revision 2).

V1 lives in :mod:`ventilastation.sprites` and deliberately remains separate.
This module is the complete V2 surface: a scene builds a fixed display graph
once, then mutates it without allocating renderer records while it runs.
"""

import struct
import sys
import utime

from ventilastation import api_guard
from ventilastation.director import director, stripes
from ventilastation.display_geometry import DISPLAY_HEIGHT, DISPLAY_WIDTH
from ventilastation.scene import Scene as _Scene
from ventilastation.runtime import get_platform


def _claim():
    api_guard.claim("vs2", "vs2")


_claim()


# Projection values are the native renderer's wire values.
FULLSCREEN = 0
TUNNEL = 1
HUD = 2

TRANSPARENT = 255
EMPTY_TILE = 255
NO_LAYER = 255
RECYCLE = object()

FLAG_VISIBLE = 0x01
FLAG_FLIP_X = 0x02
FLAG_FLIP_Y = 0x04

PAYLOAD_MAGIC = b"VS2\0"
PAYLOAD_VERSION = 3
PAYLOAD_HEADER_SIZE = 16
PAYLOAD_LAYER_SIZE = 8
PAYLOAD_SPRITE_SIZE = 24
PAYLOAD_TILEMAP_SIZE = 32
PAYLOAD_DRAW_REF_SIZE = 2
DRAW_SPRITE = 0
DRAW_TILEMAP = 1


class SceneSealedError(RuntimeError):
    pass


class ResourceLimitError(RuntimeError):
    pass


class AssetNotFoundError(LookupError):
    pass


class FrameError(ValueError):
    pass


class _Limits:
    layers = 8
    sprites = 100
    tilemaps = 16
    image_strips = 100


limits = _Limits()


class _Display:
    """Target-derived display information and palette publication."""

    width = DISPLAY_WIDTH
    height = DISPLAY_HEIGHT

    @property
    def palettes(self):
        return getattr(director, "palette_data", None)

    def apply_palettes(self):
        palettes = self.palettes
        if palettes is not None:
            get_platform().display.set_palettes(palettes)


display = _Display()


class _BaseLeds:
    def __init__(self, owner):
        self.owner = owner

    def set_all(self, red, green, blue):
        self.owner._set_leds(red, green, blue)

    def off(self):
        self.set_all(0, 0, 0)


class _BaseServo:
    def __init__(self, owner):
        self.owner = owner

    def set(self, position):
        self.owner._set_servo(position)


class _BaseButtons:
    def __init__(self, owner):
        self.owner = owner

    def set(self, mask, blink_ms=0):
        self.owner._set_buttons(mask, blink_ms)

    def off(self):
        self.set(0)


class _BaseControl:
    BUTTON_LED_1 = 0x01
    BUTTON_LED_2 = 0x02
    BUTTON_LED_ALL = 0x03

    def __init__(self):
        self.leds = _BaseLeds(self)
        self.servo = _BaseServo(self)
        self.buttons = _BaseButtons(self)
        self._led_state = None
        self._servo_state = None
        self._button_state = None

    @staticmethod
    def _integer(value, minimum, maximum, name):
        if not isinstance(value, int) or value < minimum or value > maximum:
            raise ValueError("%s must be in %d..%d" % (name, minimum, maximum))
        return value

    @staticmethod
    def _send(line):
        get_platform().comms.send(line.encode("ascii"))

    def _set_leds(self, red, green, blue):
        state = (self._integer(red, 0, 255, "red"),
                 self._integer(green, 0, 255, "green"),
                 self._integer(blue, 0, 255, "blue"))
        if state != self._led_state:
            self._send("base leds %d %d %d" % state)
            self._led_state = state

    def _set_servo(self, position):
        state = self._integer(position, 0, 255, "position")
        if state != self._servo_state:
            self._send("base servo %d" % state)
            self._servo_state = state

    def _set_buttons(self, mask, blink_ms):
        state = (self._integer(mask, 0, self.BUTTON_LED_ALL, "mask"),
                 self._integer(blink_ms, 0, 10000, "blink_ms"))
        if state != self._button_state:
            self._send("base buttons %d %d" % state)
            self._button_state = state


base = _BaseControl()


class _Controller:
    def __init__(self, player):
        self.player = player

    def _mask(self, button):
        return button[0] if isinstance(button, tuple) else button

    def _extra(self, button):
        if not isinstance(button, tuple):
            return 0
        return button[self.player]

    def held(self, button):
        mask = self._mask(button)
        extra = self._extra(button)
        if self.player == 1:
            return bool((director.buttons & mask) or (director.extra_buttons & extra))
        return bool((director.buttons2 & mask) or (director.extra_buttons & extra))

    def just_pressed(self, button):
        mask = self._mask(button)
        extra = self._extra(button)
        if self.player == 1:
            return bool(((director.buttons & mask) and not (director.last_buttons & mask))
                        or ((director.extra_buttons & extra) and not (director.last_extra_buttons & extra)))
        return bool(((director.buttons2 & mask) and not (director.last_buttons2 & mask))
                    or ((director.extra_buttons & extra) and not (director.last_extra_buttons & extra)))

    def just_released(self, button):
        mask = self._mask(button)
        extra = self._extra(button)
        if self.player == 1:
            return bool((not (director.buttons & mask) and (director.last_buttons & mask))
                        or (not (director.extra_buttons & extra) and (director.last_extra_buttons & extra)))
        return bool((not (director.buttons2 & mask) and (director.last_buttons2 & mask))
                    or (not (director.extra_buttons & extra) and (director.last_extra_buttons & extra)))


class _Controls:
    LEFT = 0x01
    RIGHT = 0x02
    UP = 0x04
    DOWN = 0x08
    A = 0x10
    B = 0x20
    X = 0x40
    # The high bit also mirrors Y for V1 compatibility.  The extra bit is
    # included so the semantic V2 value remains correct on both controllers.
    Y = (0x80, 0x01, 0x02)
    START = (0, 0x04, 0x10)
    BACK = (0, 0x08, 0x20)
    joy1 = _Controller(1)
    joy2 = _Controller(2)
    __all__ = ("joy1", "joy2", "LEFT", "RIGHT", "UP", "DOWN", "A", "B",
               "X", "Y", "START", "BACK")


controls = _Controls()
# ``vs2`` is kept as one frozen-friendly source file.  Registering this small
# module object provides the documented ``from vs2.controls import ...`` API
# without making the board filesystem package layout more fragile.
try:
    sys.modules["vs2.controls"] = controls
except Exception:
    pass


def _app_slug():
    return api_guard.current_app() or "the current app"


def _qualified_asset(name):
    if "/" in name:
        return name
    slug = api_guard.current_app()
    return (slug + "/" + name) if slug else name


class _Audio:
    def sound(self, name):
        director.sound_play(_qualified_asset(name))

    def music(self, name, loop=False):
        director.music_play(_qualified_asset(name), loop=bool(loop))

    def stop_music(self):
        director.music_off()

    def notes(self, notes):
        director.notes_play(api_guard.current_app() or "", notes)


audio = _Audio()


def _vs2_backend():
    return getattr(get_platform(), "vs2", None)


def _fixed_8_8(value):
    try:
        fixed = int(value * 256)
    except TypeError:
        fixed = 0
    if fixed < -0x80000000:
        return -0x80000000
    if fixed > 0x7fffffff:
        return 0x7fffffff
    return fixed


def _floor_coord(value):
    try:
        value_int = int(value)
    except TypeError:
        return 0
    return value_int - 1 if value < value_int else value_int


def _render_coord(value, minimum=0, maximum=255):
    try:
        value = int(value)
    except TypeError:
        value = 0
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def _sprite_flags(sprite):
    flags = FLAG_VISIBLE if sprite.visible else 0
    if sprite.flip_x:
        flags |= FLAG_FLIP_X
    if sprite.flip_y:
        flags |= FLAG_FLIP_Y
    return flags


def _strip_metadata(number):
    metadata = getattr(director, "image_metadata", {}).get(number)
    if metadata is not None:
        return metadata
    # Tests and tiny apps can install a strip directly into the backend.  The
    # fallback preserves that useful workflow while ROM-loaded games get the
    # authoritative metadata parsed by the director.
    table = getattr(get_platform().sprites, "stripes", {})
    strip = table.get(number)
    if isinstance(strip, dict):
        return strip
    if strip is not None and len(strip) >= 4:
        width = strip[0]
        return {"width": 256 if width == 255 else width, "height": strip[1],
                "frames": strip[2], "palette": strip[3]}
    return None


class Image:
    """Read-only asset-bank image handle."""

    def __init__(self, name, strip, metadata):
        self.name = name
        self._strip = strip
        self.width = int(metadata["width"])
        self.height = int(metadata["height"])
        self.frames = int(metadata["frames"])
        self.glyphs = metadata.get("glyphs")


def _resolve_image(value):
    if isinstance(value, Image):
        return value
    if not isinstance(value, str):
        raise TypeError("image must be an image name or vs2.Image")
    try:
        strip = stripes[value]
    except KeyError:
        raise AssetNotFoundError("image '%s' is not in %s" % (value, _app_slug()))
    metadata = _strip_metadata(strip)
    if metadata is None:
        raise AssetNotFoundError("image '%s' has no loaded metadata in %s" % (value, _app_slug()))
    return Image(value, strip, metadata)


def _intersects(x1, width1, x2, width2):
    delta = min(x1, x2)
    x1 = (x1 - delta + display.width // 2) % display.width
    x2 = (x2 - delta + display.width // 2) % display.width
    return x1 < x2 + width2 and x1 + width1 > x2


class Scene(_Scene):
    """A V2 scene with an explicit build/sealed/closed lifetime."""

    idle_timeout = 30
    back_button = True
    starfield = False
    asset_pack = None

    def __init__(self):
        _claim()
        _Scene.__init__(self)
        self.layers = []
        self._phase = "new"
        self._vs2_payload = None
        self._pending_transition = None
        self._sprite_count = 0
        self._tilemap_count = 0
        self._image_cache = {}

    def build(self):
        pass

    def update(self):
        pass

    def teardown(self):
        pass

    def _require_build(self, method):
        if self._phase != "building":
            raise SceneSealedError("%s() is only allowed while %s.build() runs" %
                                   (method, self.__class__.__name__))

    def _reserve(self, kind, count, layer):
        if kind == "sprite":
            current = self._sprite_count
            limit = limits.sprites
        elif kind == "tilemap":
            current = self._tilemap_count
            limit = limits.tilemaps
        else:
            current = len(self.layers)
            limit = limits.layers
        requested = current + count
        if requested > limit:
            raise ResourceLimitError(
                "%s %d/%d in %s (%s); reduce the %s budget"
                % (kind, requested, limit, self.__class__.__name__,
                   getattr(layer, "name", None) or "scene", kind)
            )
        if kind == "sprite":
            self._sprite_count = requested
        elif kind == "tilemap":
            self._tilemap_count = requested

    def image(self, value):
        if isinstance(value, Image):
            return value
        cached = self._image_cache.get(value)
        if cached is None:
            cached = _resolve_image(value)
            self._image_cache[value] = cached
        return cached

    def layer(self, name=None, projection=TUNNEL, visible=True, **legacy):
        if "mode" in legacy:
            projection = legacy["mode"]
        self._require_build("layer")
        self._reserve("layer", 1, self)
        layer = Layer(self, name, projection, visible)
        self.layers.append(layer)
        return layer

    def on_enter(self):
        backend = _vs2_backend()
        self._clear_drawables()
        self._phase = "building"
        self._pending_transition = None
        self._sprite_count = 0
        self._tilemap_count = 0
        self._image_cache.clear()
        if backend is not None:
            backend.reset_scene()
            backend.set_active(True)
        try:
            # V2 owns its asset pack.  Existing unit tests and embedded tools
            # may construct an anonymous scene with preinstalled strips, in
            # which case there is intentionally nothing to load.
            pack = self.asset_pack or getattr(self, "_vs_api_slug", None)
            if pack:
                director.load_rom("roms/" + pack + ".rom")
            self.build()
        except Exception:
            self._phase = "closed"
            if backend is not None:
                backend.set_active(False)
                backend.reset_scene()
            raise
        self._phase = "sealed"
        setter = getattr(get_platform().display, "set_starfield", None)
        if setter is not None:
            setter(bool(self.starfield))

    def on_exit(self):
        backend = _vs2_backend()
        self._phase = "closing"
        try:
            self.teardown()
        finally:
            self.pending_calls.clear()
            self._clear_drawables()
            self._vs2_payload = None
            self._image_cache.clear()
            self._phase = "closed"
            setter = getattr(get_platform().display, "set_starfield", None)
            if setter is not None:
                setter(False)
            if backend is not None:
                backend.set_active(False)
                backend.reset_scene()
            _Scene.on_exit(self)

    def _clear_drawables(self):
        for layer in self.layers:
            layer._close()
        del self.layers[:]

    def call_later(self, delay, callback, *args, **kwargs):
        if self._phase not in ("building", "sealed"):
            raise SceneSealedError("call_later() requires a building or running V2 scene")
        when = utime.ticks_add(utime.ticks_ms(), int(delay))
        self.pending_calls.append((when, callback, args, kwargs))
        self.pending_calls.sort(key=lambda entry: entry[0])

    def _queue_transition(self, kind, target=None):
        if self._pending_transition is not None:
            raise RuntimeError("%s already queued a scene transition" % self.__class__.__name__)
        self._pending_transition = (kind, target)

    def push(self, scene):
        self._queue_transition("push", scene)

    def pop(self):
        self._queue_transition("pop")

    def switch(self, scene):
        self._queue_transition("switch", scene)

    def on_idle(self):
        self.pop()

    def _run_defaults(self):
        if self._pending_transition is not None:
            return
        if self.back_button and (controls.joy1.just_pressed(controls.Y)
                                 or controls.joy1.just_pressed(controls.BACK)):
            self.pop()
            return
        if self.idle_timeout is not None and director.timedout:
            self.on_idle()

    def _drain_timers(self):
        now = utime.ticks_ms()
        while self.pending_calls:
            when, callback, args, kwargs = self.pending_calls[0]
            if utime.ticks_diff(when, now) > 0:
                break
            self.pending_calls.pop(0)
            callback(*args, **kwargs)
            if self._pending_transition is not None:
                break

    def _commit_transition(self):
        transition = self._pending_transition
        self._pending_transition = None
        if transition is None:
            return
        kind, target = transition
        if kind == "push":
            director.push(target)
        elif kind == "switch":
            director.pop()
            director.push(target)
        else:
            director.pop()

    def scene_step(self):
        self.update()
        if self._pending_transition is None:
            self._run_defaults()
        if self._pending_transition is None:
            self._drain_timers()
        # Director re-reads the stack after scene_step(), so callbacks that
        # queued a transition cannot run against a scene that has just left.
        self._commit_transition()


class Layer:
    def __init__(self, scene, name, projection, visible):
        self.scene = scene
        self.name = name
        self._projection = _projection(projection)
        self._visible = bool(visible)
        self._drawables = []
        backend = _vs2_backend()
        self._layer = backend.Layer(mode=self._projection, visible=self._visible) if backend else None

    def _require_build(self, method):
        self.scene._require_build(method)

    def _close(self):
        for drawable in self._drawables:
            drawable._closed = True
            drawable._layer = None
        del self._drawables[:]
        self.scene = None
        self._layer = None

    @property
    def projection(self):
        return self._projection

    @projection.setter
    def projection(self, value):
        self._projection = _projection(value)
        if self._layer is not None:
            self._layer.set_mode(self._projection)

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value):
        self._visible = bool(value)
        if self._layer is not None:
            self._layer.set_visible(self._visible)

    @property
    def sprites(self):
        return [drawable for drawable in self._drawables if isinstance(drawable, Sprite)]

    @property
    def tilemaps(self):
        return [drawable for drawable in self._drawables if isinstance(drawable, Tilemap)]

    def sprite(self, image, x=0, y=0, frame=0, visible=True, flip_x=False, flip_y=False):
        self._require_build("sprite")
        self.scene._reserve("sprite", 1, self)
        sprite = Sprite(self, self.scene.image(image), x, y, frame, visible, flip_x, flip_y)
        self._drawables.append(sprite)
        return sprite

    def sprite_pool(self, image, count, frame=0, on_empty=None):
        self._require_build("sprite_pool")
        count = int(count)
        if count < 1:
            raise ValueError("sprite_pool count must be positive")
        self.scene._reserve("sprite", count, self)
        image = self.scene.image(image)
        sprites = []
        for _ in range(count):
            sprite = Sprite(self, image, 0, 0, frame, False, False, False)
            self._drawables.append(sprite)
            sprites.append(sprite)
        return SpritePool(sprites, on_empty)

    def tilemap(self, image, columns, rows, cells=None, x=0, y=0,
                view_width=None, view_height=None, view_x=0, view_y=0, visible=True):
        self._require_build("tilemap")
        if self.projection == FULLSCREEN:
            raise ValueError("tilemap() is not supported on a FULLSCREEN layer")
        self.scene._reserve("tilemap", 1, self)
        tilemap = Tilemap(self, self.scene.image(image), columns, rows, cells,
                          x, y, view_width, view_height, view_x, view_y, visible)
        self._drawables.append(tilemap)
        return tilemap

    def label(self, image, columns, rows=1, x=0, y=0, text=None, glyphs=None, visible=True):
        self._require_build("label")
        if self.projection == FULLSCREEN:
            raise ValueError("label() is not supported on a FULLSCREEN layer")
        self.scene._reserve("tilemap", 1, self)
        label = Label(self, self.scene.image(image), columns, rows, x, y, glyphs, visible)
        self._drawables.append(label)
        if text is not None:
            label.text = text
        return label


def _projection(value):
    value = int(value)
    if value not in (FULLSCREEN, TUNNEL, HUD):
        raise ValueError("projection must be vs2.FULLSCREEN, TUNNEL, or HUD")
    return value


class Sprite:
    def __init__(self, layer, image, x, y, frame, visible, flip_x, flip_y):
        self._layer = layer
        self._closed = False
        backend = _vs2_backend()
        if backend is None:
            backend = get_platform().sprites
        self._sprite = backend.Sprite()
        self._uses_fixed_coords = hasattr(self._sprite, "set_x_fixed")
        self._has_flags = hasattr(self._sprite, "set_flags")
        self._has_layer = hasattr(self._sprite, "set_layer")
        self._image = image
        self._x = x
        self._y = y
        self._frame = 0
        self._visible = bool(visible)
        self._flip_x = bool(flip_x)
        self._flip_y = bool(flip_y)
        self._pool = None
        self._pool_live_index = -1
        self._set_frame(frame)
        self._sync_all()

    def _sync_all(self):
        self._sprite.set_strip(self._image._strip)
        if self._uses_fixed_coords:
            self._sprite.set_x_fixed(_fixed_8_8(self._x))
            self._sprite.set_y_fixed(_fixed_8_8(self._y))
        else:
            self._sprite.set_x(_floor_coord(self._x) % display.width)
            self._sprite.set_y(_render_coord(_floor_coord(self._y), 0, display.height - 1))
        self._sprite.set_perspective(self._layer.projection)
        if self._has_layer:
            self._sprite.set_layer(self._layer._layer)
        self._sync_flags()
        self._sync_frame()

    def _sync_flags(self):
        if self._has_flags:
            self._sprite.set_flags(_sprite_flags(self))

    def _sync_frame(self):
        if self._has_flags or self._visible:
            self._sprite.set_frame(self._frame)
        else:
            self._sprite.set_frame(EMPTY_TILE)

    def _set_frame(self, value):
        value = int(value)
        if value < 0 or value >= self._image.frames:
            raise FrameError("%s has %d frames; frame must be 0..%d" %
                             (self._image.name, self._image.frames, self._image.frames - 1))
        self._frame = value

    @property
    def layer(self):
        return self._layer

    @property
    def image(self):
        return self._image

    @image.setter
    def image(self, value):
        image = self._layer.scene.image(value)
        self._image = image
        if self._frame >= image.frames:
            self._frame = 0
        self._sprite.set_strip(image._strip)
        self._sync_frame()

    @property
    def x(self):
        return self._x

    @x.setter
    def x(self, value):
        self._x = value
        if self._uses_fixed_coords:
            self._sprite.set_x_fixed(_fixed_8_8(value))
        else:
            self._sprite.set_x(_floor_coord(value) % display.width)

    @property
    def y(self):
        return self._y

    @y.setter
    def y(self, value):
        self._y = value
        if self._uses_fixed_coords:
            self._sprite.set_y_fixed(_fixed_8_8(value))
        else:
            self._sprite.set_y(_render_coord(_floor_coord(value), 0, display.height - 1))

    @property
    def frame(self):
        return self._frame

    @frame.setter
    def frame(self, value):
        self._set_frame(value)
        self._sync_frame()

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value):
        self._visible = bool(value)
        self._sync_flags()
        self._sync_frame()

    @property
    def flip_x(self):
        return self._flip_x

    @flip_x.setter
    def flip_x(self, value):
        self._flip_x = bool(value)
        self._sync_flags()

    @property
    def flip_y(self):
        return self._flip_y

    @flip_y.setter
    def flip_y(self, value):
        self._flip_y = bool(value)
        self._sync_flags()

    @property
    def width(self):
        return self._image.width

    @property
    def height(self):
        return self._image.height

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def overlaps(self, other):
        return _intersects(self.x, self.width, other.x, other.width) and _intersects(
            self.y, self.height, other.y, other.height)

    def first_overlap(self, sprites):
        for other in sprites:
            if self.overlaps(other):
                return other
        return None


class _PoolIterator:
    def __init__(self, pool):
        self.pool = pool
        self.index = 0
        self.previous = None

    def __iter__(self):
        return self

    def __next__(self):
        if self.previous is not None and self.previous._pool_live_index == -1:
            self.previous = None
        else:
            self.index += 1 if self.previous is not None else 0
            self.previous = None
        if self.index >= len(self.pool._live):
            raise StopIteration
        self.previous = self.pool._live[self.index]
        return self.previous


class SpritePool:
    def __init__(self, sprites, on_empty):
        self._free = sprites
        self._live = []
        self._on_empty = on_empty
        for sprite in sprites:
            sprite._pool = self

    @property
    def free(self):
        return len(self._free)

    def __len__(self):
        return len(self._live)

    def __iter__(self):
        return _PoolIterator(self)

    def spawn(self, x, y, frame=0, flip_x=False, flip_y=False):
        if not self._free:
            if self._on_empty is not RECYCLE:
                return None
            self.despawn(self._live[0])
        sprite = self._free.pop()
        sprite.x = x
        sprite.y = y
        sprite.frame = frame
        sprite.flip_x = flip_x
        sprite.flip_y = flip_y
        sprite.visible = True
        sprite._pool_live_index = len(self._live)
        self._live.append(sprite)
        return sprite

    def despawn(self, sprite):
        if getattr(sprite, "_pool", None) is not self or sprite._pool_live_index < 0:
            raise ValueError("sprite is not live in this pool")
        index = sprite._pool_live_index
        tail = self._live.pop()
        if tail is not sprite:
            self._live[index] = tail
            tail._pool_live_index = index
        sprite._pool_live_index = -1
        sprite.hide()
        self._free.append(sprite)

    def despawn_all(self):
        while self._live:
            self.despawn(self._live[-1])


class Tilemap:
    def __init__(self, layer, image, columns, rows, cells, x, y,
                 view_width, view_height, view_x, view_y, visible):
        columns = int(columns)
        rows = int(rows)
        if columns < 1 or rows < 1:
            raise ValueError("tilemap columns and rows must be positive")
        if cells is None:
            cells = bytearray([EMPTY_TILE] * (columns * rows))
        if len(cells) != columns * rows:
            raise ValueError("cells length must equal columns * rows")
        self._layer = layer
        self._closed = False
        self._image = image
        self.columns = columns
        self.rows = rows
        self.tile_width = image.width
        self.tile_height = image.height
        self.cells = cells
        self._x = x
        self._y = y
        self._view_x = int(view_x)
        self._view_y = int(view_y)
        self.view_width = int(view_width if view_width is not None else columns * image.width)
        self.view_height = int(view_height if view_height is not None else rows * image.height)
        if self._view_x < 0 or self._view_y < 0 or self.view_width < 1 or self.view_height < 1:
            raise ValueError("invalid tilemap view")
        self._visible = bool(visible)
        backend = _vs2_backend()
        self._tilemap = None
        if backend is not None and hasattr(backend, "Tilemap"):
            self._tilemap = backend.Tilemap(
                strip=image._strip, frames=cells, columns=columns, rows=rows,
                tile_width=image.width, tile_height=image.height)
        self._sync_all()

    @property
    def layer(self):
        return self._layer

    @property
    def image(self):
        return self._image

    @property
    def frames(self):
        # Read-only compatibility alias for renderer tooling.  V2 game code
        # uses ``cells``.
        return self.cells

    @property
    def x(self):
        return self._x

    @x.setter
    def x(self, value):
        self._x = value
        if self._tilemap is not None:
            self._tilemap.set_x_fixed(_fixed_8_8(value))

    @property
    def y(self):
        return self._y

    @y.setter
    def y(self, value):
        self._y = value
        if self._tilemap is not None:
            self._tilemap.set_y_fixed(_fixed_8_8(value))

    @property
    def view_x(self):
        return self._view_x

    @view_x.setter
    def view_x(self, value):
        self._view_x = int(value)
        self._sync_view()

    @property
    def view_y(self):
        return self._view_y

    @view_y.setter
    def view_y(self, value):
        self._view_y = int(value)
        self._sync_view()

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value):
        self._visible = bool(value)
        if self._tilemap is not None:
            self._tilemap.set_flags(FLAG_VISIBLE if self._visible else 0)

    def _sync_all(self):
        if self._tilemap is None:
            return
        self._tilemap.set_x_fixed(_fixed_8_8(self._x))
        self._tilemap.set_y_fixed(_fixed_8_8(self._y))
        self._tilemap.set_perspective(self._layer.projection)
        self._tilemap.set_layer(self._layer._layer)
        self._tilemap.set_flags(FLAG_VISIBLE if self._visible else 0)
        self._sync_view()

    def _sync_view(self):
        if self._tilemap is not None:
            self._tilemap.set_viewport(self._view_x, self._view_y,
                                       self.view_width, self.view_height)

    def __getitem__(self, position):
        column, row = position
        return self.cells[self._cell_index(column, row)]

    def __setitem__(self, position, value):
        self.cells[self._cell_index(*position)] = int(value)

    def _cell_index(self, column, row):
        column = int(column)
        row = int(row)
        if column < 0 or column >= self.columns or row < 0 or row >= self.rows:
            raise IndexError("tilemap cell out of range")
        return row * self.columns + column

    def fill(self, value):
        value = int(value)
        for index in range(len(self.cells)):
            self.cells[index] = value

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False


class Label(Tilemap):
    def __init__(self, layer, image, columns, rows, x, y, glyphs, visible):
        self._glyphs = glyphs if glyphs is not None else image.glyphs
        Tilemap.__init__(self, layer, image, columns, rows, None, x, y,
                         image.width * int(columns), image.height * int(rows),
                         0, 0, visible)

    def _glyph(self, char, frame_offset):
        if self._glyphs is None:
            value = ord(char)
        else:
            try:
                value = self._glyphs.index(char)
            except ValueError:
                return EMPTY_TILE
        value += frame_offset
        return value if 0 <= value < self.image.frames else EMPTY_TILE

    def write(self, column, row, text, frame_offset=0, pad=True):
        column = int(column)
        row = int(row)
        if row < 0 or row >= self.rows:
            raise IndexError("label row out of range")
        if column < 0 or column >= self.columns:
            raise IndexError("label column out of range")
        text = str(text)
        remaining = self.columns - column if pad else min(len(str(text)), self.columns - column)
        for index in range(remaining):
            char = text[index] if index < len(text) else None
            value = EMPTY_TILE if char is None else self._glyph(char, int(frame_offset))
            # Tile storage runs counter-clockwise; this is the one place the
            # direction inversion belongs, never in game code.
            self.cells[row * self.columns + self.columns - 1 - (column + index)] = value

    @property
    def text(self):
        if self.rows != 1:
            raise AttributeError("multi-line labels have no text property")
        return ""

    @text.setter
    def text(self, value):
        if self.rows != 1:
            raise AttributeError("multi-line labels have no text property")
        self.write(0, 0, value)

    def set_number(self, value, width=1, pad="0"):
        width = int(width)
        if width < 1 or width > self.columns:
            raise ValueError("number width must fit the label")
        value = int(value)
        if value < 0:
            value = 0
        divisor = 1
        for _ in range(width - 1):
            divisor *= 10
        for index in range(width):
            digit = value // divisor if divisor else value
            if digit > 9:
                digit = 9
            if value < divisor and pad != "0" and index < width - 1:
                char = pad[0] if pad else " "
            else:
                char = chr(ord("0") + digit)
            self.cells[self.columns - 1 - index] = self._glyph(char, 0)
            value %= divisor if divisor else 1
            divisor //= 10 if divisor > 1 else 1


def _payload_buffer(scene, size):
    payload = scene._vs2_payload
    if payload is None or len(payload) != size:
        payload = bytearray(size)
        scene._vs2_payload = payload
    return payload


def export_scene_payload(scene=None):
    """Export the sealed display graph for desktop and browser renderers."""
    _claim()
    if scene is None:
        return bytearray()
    layers = scene.layers
    sprites = []
    tilemaps = []
    drawables = []
    for layer_index, layer in enumerate(layers):
        for drawable in layer._drawables:
            if isinstance(drawable, Sprite):
                sprites.append(drawable)
                drawables.append((DRAW_SPRITE, len(sprites) - 1, layer_index))
            else:
                tilemaps.append(drawable)
                drawables.append((DRAW_TILEMAP, len(tilemaps) - 1, layer_index))
    frames_size = 0
    for tilemap in tilemaps:
        frames_size += len(tilemap.cells)
    size = (PAYLOAD_HEADER_SIZE + len(layers) * PAYLOAD_LAYER_SIZE
            + len(sprites) * PAYLOAD_SPRITE_SIZE + len(tilemaps) * PAYLOAD_TILEMAP_SIZE
            + frames_size + len(drawables) * PAYLOAD_DRAW_REF_SIZE)
    payload = _payload_buffer(scene, size)
    struct.pack_into("<4sBBBBHHHH", payload, 0, PAYLOAD_MAGIC, PAYLOAD_VERSION,
                     len(layers), len(sprites), len(tilemaps), PAYLOAD_HEADER_SIZE,
                     PAYLOAD_LAYER_SIZE, PAYLOAD_SPRITE_SIZE, PAYLOAD_TILEMAP_SIZE)
    offset = PAYLOAD_HEADER_SIZE
    for index, layer in enumerate(layers):
        struct.pack_into("<BBBBBBBB", payload, offset, index, layer.projection,
                         FLAG_VISIBLE if layer.visible else 0, 0, 0, 0, 0, 0)
        offset += PAYLOAD_LAYER_SIZE
    for sprite in sprites:
        layer_index = layers.index(sprite.layer)
        struct.pack_into("<BBBBBBhhii", payload, offset, layer_index,
                         sprite.image._strip, sprite.frame, sprite.layer.projection,
                         _sprite_flags(sprite), 0, 0, 0, _fixed_8_8(sprite.x),
                         _fixed_8_8(sprite.y))
        offset += PAYLOAD_SPRITE_SIZE
    cells_offset = offset + len(tilemaps) * PAYLOAD_TILEMAP_SIZE
    for tilemap in tilemaps:
        layer_index = layers.index(tilemap.layer)
        struct.pack_into("<BBBBHHHHHHHHiiI", payload, offset, layer_index,
                         tilemap.image._strip, FLAG_VISIBLE if tilemap.visible else 0,
                         tilemap.layer.projection, tilemap.columns, tilemap.rows,
                         tilemap.tile_width, tilemap.tile_height, tilemap.view_x,
                         tilemap.view_y, tilemap.view_width, tilemap.view_height,
                         _fixed_8_8(tilemap.x), _fixed_8_8(tilemap.y), cells_offset)
        offset += PAYLOAD_TILEMAP_SIZE
        payload[cells_offset:cells_offset + len(tilemap.cells)] = tilemap.cells
        cells_offset += len(tilemap.cells)
    for kind, index, _layer_index in drawables:
        payload[cells_offset] = kind
        payload[cells_offset + 1] = index
        cells_offset += PAYLOAD_DRAW_REF_SIZE
    return payload


def reset_runtime_state():
    base._led_state = None
    base._servo_state = None
    base._button_state = None


def set_starfield(enabled):
    """Temporary adapter for code that has not moved to Scene.starfield."""
    setter = getattr(get_platform().display, "set_starfield", None)
    if setter is not None:
        return setter(bool(enabled))
    get_platform().display.starfield_enabled = bool(enabled)
    return None
