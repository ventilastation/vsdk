"""Raw-evdev keyboard state for console/no-display builds (see consoleengine.py).

Console mode never creates a pyglet.window.Window -- the Base's console has
no X11/EGL context to back one, only the spinning board's LEDs are the
display. Without a window there is no event queue to dispatch key-down/up
into, so pyglet.window.key.KeyStateHandler (what pyglet1x/pyglet2x's
inputs.py use in the windowed desktop build) isn't available. The arcade
panel's button encoder(s) present as plain USB HID keyboards, so this reads
them directly off /dev/input/eventN instead and exposes the same
keys[pyglet_symbol] -> bool interface inputs_common.keyboard_state() and
keyboard_v2_state() expect, so those functions work unmodified either way.

MultiKeyState supports any number of keyboard-like devices at once (their
pressed keys are simply ORed together) and hot-plugs them: newly attached
matching devices are picked up on the next periodic rescan, and a device
that errors out on read (unplugged) is dropped without taking the rest of
the engine down. This matters for a 2-player cabinet with one encoder per
player, and for testing where a device gets connected after the process
already started.

Importing this module requires pyglet.options['shadow_window'] to already
be False (set in emu.py before any pyglet-touching import runs, including
comms.py) -- otherwise the `from pyglet.window import key` below drags in
a live X11 connection attempt. See consoleengine.py's module docstring.
"""

import time

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

# How often to re-scan /dev/input for newly attached (or gone) matching
# devices. Listing + opening every node isn't free, so this is throttled
# rather than done every tick; a device going away is still noticed
# immediately, on the very next read, regardless of this interval.
_RESCAN_INTERVAL_S = 2.0


def _is_joystick_like(device):
    """True for anything that looks like a joystick/gamepad interface.

    Cheap USB gamepads are exactly the kind of device that can otherwise
    pass the keyboard check below (many report a real KEY_* range for
    D-pad/buttons alongside their axes) -- this keeps one from being
    grabbed as "a keyboard" and losing pyglet's own Controller/Joystick
    handling of it, and from taking the whole engine down via
    MultiKeyState the moment it's unplugged.
    """
    caps = device.capabilities()
    if ecodes.EV_ABS in caps:
        return True
    return any(code >= ecodes.BTN_JOYSTICK for code in caps.get(ecodes.EV_KEY, []))


def _looks_like_keyboard(device):
    keys = set(device.capabilities().get(ecodes.EV_KEY, []))
    if len(keys & set(_EVDEV_TO_PYGLET)) < _MIN_MATCHING_KEYS:
        return False
    return not _is_joystick_like(device)


class MultiKeyState:
    """keys[pyglet_symbol] -> bool, backed by any number of hot-pluggable
    evdev keyboard-like devices, ORed together. Safe to use even with no
    matching device present (or evdev not installed): every key just reads
    as not-pressed, matching pyglet's KeyStateHandler default."""

    def __init__(self, name_substring=None):
        self._name_substring = name_substring
        self._devices = {}  # path -> (evdev.InputDevice, {pressed pyglet symbols})
        self._last_scan = 0.0
        self._rescan()

    def _matches(self, device):
        if self._name_substring:
            return self._name_substring.lower() in device.name.lower()
        return _looks_like_keyboard(device)

    def _rescan(self):
        self._last_scan = time.monotonic()
        if evdev is None:
            return
        try:
            live_paths = set(evdev.list_devices())
        except OSError as error:
            print("evdev_keys: device scan failed:", error)
            return
        for path in live_paths - self._devices.keys():
            try:
                device = evdev.InputDevice(path)
                if not self._matches(device):
                    continue
            except OSError:
                continue
            print(f"evdev_keys: keyboard connected: {path} ({device.name})")
            self._devices[path] = (device, set())

    def poll(self):
        """Drain pending events on every open device, dropping any that
        error out (unplugged). Also re-scans for newly attached devices,
        throttled to _RESCAN_INTERVAL_S. Call once per tick."""
        if time.monotonic() - self._last_scan >= _RESCAN_INTERVAL_S:
            self._rescan()

        dead = []
        for path, (device, pressed) in self._devices.items():
            try:
                for event in device.read():
                    if event.type != ecodes.EV_KEY:
                        continue
                    symbol = _EVDEV_TO_PYGLET.get(event.code)
                    if symbol is None:
                        continue
                    if event.value == _UP:
                        pressed.discard(symbol)
                    elif event.value in (_DOWN, _REPEAT):
                        pressed.add(symbol)
            except BlockingIOError:
                pass
            except OSError:
                print(f"evdev_keys: keyboard disconnected: {path} ({device.name})")
                dead.append(path)
        for path in dead:
            del self._devices[path]

    def __getitem__(self, symbol):
        return any(symbol in pressed for _device, pressed in self._devices.values())
