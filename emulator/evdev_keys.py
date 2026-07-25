"""Raw-evdev keyboard state for console/no-display builds (see consoleengine.py).

Console mode never creates a pyglet.window.Window -- the Base's console has
no X11/EGL context to back one, only the spinning board's LEDs are the
display. Without a window there is no event queue to dispatch key-down/up
into, so pyglet.window.key.KeyStateHandler (what pyglet1x/pyglet2x's
inputs.py use in the windowed desktop build) isn't available. The arcade
panel's button encoder presents as a plain USB HID keyboard, so this reads
it directly off /dev/input/eventN instead and exposes the same
keys[pyglet_symbol] -> bool interface inputs_common.keyboard_state() and
keyboard_v2_state() expect, so those functions work unmodified either way.

Importing this module requires pyglet.options['shadow_window'] to already
be False (set in consoleengine.py before any of these imports run) --
otherwise the `from pyglet.window import key` below drags in a live X11
connection attempt. See consoleengine.py's module docstring.
"""

try:
    import evdev
    from evdev import ecodes
except ImportError:
    evdev = None
    ecodes = None

from pyglet.window import key as pygkey

_EVDEV_TO_PYGLET = {}
if evdev is not None:
    _EVDEV_TO_PYGLET = {
        ecodes.KEY_LEFT: pygkey.LEFT,
        ecodes.KEY_RIGHT: pygkey.RIGHT,
        ecodes.KEY_UP: pygkey.UP,
        ecodes.KEY_DOWN: pygkey.DOWN,
        ecodes.KEY_A: pygkey.A,
        ecodes.KEY_D: pygkey.D,
        ecodes.KEY_W: pygkey.W,
        ecodes.KEY_S: pygkey.S,
        ecodes.KEY_SPACE: pygkey.SPACE,
        ecodes.KEY_O: pygkey.O,
        ecodes.KEY_P: pygkey.P,
        ecodes.KEY_H: pygkey.H,
        ecodes.KEY_J: pygkey.J,
        ecodes.KEY_K: pygkey.K,
        ecodes.KEY_L: pygkey.L,
        ecodes.KEY_Z: pygkey.Z,
        ecodes.KEY_X: pygkey.X,
        ecodes.KEY_C: pygkey.C,
        ecodes.KEY_V: pygkey.V,
        ecodes.KEY_Y: pygkey.Y,
        ecodes.KEY_PAGEUP: pygkey.PAGEUP,
        ecodes.KEY_PAGEDOWN: pygkey.PAGEDOWN,
        ecodes.KEY_HOME: pygkey.HOME,
        ecodes.KEY_END: pygkey.END,
        ecodes.KEY_ESC: pygkey.ESCAPE,
    }

_UP, _DOWN, _REPEAT = 0, 1, 2

# A candidate device needs at least this many of the mapped keys present to
# count as "a keyboard" during auto-detect -- filters out oddities (power
# buttons, single media-key devices) that also emit EV_KEY without being
# the arcade panel's encoder.
_MIN_MATCHING_KEYS = 10


class NullKeyState:
    """Stand-in when evdev is unavailable or no device was found: every key
    reads as not-pressed, matching pyglet's KeyStateHandler default."""

    def poll(self):
        pass

    def __getitem__(self, symbol):
        return False


class EvdevKeyState:
    """keys[pyglet_symbol] -> bool, backed by polling one evdev device."""

    def __init__(self, device_path):
        self._device = evdev.InputDevice(device_path)
        self._pressed = set()
        print(f"evdev_keys: reading keyboard from {device_path} ({self._device.name})")

    def poll(self):
        """Drain pending events. Call once per tick before reading state."""
        try:
            for event in self._device.read():
                if event.type != ecodes.EV_KEY:
                    continue
                symbol = _EVDEV_TO_PYGLET.get(event.code)
                if symbol is None:
                    continue
                if event.value == _UP:
                    self._pressed.discard(symbol)
                elif event.value in (_DOWN, _REPEAT):
                    self._pressed.add(symbol)
        except BlockingIOError:
            pass

    def __getitem__(self, symbol):
        return symbol in self._pressed


def _looks_like_keyboard(device):
    keys = device.capabilities().get(ecodes.EV_KEY, [])
    return len(set(keys) & set(_EVDEV_TO_PYGLET)) >= _MIN_MATCHING_KEYS


def find_device(name_substring=None):
    """Return an evdev device path for the arcade panel's keyboard encoder,
    or None. With name_substring, matches the first device whose name
    contains it (case-insensitive); otherwise auto-detects the first
    device exposing a broad keyboard-like key range."""
    if evdev is None:
        return None

    candidates = []
    for path in evdev.list_devices():
        try:
            candidates.append((path, evdev.InputDevice(path)))
        except OSError:
            continue

    if name_substring:
        needle = name_substring.lower()
        for path, device in candidates:
            if needle in device.name.lower():
                return path
        return None

    for path, device in candidates:
        if _looks_like_keyboard(device):
            return path
    return None


def open_keyboard(name_substring=None):
    """Build the keys[] state for console mode. Falls back to a no-op
    NullKeyState (all keys unpressed) if evdev is unavailable or no
    matching device is found -- mirrors inputs_common.py's RPi.GPIO
    fallback for dev machines without the real peripheral."""
    if evdev is None:
        print("evdev_keys: evdev not installed; keyboard input disabled")
        return NullKeyState()
    try:
        path = find_device(name_substring)
    except Exception as error:
        print("evdev_keys: device scan failed:", error)
        return NullKeyState()
    if path is None:
        print("evdev_keys: no keyboard device found; keyboard input disabled")
        return NullKeyState()
    try:
        return EvdevKeyState(path)
    except Exception as error:
        print("evdev_keys: failed to open", path, "-", error)
        return NullKeyState()
