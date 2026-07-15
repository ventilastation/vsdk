"""Input helpers shared by the pyglet 1.x and 2.x backends.

Owns everything that does not depend on the pyglet version: the Super
Ventilagon base's GPIO buttons, the keyboard mapping, and packing the
final joy1/joy2/extra bitmasks (bit layout matches Director.JOY_*/BUTTON_*).
"""

from pyglet.window import key

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

    Page Up and Page Down deliberately do not appear here: protocol v2 uses
    them for Joy1 Start and Back in ``keyboard_v2_state()``.
    """
    return (
        keys[key.LEFT] or keys[key.A] or base_button_left(),
        keys[key.RIGHT] or keys[key.D] or base_button_right(),
        keys[key.UP] or keys[key.W],
        keys[key.DOWN] or keys[key.S],
        keys[key.SPACE],
        keys[key.O],
        keys[key.P],
    )


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

    The layout keeps Joy1 close to the existing desktop controls while using
    the familiar H/J/K/L cursor cluster and Z/X/C/V face-button cluster for
    Joy2. Home/End provide Joy2 Start/Back without colliding with Joy1's
    Page Up/Page Down controls.
    """
    joy2 = pack_directions(
        keys[key.H], keys[key.L], keys[key.K], keys[key.J],
    )
    joy2 |= (bool(keys[key.Z]) << 4 |
             bool(keys[key.X]) << 5 |
             bool(keys[key.C]) << 6)
    extra = (bool(keys[key.Y]) * EXTRA_JOY1_Y |
             bool(keys[key.V]) * EXTRA_JOY2_Y |
             bool(keys[key.PAGEUP]) * EXTRA_JOY1_START |
             bool(keys[key.PAGEDOWN]) * EXTRA_JOY1_BACK |
             bool(keys[key.HOME]) * EXTRA_JOY2_START |
             bool(keys[key.END]) * EXTRA_JOY2_BACK)
    return joy2, extra


def ota_shortcut_pressed(symbol, modifiers):
    """Accept Ctrl-U everywhere and Command-U on macOS in both Pyglet APIs."""
    return symbol == key.U and bool(modifiers & (key.MOD_CTRL | key.MOD_COMMAND))


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
