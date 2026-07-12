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


def _read_nvs():
    try:
        import esp32
        buffer = bytearray(PROFILE_BYTES)
        size = esp32.NVS(NVS_NAMESPACE).get_blob(NVS_KEY, buffer)
        return bytes(buffer[:size])
    except Exception:
        return None


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


def send_state(send):
    """Send the active profile through a platform comms ``send(line, data)``."""
    payload = active_profile()
    version, generation = _header(payload)
    send(b"povcal_state %d %d %d" % (version, generation, len(payload)), payload)


def handle_command(parts, send):
    """Handle the implemented read-only portion of the ``povcal`` protocol.

    Editing/committing is intentionally deferred until the renderer can apply
    a new profile atomically. Returning success for an unapplied change would
    make the emulator sliders lie about the physical LEDs.
    """
    if parts == ["get"]:
        send_state(send)
        return True
    return False
