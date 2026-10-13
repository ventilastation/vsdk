"""Input helpers shared by the pyglet 1.x and 2.x backends.

Owns everything that does not depend on the pyglet version: the Super
Ventilagon base's GPIO buttons, the keyboard mapping, and packing the
final joy1/joy2/extra bitmasks (bit layout matches Director.JOY_*/BUTTON_*).
"""

from pyglet.window import key
from keyboard_layout import KEYS

KEYBOARD_BINDINGS = [
    (tuple(getattr(key, name) for name in [entry["symbol"]] + entry.get("aliases", [])),
     entry["channel"], entry["bit"])
    for entry in KEYS
]


def _keyboard_channel(keys, channel):
    value = 0
    for symbols, target, bit in KEYBOARD_BINDINGS:
        if target == channel and any(keys[symbol] for symbol in symbols):
            value |= bit
    return value

try:
    # Physical buttons on the Super Ventilagon base (Raspberry Pi GPIO).
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup([9, 10], GPIO.IN, GPIO.PUD_UP)

    def base_button_left():
        return GPIO.input(9) == 0

    def base_button_right():
        return GPIO.input(10) == 0

except ImportError:
    def base_button_left():
        return False

    def base_button_right():
        return False


def keyboard_state(keys):
    """Return Joy1's first seven input bits from the keyboard and base GPIO.

    D, Select and Start live in the extra byte in ``keyboard_v2_state()``.
    """
    joy1 = _keyboard_channel(keys, "joy1")
    return (bool(joy1 & 1) or base_button_left(),
            bool(joy1 & 2) or base_button_right(),
            *(bool(joy1 & bit) for bit in (4, 8, 16, 32, 64)))


def pack_input(left, right, up, down, boton, accel, decel, reset):
    joy1 = (bool(left) << 0 | bool(right) << 1 | bool(up) << 2 | bool(down) << 3 |
            bool(boton) << 4 | bool(accel) << 5 | bool(decel) << 6)
    extra = bool(reset) << 0   # BUTTON_D / EXTRA_BTN_0
    return joy1, extra


# Input protocol v2 extra byte.  Bit 0 remains BUTTON_D for old
# MicroPython games; it is now driven by the first controller's face-Y
# button, rather than by Home/Guide.
EXTRA_JOY1_Y     = 0x01
EXTRA_JOY2_Y     = 0x02
EXTRA_JOY1_START = 0x04
EXTRA_JOY1_BACK  = 0x08
EXTRA_JOY2_START = 0x10
EXTRA_JOY2_BACK  = 0x20


def keyboard_v2_state(keys):
    """Return (joy2, extra) for keyboard-only Input Protocol v2 controls.

    Joy1 uses arrows and numpad 0/1/2/3 with numpad +/Enter for
    Select/Start. Joy2 uses WASD and Space/B/N/M with 1/2 for Select/Start.
    """
    return _keyboard_channel(keys, "joy2"), _keyboard_channel(keys, "extra")


class KeyboardHelpGate:
    """Keep help-preview keys out of gameplay until they have been released."""
    def __init__(self):
        self.blocked = set()

    def read(self, keys, help_open):
        held = {symbol for symbols, _, _ in KEYBOARD_BINDINGS for symbol in symbols if keys[symbol]}
        self.blocked.intersection_update(held)
        if help_open:
            self.blocked.update(held)
            return (False,) * 7, (0, 0)
        state = {symbol: symbol in held and symbol not in self.blocked
                 for symbols, _, _ in KEYBOARD_BINDINGS for symbol in symbols}
        return keyboard_state(state), keyboard_v2_state(state)


def ota_shortcut_pressed(symbol, modifiers):
    """Accept Ctrl-U everywhere and Command-U on macOS in both Pyglet APIs."""
    return symbol == key.U and bool(modifiers & (key.MOD_CTRL | key.MOD_COMMAND))


# Both symbol spellings of each modifier: which one a held key reads as
# depends on the pyglet backend, and console mode gets its own from
# evdev_keys' translation table rather than from pyglet at all.
OTA_MODIFIER_KEYS = (
    key.LCTRL, key.RCTRL, key.LCOMMAND, key.RCOMMAND, key.LMETA, key.RMETA,
)


def ota_shortcut_held(keys):
    """Same chord as ota_shortcut_pressed(), read from polled key state.

    Console mode never creates a window (see consoleengine.py), so nothing
    delivers on_key_press and there is no `modifiers` mask to test -- it polls
    evdev state instead. Keeping both forms here means the shortcut has one
    definition rather than drifting between the windowed and headless engines.
    """
    return bool(keys[key.U]) and any(bool(keys[symbol]) for symbol in OTA_MODIFIER_KEYS)


def pack_directions(left, right, up, down):
    return (bool(left) << 0 | bool(right) << 1 |
            bool(up) << 2 | bool(down) << 3)


def _value(controller, name, default=0):
    """Read a pyglet controller property without treating a missing mapping
    as a disconnected controller.  Generic HID devices often omit one or more
    optional controls."""
    try:
        value = getattr(controller, name)
        return default if value is None else value
    except (AttributeError, TypeError):
        return default


def _pressed(controller, name, threshold=0.5):
    """Read either a digital button or an analogue trigger as a button."""
    value = _value(controller, name)
    if isinstance(value, bool):
        return value
    try:
        return value > threshold
    except TypeError:
        return bool(value)


def controller_directions(controller, x_name, y_name, include_dpad=False, threshold=0.5):
    """Return the v2 direction nibble for one analogue stick.

    D-pad is deliberately only combined with the primary stick.  With one
    gamepad its right stick is joy2; with two gamepads the second controller's
    primary stick plus D-pad is joy2.
    """
    x = _value(controller, x_name)
    y = _value(controller, y_name)
    dpad_x = _value(_value(controller, "dpad", None), "x") if include_dpad else 0
    dpad_y = _value(_value(controller, "dpad", None), "y") if include_dpad else 0
    return pack_directions(
        x < -threshold or dpad_x < -threshold,
        x > threshold or dpad_x > threshold,
        y < -threshold or dpad_y > threshold,
        y > threshold or dpad_y < -threshold,
    )


def controller_buttons(controller, player):
    """Return (A/B/X bits, extra bits, home) for one standard controller."""
    face = (_pressed(controller, "a") << 4 |
            _pressed(controller, "b") << 5 |
            _pressed(controller, "x") << 6)
    if player == 1:
        extra = (EXTRA_JOY1_Y if _pressed(controller, "y") else 0)
        extra |= EXTRA_JOY1_START if _pressed(controller, "start") else 0
        extra |= EXTRA_JOY1_BACK if _pressed(controller, "back") else 0
    else:
        extra = (EXTRA_JOY2_Y if _pressed(controller, "y") else 0)
        extra |= EXTRA_JOY2_START if _pressed(controller, "start") else 0
        extra |= EXTRA_JOY2_BACK if _pressed(controller, "back") else 0
    return face, extra, _pressed(controller, "guide") or _pressed(controller, "home")


def primary_joy2_buttons(controller):
    """Use the spare shoulder/trigger controls as Joy2 ABXY for one pad."""
    face = (_pressed(controller, "leftshoulder") << 4 |
            _pressed(controller, "lefttrigger") << 5 |
            _pressed(controller, "rightshoulder") << 6)
    extra = EXTRA_JOY2_Y if _pressed(controller, "righttrigger") else 0
    return face, extra


def pack_controllers(primary, secondary=None, keyboard=(False,) * 7,
                     keyboard_v2=(0, 0)):
    """Encode up to two standard pyglet controllers into input protocol v2.

    A single controller contributes left-stick/D-pad to joy1 and right stick
    to joy2.  With two controllers, joy2 is the second controller's
    left-stick/D-pad, while the first right stick is ignored.
    """
    kb_left, kb_right, kb_up, kb_down, kb_a, kb_b, kb_x = keyboard
    kb_joy2, kb_extra = keyboard_v2
    joy1 = pack_directions(kb_left, kb_right, kb_up, kb_down)
    joy2 = 0
    extra = 0
    home = False

    if primary is not None:
        joy1 |= controller_directions(primary, "leftx", "lefty", include_dpad=True)
        face, extra_bits, home = controller_buttons(primary, 1)
        joy1 |= face
        extra |= extra_bits

    if secondary is None:
        if primary is not None:
            joy2 = controller_directions(primary, "rightx", "righty")
            face, extra_bits = primary_joy2_buttons(primary)
            joy2 |= face
            extra |= extra_bits
    else:
        joy2 = controller_directions(secondary, "leftx", "lefty", include_dpad=True)
        face, extra_bits, secondary_home = controller_buttons(secondary, 2)
        joy2 |= face
        extra |= extra_bits
        home = home or secondary_home

    joy1 |= (bool(kb_a) << 4 | bool(kb_b) << 5 | bool(kb_x) << 6)
    joy2 |= kb_joy2
    extra |= kb_extra
    return joy1, joy2, extra, home
