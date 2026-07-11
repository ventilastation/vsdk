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
PAYLOAD_VERSION_TILEMAPS = 2
PAYLOAD_HEADER_SIZE = 16
PAYLOAD_LAYER_SIZE = 8
PAYLOAD_SPRITE_SIZE = 24
PAYLOAD_TILEMAP_SIZE = 32

FLAG_VISIBLE = 0x01
FLAG_FLIP_X = 0x02
FLAG_FLIP_Y = 0x04
NO_LAYER = 255
EMPTY_TILE = 255

_live_sprites = []
_live_tilemaps = []
_active_scene = None
_next_sprite_order = 0
_scratch_sprites = []
_scratch_tilemaps = []


def _vs2_backend():
    return getattr(get_platform(), "vs2", None)


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


def _floor_coord(value):
    try:
        ivalue = int(value)
    except TypeError:
        return 0
    if value < ivalue:
        return ivalue - 1
    return ivalue


def _wrap_x_coord(value):
    return _floor_coord(value) % 256


def _clip_y_coord(value):
    return _render_coord(_floor_coord(value), 0, 255)


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


def _register_tilemap(tilemap):
    global _next_sprite_order
    if tilemap not in _live_tilemaps:
        tilemap._vs2_order = _next_sprite_order
        _next_sprite_order += 1
        _live_tilemaps.append(tilemap)


def reset_runtime_state():
    global _active_scene, _next_sprite_order
    del _live_sprites[:]
    del _scratch_sprites[:]
    del _live_tilemaps[:]
    del _scratch_tilemaps[:]
    _active_scene = None
    _next_sprite_order = 0


def _remove_scene_sprites(scene):
    write = 0
    for read in range(len(_live_sprites)):
        sprite = _live_sprites[read]
        if getattr(sprite, "_scene", None) is scene:
            sprite._scene = None
            continue
        if write != read:
            _live_sprites[write] = sprite
        write += 1
    del _live_sprites[write:]


def _remove_scene_tilemaps(scene):
    write = 0
    for read in range(len(_live_tilemaps)):
        tilemap = _live_tilemaps[read]
        if getattr(tilemap, "_scene", None) is scene:
            tilemap._scene = None
            continue
        if write != read:
            _live_tilemaps[write] = tilemap
        write += 1
    del _live_tilemaps[write:]


def _clear_scene_objects(scene):
    """Drop the Python ownership links for one scene's drawables."""
    _remove_scene_sprites(scene)
    _remove_scene_tilemaps(scene)
    for layer in scene.layers:
        layer.clear()
        layer.scene = None
        layer._layer = None
    del scene.layers[:]


def _collect_scene_sprites(scene, sprites):
    del sprites[:]
    for sprite in _live_sprites:
        if scene is not None and getattr(sprite, "_scene", None) is not scene:
            continue
        sprites.append(sprite)
    return sprites


def _collect_scene_tilemaps(scene, tilemaps):
    del tilemaps[:]
    for tilemap in _live_tilemaps:
        if scene is not None and getattr(tilemap, "_scene", None) is not scene:
            continue
        tilemaps.append(tilemap)
    return tilemaps


def _layer_index(layers, layer):
    for index, candidate in enumerate(layers):
        if candidate is layer:
            return index
    return NO_LAYER


def _payload_buffer(scene, size):
    if scene is None:
        return bytearray(size)
    payload = getattr(scene, "_vs2_payload", None)
    if payload is None or len(payload) != size:
        payload = bytearray(size)
        scene._vs2_payload = payload
    return payload


def export_scene_payload(scene=None):
    _claim()
    layers = ()
    if scene is not None:
        layers = getattr(scene, "layers", ())

    sprites = _collect_scene_sprites(scene, _scratch_sprites)
    tilemaps = _collect_scene_tilemaps(scene, _scratch_tilemaps)
    frames_size = 0
    for tilemap in tilemaps:
        frames_size += tilemap.columns * tilemap.rows
    payload = _payload_buffer(
        scene,
        PAYLOAD_HEADER_SIZE
        + len(layers) * PAYLOAD_LAYER_SIZE
        + len(sprites) * PAYLOAD_SPRITE_SIZE
        + len(tilemaps) * PAYLOAD_TILEMAP_SIZE
        + frames_size
    )
    struct.pack_into(
        "<4sBBBBHHHH",
        payload,
        0,
        PAYLOAD_MAGIC,
        PAYLOAD_VERSION_TILEMAPS if tilemaps else PAYLOAD_VERSION,
        len(layers),
        len(sprites),
        len(tilemaps),
        PAYLOAD_HEADER_SIZE,
        PAYLOAD_LAYER_SIZE,
        PAYLOAD_SPRITE_SIZE,
        PAYLOAD_TILEMAP_SIZE if tilemaps else 0,
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
        index = _layer_index(layers, layer) if layer is not None else NO_LAYER
        if index != NO_LAYER:
            mode = layer.mode
        else:
            mode = sprite.mode
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
    frames_offset = offset + len(tilemaps) * PAYLOAD_TILEMAP_SIZE
    for tilemap in tilemaps:
        layer = tilemap.layer
        index = _layer_index(layers, layer) if layer is not None else NO_LAYER
        if index != NO_LAYER:
            mode = layer.mode
        else:
            mode = tilemap.mode
        viewport_x, viewport_y, viewport_w, viewport_h = tilemap.viewport
        struct.pack_into(
            "<BBBBHHHHHHHHiiI",
            payload,
            offset,
            index,
            _strip_number(tilemap),
            FLAG_VISIBLE if tilemap.visible else 0,
            _render_coord(mode, 0, 2),
            tilemap.columns,
            tilemap.rows,
            tilemap.tile_width,
            tilemap.tile_height,
            viewport_x,
            viewport_y,
            viewport_w,
            viewport_h,
            _fixed_8_8(tilemap.x),
            _fixed_8_8(tilemap.y),
            frames_offset,
        )
        offset += PAYLOAD_TILEMAP_SIZE
        cells = tilemap.columns * tilemap.rows
        payload[frames_offset:frames_offset + cells] = tilemap.frames
        frames_offset += cells
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
        self._vs2_payload = None

    def on_enter(self):
        global _active_scene
        backend = _vs2_backend()
        _clear_scene_objects(self)
        if backend is not None:
            backend.reset_scene()
            backend.set_active(True)
        _active_scene = self
        super().on_enter()

    def on_exit(self):
        global _active_scene
        backend = _vs2_backend()
        if backend is not None:
            backend.set_active(False)
        if _active_scene is self:
            _active_scene = None
        _clear_scene_objects(self)
        self._vs2_payload = None
        if backend is not None:
            backend.reset_scene()
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
        self._mode = mode
        self._visible = visible
        self.sprites = []
        self.tilemaps = []
        backend = _vs2_backend()
        if backend is not None:
            self._layer = backend.Layer(mode=mode, visible=visible)
        else:
            self._layer = None

    def _sync_mode(self):
        if self._layer is not None:
            self._layer.set_mode(_render_coord(self._mode, 0, 2))

    def _sync_visible(self):
        if self._layer is not None:
            self._layer.set_visible(self._visible)

    def add(self, drawable):
        if isinstance(drawable, Tilemap):
            if drawable not in self.tilemaps:
                self.tilemaps.append(drawable)
        elif drawable not in self.sprites:
            self.sprites.append(drawable)
        drawable.layer = self
        if self.scene is not None:
            drawable._scene = self.scene
        drawable.mode = self.mode
        return drawable

    def remove(self, drawable):
        if drawable in self.sprites:
            self.sprites.remove(drawable)
        if drawable in self.tilemaps:
            self.tilemaps.remove(drawable)
        if drawable.layer is self:
            drawable.layer = None

    def clear(self):
        while self.sprites:
            self.remove(self.sprites[-1])
        while self.tilemaps:
            self.remove(self.tilemaps[-1])

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, value):
        self._mode = value
        self._sync_mode()
        for sprite in self.sprites:
            sprite.mode = value
        for tilemap in self.tilemaps:
            tilemap.mode = value

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value):
        self._visible = bool(value)
        self._sync_visible()


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
        backend = _vs2_backend()
        if backend is None:
            backend = get_platform().sprites
        if replacing is not None:
            self._sprite = backend.Sprite(replacing=replacing._sprite)
        else:
            self._sprite = backend.Sprite()
        self._uses_fixed_coords = hasattr(self._sprite, "set_x_fixed")
        self._has_flags = hasattr(self._sprite, "set_flags")
        self._has_layer = hasattr(self._sprite, "set_layer")
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
        self._layer = None
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
        self._sync_layer()
        self._sync_flags()
        self._sync_frame()

    def _sync_position(self):
        if self._uses_fixed_coords:
            self._sprite.set_x_fixed(_fixed_8_8(self._x))
            self._sprite.set_y_fixed(_fixed_8_8(self._y))
        else:
            self._sprite.set_x(_wrap_x_coord(self._x))
            self._sprite.set_y(_clip_y_coord(self._y))

    def _sync_frame(self):
        if self._uses_fixed_coords:
            self._sprite.set_frame(_render_coord(self._frame, 0, 254))
        elif self._visible:
            self._sprite.set_frame(_render_coord(self._frame, 0, 254))
        else:
            self._sprite.set_frame(255)

    def _sync_mode(self):
        self._sprite.set_perspective(_render_coord(self._mode, 0, 2))

    def _sync_flags(self):
        if self._has_flags:
            self._sprite.set_flags(_sprite_flags(self))

    def _sync_layer(self):
        if not self._has_layer:
            return
        layer = self._layer
        self._sprite.set_layer(layer._layer if layer is not None else None)

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
        self._sync_flags()
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
    def layer(self):
        return self._layer

    @layer.setter
    def layer(self, value):
        self._layer = value
        self._sync_layer()

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


class Tilemap:
    """A grid of tiles rendered from a caller-owned byte buffer of frame ids.

    The supplied ``frames`` buffer is retained, never copied: mutate cells with
    plain indexed writes (``frames[index] = tile``). ``columns``, ``rows``,
    ``tile_width`` and ``tile_height`` are fixed after creation, and resizing
    or replacing the buffer while the tilemap is active is unsupported.
    ``viewport`` is a pixel rectangle of the map drawn at the on-screen origin
    (x, y); changing its position pans the map under a fixed window. Frame id
    255 (EMPTY_TILE) leaves a cell empty.
    """

    def __init__(
        self,
        strip,
        frames,
        columns,
        rows,
        tile_width,
        tile_height,
        x=0,
        y=0,
        viewport=None,
        layer=None,
        visible=True,
    ):
        _claim()
        columns = int(columns)
        rows = int(rows)
        tile_width = int(tile_width)
        tile_height = int(tile_height)
        if columns <= 0 or rows <= 0 or tile_width <= 0 or tile_height <= 0:
            raise ValueError("tilemap dimensions must be positive")
        if columns * tile_width > 0xFFFF or rows * tile_height > 0xFFFF:
            raise ValueError("tilemap pixel size too large")
        if len(frames) != columns * rows:
            raise ValueError("frames length must equal columns * rows")
        self.frames = frames
        self.columns = columns
        self.rows = rows
        self.tile_width = tile_width
        self.tile_height = tile_height
        self._strip = _resolve_strip(strip)
        self._x = x
        self._y = y
        self._mode = TUNNEL
        self._visible = bool(visible)
        if viewport is None:
            viewport = (0, 0, columns * tile_width, rows * tile_height)
        self._viewport = _check_viewport(viewport)
        self._layer = None
        backend = _vs2_backend()
        if backend is not None and hasattr(backend, "Tilemap"):
            self._tilemap = backend.Tilemap(
                strip=self._strip,
                frames=frames,
                columns=columns,
                rows=rows,
                tile_width=tile_width,
                tile_height=tile_height,
            )
        else:
            self._tilemap = None
        self._scene = _active_scene
        _register_tilemap(self)
        if layer is not None:
            layer.add(self)
        self._sync_all()

    def _sync_all(self):
        self._sync_mode()
        self._sync_position()
        self._sync_layer()
        self._sync_flags()
        self._sync_viewport()

    def _sync_position(self):
        if self._tilemap is not None:
            self._tilemap.set_x_fixed(_fixed_8_8(self._x))
            self._tilemap.set_y_fixed(_fixed_8_8(self._y))

    def _sync_mode(self):
        if self._tilemap is not None:
            self._tilemap.set_perspective(_render_coord(self._mode, 0, 2))

    def _sync_flags(self):
        if self._tilemap is not None:
            self._tilemap.set_flags(FLAG_VISIBLE if self._visible else 0)

    def _sync_layer(self):
        if self._tilemap is not None:
            layer = self._layer
            self._tilemap.set_layer(layer._layer if layer is not None else None)

    def _sync_viewport(self):
        if self._tilemap is not None:
            viewport_x, viewport_y, viewport_w, viewport_h = self._viewport
            self._tilemap.set_viewport(
                viewport_x, viewport_y, viewport_w, viewport_h
            )

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
    def strip(self):
        return self._strip

    @property
    def viewport(self):
        return self._viewport

    @viewport.setter
    def viewport(self, value):
        self._viewport = _check_viewport(value)
        self._sync_viewport()

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
        self._sync_flags()

    @property
    def layer(self):
        return self._layer

    @layer.setter
    def layer(self, value):
        self._layer = value
        self._sync_layer()

    def hide(self):
        self.visible = False

    def show(self):
        self.visible = True


def _check_viewport(value):
    viewport_x, viewport_y, viewport_w, viewport_h = value
    viewport_x = int(viewport_x)
    viewport_y = int(viewport_y)
    viewport_w = int(viewport_w)
    viewport_h = int(viewport_h)
    if viewport_x < 0 or viewport_y < 0 or viewport_w <= 0 or viewport_h <= 0:
        raise ValueError("invalid viewport")
    if (
        viewport_x > 0xFFFF
        or viewport_y > 0xFFFF
        or viewport_w > 0xFFFF
        or viewport_h > 0xFFFF
    ):
        raise ValueError("invalid viewport")
    return (viewport_x, viewport_y, viewport_w, viewport_h)


def _intersects(x1, w1, x2, w2):
    delta = min(x1, x2)
    x1 = (x1 - delta + 128) % 256
    x2 = (x2 - delta + 128) % 256
    return x1 < x2 + w2 and x1 + w1 > x2
