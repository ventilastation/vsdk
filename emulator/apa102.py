"""APA102 drive-value decoding for the desktop preview."""

from color_profile import DEFAULT_PROFILE


def decode_preview_rgb(global_byte, blue_pwm, green_pwm, red_pwm, profile=None):
    """Return monitor-sRGB bytes for one raw APA102 LED frame."""
    return (profile or DEFAULT_PROFILE).decode_preview_rgb(global_byte, blue_pwm, green_pwm, red_pwm)
