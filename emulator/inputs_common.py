"""Input helpers shared by the pyglet 1.x and 2.x backends.

Owns everything that does not depend on the pyglet version: the Super
Ventilagon base's GPIO buttons, the keyboard mapping, and packing the
final joy1/extra bitmask (bit layout matches Director.JOY_*/BUTTON_*).
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
    """Return (left, right, up, down, boton, accel, decel) from the keyboard
    and the base's GPIO buttons -- the fallback when no game controller is
    connected, and OR-ed with the controller state when one is."""
    return (
        keys[key.LEFT] or keys[key.A] or base_button_left(),
        keys[key.RIGHT] or keys[key.D] or base_button_right(),
        keys[key.UP] or keys[key.W],
        keys[key.DOWN] or keys[key.S],
        keys[key.SPACE],
        keys[key.PAGEUP] or keys[key.P],
        keys[key.PAGEDOWN] or keys[key.O],
    )


def pack_input(left, right, up, down, boton, accel, decel, reset):
    joy1 = (bool(left) << 0 | bool(right) << 1 | bool(up) << 2 | bool(down) << 3 |
            bool(boton) << 4 | bool(accel) << 5 | bool(decel) << 6)
    extra = bool(reset) << 0   # BUTTON_D / EXTRA_BTN_0
    return joy1, extra
