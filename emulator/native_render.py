"""ctypes bridge to the real hardware VS2 renderer (gpu.c's render_vs2(),
the same code exercised by tests/native/test_render_vs2.c), built as
emulator/native/libvs2render.so.

povrender.py's pure-Python render()/render_tilemap() re-implements this same
logic for the desktop preview; this module lets the preview call the actual
tested C renderer instead, when the shared library has been built. If it's
missing (not yet built, or a platform without a C toolchain configured), all
functions here are no-ops / return None and povrender.py falls back to its
existing Python implementation unchanged.
"""
import ctypes
import os

import numpy as np

COLUMNS = 256
PIXELS = 54

_LIB_PATH = os.path.join(os.path.dirname(__file__), "native", "libvs2render.so")

available = False
_lib = None

# Keeps the raw wire buffer for the currently-active scene alive: the C side
# borrows pointers into it (tilemap frame tables), the same convention
# vs2_tilemap_t.frames uses on real hardware.
_active_scene_bytes = None


def _load():
    global available, _lib
    try:
        lib = ctypes.CDLL(_LIB_PATH)
    except OSError:
        return

    lib.emu_gpu_init.argtypes = []
    lib.emu_gpu_init.restype = None
    lib.emu_gpu_step_starfield.argtypes = []
    lib.emu_gpu_step_starfield.restype = None
    lib.emu_gpu_set_palette.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.emu_gpu_set_palette.restype = ctypes.c_bool
    lib.emu_gpu_set_image_strip.argtypes = [ctypes.c_int, ctypes.c_char_p]
    lib.emu_gpu_set_image_strip.restype = ctypes.c_bool
    lib.emu_gpu_clear_image_strip.argtypes = [ctypes.c_int]
    lib.emu_gpu_clear_image_strip.restype = None
    lib.emu_gpu_decode_scene.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.emu_gpu_decode_scene.restype = ctypes.c_bool
    lib.emu_gpu_clear_scene.argtypes = []
    lib.emu_gpu_clear_scene.restype = None
    lib.emu_gpu_render_frame.argtypes = [ctypes.POINTER(ctypes.c_uint32)]
    lib.emu_gpu_render_frame.restype = None
    lib.emu_gpu_set_legacy_sprites.argtypes = [ctypes.c_char_p]
    lib.emu_gpu_set_legacy_sprites.restype = None
    lib.emu_gpu_render_legacy_frame.argtypes = [ctypes.POINTER(ctypes.c_uint32)]
    lib.emu_gpu_render_legacy_frame.restype = None

    lib.emu_gpu_init()
    _lib = lib
    available = True


_load()

_frame_buffer = np.empty(COLUMNS * PIXELS, dtype=np.uint32) if available else None
_frame_buffer_ptr = (
    _frame_buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32)) if available else None
)


def step_starfield():
    if available:
        _lib.emu_gpu_step_starfield()


def set_palette(paldata):
    if available:
        _lib.emu_gpu_set_palette(bytes(paldata), len(paldata))


def set_image_strip(slot, data):
    if available:
        _lib.emu_gpu_set_image_strip(slot, bytes(data))


def clear_image_strip(slot):
    if available:
        _lib.emu_gpu_clear_image_strip(slot)


def decode_scene(data):
    """Parse a raw VS2 scene wire buffer. Keeps `data` alive as long as it's
    the active scene; tilemap frame tables borrow pointers into it."""
    global _active_scene_bytes
    if not available:
        return False
    data = bytes(data)
    ok = _lib.emu_gpu_decode_scene(data, len(data))
    if ok:
        _active_scene_bytes = data
    return ok


def clear_scene():
    global _active_scene_bytes
    if available:
        _lib.emu_gpu_clear_scene()
    _active_scene_bytes = None


def render_frame():
    """Render all 256 columns of the VS2-scene path. Returns a numpy uint32
    array (COLUMNS*PIXELS) of packed 0xAABBGGRR pixels, or None if the native
    library isn't built."""
    if not available:
        return None
    _lib.emu_gpu_render_frame(_frame_buffer_ptr)
    return _frame_buffer


def set_legacy_sprites(data):
    """Install the pre-VS2 fixed 100-sprite-slot table (povrender.spritedata's
    5-bytes-per-slot layout: x, y, image_strip_index, frame, perspective)."""
    if available:
        _lib.emu_gpu_set_legacy_sprites(bytes(data))


def render_legacy_frame():
    """Render all 256 columns of the pre-VS2 fixed-sprite-slot path. Returns
    a numpy uint32 array (COLUMNS*PIXELS), or None if not built."""
    if not available:
        return None
    _lib.emu_gpu_render_legacy_frame(_frame_buffer_ptr)
    return _frame_buffer
