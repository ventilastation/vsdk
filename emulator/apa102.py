"""APA102 drive-value decoding for the desktop preview.

Workbench capture is deliberately lossless: the incoming LED datum is
``[0xe0 | global_brightness, B, G, R]``.  The default decoder below models a
linear PWM/current response and converts the resulting relative light to
sRGB.  A board colour profile will replace these response curves and add its
measured LED-to-preview matrix without changing callers or the wire format.
"""


def _srgb_encode(linear):
    if linear <= 0.0:
        return 0
    if linear >= 1.0:
        return 255
    if linear <= 0.0031308:
        encoded = linear * 12.92
    else:
        encoded = 1.055 * pow(linear, 1.0 / 2.4) - 0.055
    return max(0, min(255, int(encoded * 255.0 + 0.5)))


def decode_preview_rgb(global_byte, blue_pwm, green_pwm, red_pwm):
    """Return monitor-sRGB bytes for one raw APA102 LED frame.

    The APA102 global control is shared by the three PWM channels. Values
    whose leading bits are not the normal ``111`` frame prefix are treated as
    off so malformed telemetry cannot turn into a bright preview artefact.
    """
    if (global_byte & 0xE0) != 0xE0:
        return (0, 0, 0)
    brightness = global_byte & 0x1F
    if brightness == 0:
        return (0, 0, 0)
    scale = brightness / 31.0 / 255.0
    return (
        _srgb_encode(red_pwm * scale),
        _srgb_encode(green_pwm * scale),
        _srgb_encode(blue_pwm * scale),
    )
