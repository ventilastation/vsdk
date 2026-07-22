"""Short-lived synthetic video shown while the USB workbench is absent.

The glyphs and polar placement match the MicroPython ROM browser's
``tinyfont_menu.png`` and retro-go's native Ventilastation dialog renderer.
Only the glyphs needed by the fixed message are embedded here, keeping the
headless gateway independent of Pillow and runtime ROM assets.
"""

from __future__ import annotations


COLUMNS = 256
LEDS = 54
MESSAGE = "board unplugged"
GLYPH_WIDTH = 3
GLYPH_HEIGHT = 6
CHAR_STEP = 4
ROW_STEP = GLYPH_HEIGHT + 3
ANIMATION_INTERVAL_S = 0.5
TRANSMISSION_DURATION_S = 60.0
MESSAGE_COLOR = (255, 0, 0)

# Generated from system/shared/other/images/tinyfont_white.png by the same
# extraction used by tools/generate_tinyfont_c.py. Each tuple is six rows;
# bit 2 is the leftmost of the three usable glyph columns.
TINY_FONT = {
    " ": (0, 0, 0, 0, 0, 0),
    "a": (0, 3, 5, 5, 3, 0),
    "b": (4, 6, 5, 5, 6, 0),
    "d": (1, 3, 5, 5, 3, 0),
    "e": (0, 2, 5, 6, 3, 0),
    "g": (0, 2, 5, 3, 1, 2),
    "l": (2, 2, 2, 2, 1, 0),
    "n": (0, 6, 5, 5, 5, 0),
    "o": (0, 2, 5, 5, 2, 0),
    "p": (0, 6, 5, 5, 6, 4),
    "r": (0, 2, 5, 4, 4, 0),
    "u": (0, 5, 5, 5, 3, 0),
}


def render_unplugged_frame(
    y_offset: int = 0,
    *,
    from_outermost_led: bool = False,
) -> bytes:
    """Render the warning in native column-major ``[angle][LED][RGB]`` order."""
    frame = bytearray(COLUMNS * LEDS * 3)
    angle_start = -(len(MESSAGE) * CHAR_STEP) // 2
    # This is native-dialog row zero: the outermost, most legible radial row.
    row_base_led = (
        LEDS - 1 if from_outermost_led else LEDS - ROW_STEP + y_offset
    )
    for index, character in enumerate(MESSAGE):
        # Both character order and each glyph's x axis are mirrored exactly as
        # in retro-go's ventilastation_pov.c hardware-confirmed mapping.
        glyph_angle = angle_start + (len(MESSAGE) - 1 - index) * CHAR_STEP
        for row, bits in enumerate(TINY_FONT[character]):
            led = row_base_led - row if from_outermost_led else row_base_led + row
            if not 0 <= led < LEDS:
                continue
            for glyph_x in range(GLYPH_WIDTH):
                if not bits & (1 << (GLYPH_WIDTH - 1 - glyph_x)):
                    continue
                column = (glyph_angle - glyph_x) % COLUMNS
                offset = (column * LEDS + led) * 3
                frame[offset:offset + 3] = bytes(MESSAGE_COLOR)
    return bytes(frame)


class UnpluggedFrameStream:
    """Emit a bobbing warning twice a second, for at most one minute."""

    def __init__(
        self,
        interval_s: float = ANIMATION_INTERVAL_S,
        duration_s: float = TRANSMISSION_DURATION_S,
    ) -> None:
        self.interval_s = interval_s
        self.duration_s = duration_s
        self.connected = True
        self.disconnected_at: float | None = None
        self._last_phase: int | None = None
        self._frames = (render_unplugged_frame(0), render_unplugged_frame(-1))
        self._final_frame = render_unplugged_frame(from_outermost_led=True)

    def set_connected(self, connected: bool, now: float) -> bool:
        connected = bool(connected)
        if connected == self.connected:
            return False
        self.connected = connected
        self._last_phase = None
        self.disconnected_at = None if connected else now
        return True

    def restart(self, now: float) -> bool:
        """Restart the warning window while the board remains disconnected."""
        if self.connected:
            return False
        self.disconnected_at = now
        self._last_phase = None
        return True

    def next_frame(self, now: float) -> bytes | None:
        if self.connected or self.disconnected_at is None:
            return None
        elapsed = max(0.0, now - self.disconnected_at)
        if elapsed >= self.duration_s:
            # Publish one terminal warning at the physical outer edge. The
            # latest-frame cache keeps it visible without continuing traffic.
            if self._last_phase == -1:
                return None
            self._last_phase = -1
            return self._final_frame
        phase = int(elapsed / self.interval_s)
        if phase == self._last_phase:
            return None
        self._last_phase = phase
        return self._frames[phase % len(self._frames)]

    def current_frame(self, now: float) -> bytes | None:
        """Return the frame a late viewer should see without restarting output."""
        if self.connected or self.disconnected_at is None:
            return None
        elapsed = max(0.0, now - self.disconnected_at)
        if elapsed >= self.duration_s:
            return self._final_frame
        phase = int(elapsed / self.interval_s)
        return self._frames[phase % len(self._frames)]
