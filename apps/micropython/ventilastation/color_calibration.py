"""Persistent POV colour-profile transport.

This module owns the versioned NVS blob exchanged with the emulator through
``povcal_state``. The native colour pipeline will consume the same blob when
it is added; keeping the format here free of display or scene dependencies
makes it safe to answer ``povcal get`` during early boot and on desktop.
"""

import struct


MAGIC = b"PCAL"
VERSION = 1
LED_COUNT = 54
PWM_KNOTS = 17
GB_LEVELS = 32
Q15_ONE = 32767
MATRIX_Q = 4096
NVS_NAMESPACE = "voom_pov"
NVS_KEY = "color_v1"

HEADER_FORMAT = "<4sBBHI"
CONTROLS_FORMAT = "<BHHHHHHBB"
MATRIX_FORMAT = "<9h"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
CONTROLS_SIZE = struct.calcsize(CONTROLS_FORMAT)
MATRIX_SIZE = struct.calcsize(MATRIX_FORMAT)
PROFILE_BYTES = (
    HEADER_SIZE + CONTROLS_SIZE + MATRIX_SIZE + LED_COUNT * 2
    + GB_LEVELS * 2 + 3 * PWM_KNOTS * 2
)

_loaded = False
_profile = None

_OFF_SOURCE_EOTF = HEADER_SIZE
_OFF_SOURCE_GAMMA = _OFF_SOURCE_EOTF + 1
_OFF_MASTER = _OFF_SOURCE_GAMMA + 2
_OFF_WHITE = _OFF_MASTER + 2
_OFF_RADIAL_EXPONENT = _OFF_WHITE + 6
_OFF_GB_FLOOR = _OFF_RADIAL_EXPONENT + 2
_OFF_GB_CEILING = _OFF_GB_FLOOR + 1
_OFF_LED_TRIMS = HEADER_SIZE + CONTROLS_SIZE + MATRIX_SIZE


def _linear_knots(count):
    denominator = 2 * (count - 1)
    return [(2 * index * Q15_ONE + (count - 1)) // denominator for index in range(count)]


def build_default(generation=0):
    """Return the canonical default v1 profile payload."""
    body = bytearray()
    body.extend(struct.pack(
        CONTROLS_FORMAT,
        0,       # source_eotf: sRGB
        2200,    # retained for the optional power-gamma profile
        1000,    # master brightness (milli)
        1000, 1000, 1000,
        1000,    # radial exponent (milli)
        1, 31,   # APA102 global-brightness floor/ceiling
    ))
    body.extend(struct.pack(MATRIX_FORMAT,
        MATRIX_Q, 0, 0,
        0, MATRIX_Q, 0,
        0, 0, MATRIX_Q,
    ))
    body.extend(struct.pack("<%dH" % LED_COUNT, *([1024] * LED_COUNT)))
    body.extend(struct.pack("<%dH" % GB_LEVELS, *_linear_knots(GB_LEVELS)))
    pwm = _linear_knots(PWM_KNOTS)
    for _ in range(3):
        body.extend(struct.pack("<%dH" % PWM_KNOTS, *pwm))
    payload = struct.pack(HEADER_FORMAT, MAGIC, VERSION, 0, PROFILE_BYTES, generation) + bytes(body)
    if len(payload) != PROFILE_BYTES:
        raise RuntimeError("colour profile layout drifted")
    return payload


def _header(payload):
    if len(payload) != PROFILE_BYTES:
        raise ValueError("invalid colour-profile length")
    magic, version, flags, length, generation = struct.unpack(HEADER_FORMAT, payload[:HEADER_SIZE])
    if magic != MAGIC or version != VERSION or flags != 0 or length != PROFILE_BYTES:
        raise ValueError("invalid colour-profile header")
    return version, generation


def _u16(payload, offset):
    return payload[offset] | (payload[offset + 1] << 8)


def _put_u16(payload, offset, value):
    payload[offset] = value & 0xff
    payload[offset + 1] = value >> 8


def _u32(payload, offset):
    return (payload[offset] | (payload[offset + 1] << 8)
            | (payload[offset + 2] << 16) | (payload[offset + 3] << 24))


def _put_u32(payload, offset, value):
    for index in range(4):
        payload[offset + index] = (value >> (8 * index)) & 0xff


def _read_nvs():
    try:
        import esp32
        buffer = bytearray(PROFILE_BYTES)
        size = esp32.NVS(NVS_NAMESPACE).get_blob(NVS_KEY, buffer)
        return bytes(buffer[:size])
    except Exception:
        return None


def _write_nvs(payload):
    try:
        import esp32
        nvs = esp32.NVS(NVS_NAMESPACE)
        nvs.set_blob(NVS_KEY, payload)
        nvs.commit()
        return True
    except Exception as error:
        print("color_calibration: NVS save failed:", error)
        return False


def load():
    """Load a valid NVS profile, otherwise use the canonical default."""
    global _loaded, _profile
    candidate = _read_nvs()
    if candidate is not None:
        try:
            _header(candidate)
            _profile = candidate
        except Exception:
            print("color_calibration: ignoring invalid NVS profile")
            _profile = build_default()
    else:
        _profile = build_default()
    _loaded = True
    return _profile


def active_profile():
    if not _loaded:
        load()
    return _profile


def profile_info():
    version, generation = _header(active_profile())
    return version, generation


def apply_to_display(display):
    """Install the active profile into a hardware display if it supports it."""
    _apply_payload(display, active_profile())


def _apply_payload(display, payload):
    setter = getattr(display, "set_color_profile", None)
    if setter is not None:
        setter(payload)


def send_state(send):
    """Send the active profile through a platform comms ``send(line, data)``."""
    payload = active_profile()
    version, generation = _header(payload)
    send(b"povcal_state %d %d %d" % (version, generation, len(payload)), payload)


def _set_active(payload, display):
    """Apply a complete candidate profile before publishing it as active."""
    global _profile, _loaded
    _header(payload)
    _apply_payload(display, payload)
    _profile = bytes(payload)
    _loaded = True


def _next_candidate():
    candidate = bytearray(active_profile())
    _put_u32(candidate, 8, (_u32(candidate, 8) + 1) & 0xffffffff)
    return candidate


def _integer(value, name, minimum, maximum):
    try:
        parsed = int(value)
    except Exception:
        raise ValueError("invalid %s" % name)
    if parsed < minimum or parsed > maximum:
        raise ValueError("%s outside %d..%d" % (name, minimum, maximum))
    return parsed


def _set_values(parts):
    if len(parts) < 2:
        raise ValueError("missing setting")
    key = parts[1]
    values = parts[2:]
    candidate = _next_candidate()
    if key == "source_eotf":
        if values == ["srgb"]:
            candidate[_OFF_SOURCE_EOTF] = 0
        elif len(values) == 2 and values[0] == "power":
            candidate[_OFF_SOURCE_EOTF] = 1
            _put_u16(candidate, _OFF_SOURCE_GAMMA,
                     _integer(values[1], "source gamma", 1000, 4000))
        else:
            raise ValueError("source_eotf expects srgb or power <milli-gamma>")
    elif key == "master" and len(values) == 1:
        _put_u16(candidate, _OFF_MASTER, _integer(values[0], "master", 0, 4000))
    elif key == "white" and len(values) == 3:
        for channel, value in enumerate(values):
            _put_u16(candidate, _OFF_WHITE + channel * 2,
                     _integer(value, "white gain", 0, 4000))
    elif key == "radial_exponent" and len(values) == 1:
        _put_u16(candidate, _OFF_RADIAL_EXPONENT,
                 _integer(values[0], "radial exponent", 0, 4000))
    elif key == "led_gain" and len(values) == 2:
        led = _integer(values[0], "LED index", 0, LED_COUNT - 1)
        _put_u16(candidate, _OFF_LED_TRIMS + led * 2,
                 _integer(values[1], "LED gain", 0, 4096))
    elif key == "gb_floor" and len(values) == 1:
        floor = _integer(values[0], "GB floor", 0, 31)
        if floor > candidate[_OFF_GB_CEILING]:
            raise ValueError("GB floor exceeds ceiling")
        candidate[_OFF_GB_FLOOR] = floor
    elif key == "gb_ceiling" and len(values) == 1:
        ceiling = _integer(values[0], "GB ceiling", 0, 31)
        if ceiling < candidate[_OFF_GB_FLOOR]:
            raise ValueError("GB ceiling is below floor")
        candidate[_OFF_GB_CEILING] = ceiling
    else:
        raise ValueError("unsupported setting")
    return candidate


def _send_error(send, code):
    try:
        _, generation = profile_info()
    except Exception:
        generation = 0
    send(b"povcal_error %d %s" % (generation, code))


def handle_command(parts, send, display=None):
    """Handle the interactive ``povcal`` protocol.

    All edits are applied to the renderer first. ``commit`` alone persists
    them, keeping slider interaction responsive without NVS write wear.
    """
    if parts == ["get"]:
        send_state(send)
        return True
    if not parts:
        _send_error(send, b"missing_command")
        return True
    try:
        command = parts[0]
        if command == "set":
            _set_active(_set_values(parts), display)
        elif command == "commit":
            if not _write_nvs(active_profile()):
                _send_error(send, b"nvs_write_failed")
                return True
        elif command == "revert":
            stored = _read_nvs()
            if stored is None:
                raise ValueError("no persisted profile")
            _header(stored)
            _set_active(stored, display)
        elif command == "factory":
            _set_active(build_default((_u32(active_profile(), 8) + 1) & 0xffffffff), display)
        else:
            raise ValueError("unsupported command")
    except Exception as error:
        print("color_calibration:", error)
        _send_error(send, b"invalid_value")
        return True
    send_state(send)
    return True
