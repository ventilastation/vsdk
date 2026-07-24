"""APA102 drive-value decoding for the desktop preview.

numpy is imported lazily inside the functions below, not at module level:
this module (via povrender.py) is on comms.py's always-imported path, and
the headless Raspberry Pi base -- which never decodes a preview frame --
doesn't have numpy installed.
"""

try:  # Package import used by the headless remote gateway.
    from .color_profile import DEFAULT_PROFILE, MATRIX_Q, Q15_ONE, _srgb_encode
except ImportError:  # Direct ``python emulator/...`` tools retain their path.
    from color_profile import DEFAULT_PROFILE, MATRIX_Q, Q15_ONE, _srgb_encode


def decode_preview_rgb(global_byte, blue_pwm, green_pwm, red_pwm, profile=None):
    """Return monitor-sRGB bytes for one raw APA102 LED frame."""
    return (profile or DEFAULT_PROFILE).decode_preview_rgb(global_byte, blue_pwm, green_pwm, red_pwm)


_SRGB_LUT_BITS = 12
_SRGB_LUT_SIZE = 1 << _SRGB_LUT_BITS
# Quantized linear-light -> sRGB byte table. Avoids a Python-level pow() call
# per pixel per channel in the vectorized decoder below.
_srgb_lut_cache = None


def _srgb_lut():
    global _srgb_lut_cache
    if _srgb_lut_cache is None:
        import numpy as np
        _srgb_lut_cache = np.array(
            [_srgb_encode(i / (_SRGB_LUT_SIZE - 1)) for i in range(_SRGB_LUT_SIZE)],
            dtype=np.uint8,
        )
    return _srgb_lut_cache


# Per-profile numpy tables for decode_frame, keyed by profile identity so a
# calibration update naturally invalidates the cache (profiles are immutable,
# a new one is always a new object).
_frame_tables_cache = None


def _tables_for_profile(profile):
    import numpy as np
    global _frame_tables_cache
    if _frame_tables_cache is not None and _frame_tables_cache[0] is profile:
        return _frame_tables_cache[1]
    pwm_lut = np.array(profile.pwm_byte_lut, dtype=np.float64)  # shape (3, 256)
    global_response = np.array(profile.global_response, dtype=np.float64)  # shape (32,)
    matrix = np.array(profile.preview_matrix, dtype=np.float64).reshape(3, 3)
    tables = (pwm_lut, global_response, matrix)
    _frame_tables_cache = (profile, tables)
    return tables


def decode_frame(raw, profile=None):
    """Vectorized decode of one full captured frame of raw APA102 data.

    `raw` is a flat buffer of 4-byte [GB, B, G, R] APA102 data (as produced by
    the workbench capture). Returns a flat numpy uint32 array of packed
    0xFF__BBGGRR pixel values, one entry per input LED datum, in the same
    order as `raw`. This does the same math as ColorProfile.decode_preview_rgb
    but over the whole frame at once, which is what makes it fast enough to
    run per captured frame instead of per rendered pixel.
    """
    import numpy as np
    profile = profile or DEFAULT_PROFILE
    pwm_lut, global_response, matrix = _tables_for_profile(profile)

    arr = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 4)
    gb, blue_pwm, green_pwm, red_pwm = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]

    valid = (gb & 0xE0) == 0xE0
    brightness = (gb & 0x1F).astype(np.int64)
    global_light = np.where(valid & (brightness > 0), global_response[brightness], 0.0)

    scale = 1.0 / (Q15_ONE * Q15_ONE)
    led_light = np.stack(
        (
            global_light * pwm_lut[0][red_pwm] * scale,
            global_light * pwm_lut[1][green_pwm] * scale,
            global_light * pwm_lut[2][blue_pwm] * scale,
        ),
        axis=1,
    )
    preview_linear = np.maximum(led_light @ matrix.T / MATRIX_Q, 0.0)

    clamped = np.clip(preview_linear, 0.0, 1.0)
    index = (clamped * (_SRGB_LUT_SIZE - 1) + 0.5).astype(np.int32)
    channels = _srgb_lut()[index]  # shape (N, 3): R, G, B bytes

    r = channels[:, 0].astype(np.uint32)
    g = channels[:, 1].astype(np.uint32)
    b = channels[:, 2].astype(np.uint32)
    return np.uint32(0xFF000000) | (b << 16) | (g << 8) | r
