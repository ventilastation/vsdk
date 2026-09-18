"""Interactive protocol for the "LED Usage" diagnostic app (system/led_usage).

Holds a static, byte-exact LED pattern (count of LEDs lit, growing from the
rotor's shared centre LED outward, a pinned RGB colour, and the APA102
global-brightness value) so someone can measure real current draw under a
controlled load. Mirrors color_calibration.py's handle_command/send_state
shape, but there is no persistence here -- values live only while the app
is active.
"""

COUNT_MAX = 107
CHANNEL_MAX = 255
GLOBAL_MAX = 31

_active = False
_count = 0
_r = 0
_g = 0
_b = 0
_global = 0


def _apply(display):
    """Install the current state into a hardware display if it supports it.

    Desktop/browser platforms have no such display method -- this is a
    silent no-op there, same as color_calibration._apply_payload, so the
    app/panel/protocol still work for wiring and testing without a board.
    """
    setter = getattr(display, "set_led_usage", None)
    if setter is not None:
        setter(_active, _count, _r, _g, _b, _global)


def send_state(send):
    """Announce the current state through a platform comms ``send(line)``."""
    send(b"ledusage_state %d %d %d %d %d %d" % (
        1 if _active else 0, _count, _r, _g, _b, _global))


def _send_error(send, message):
    send(("ledusage_error %s" % message).encode())


def _integer(value, name, minimum, maximum):
    try:
        parsed = int(value)
    except Exception:
        raise ValueError("invalid %s" % name)
    if parsed < minimum or parsed > maximum:
        raise ValueError("%s outside %d..%d" % (name, minimum, maximum))
    return parsed


def activate(display, send, count=0, r=0, g=0, b=0, global_brightness=16):
    global _active, _count, _r, _g, _b, _global
    _active = True
    _count, _r, _g, _b, _global = count, r, g, b, global_brightness
    _apply(display)
    send_state(send)


def deactivate(display, send):
    global _active
    _active = False
    _apply(display)
    send_state(send)


def handle_command(parts, send, display=None):
    """Handle the interactive ``ledusage`` protocol."""
    if parts == ["get"]:
        send_state(send)
        return True
    if not parts:
        _send_error(send, "missing_command")
        return True
    global _count, _r, _g, _b, _global
    try:
        command = parts[0]
        if command == "set":
            if not _active:
                raise ValueError("led usage app is not running")
            if len(parts) != 6:
                raise ValueError("set expects count r g b global")
            count = _integer(parts[1], "count", 0, COUNT_MAX)
            r = _integer(parts[2], "red", 0, CHANNEL_MAX)
            g = _integer(parts[3], "green", 0, CHANNEL_MAX)
            b = _integer(parts[4], "blue", 0, CHANNEL_MAX)
            global_brightness = _integer(parts[5], "global", 0, GLOBAL_MAX)
            _count, _r, _g, _b, _global = count, r, g, b, global_brightness
            _apply(display)
        else:
            raise ValueError("unsupported command")
    except Exception as error:
        print("led_usage:", error)
        _send_error(send, "invalid_value")
        return True
    send_state(send)
    return True
