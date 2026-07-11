"""Shared, safe model for the optional Ventilastation base peripherals."""

BUTTON_LED_1 = 0x01
BUTTON_LED_2 = 0x02
BUTTON_LED_ALL = BUTTON_LED_1 | BUTTON_LED_2
MIN_BLINK_MS = 100
MAX_BLINK_MS = 10000


def gamma_correct(value):
    """The base strip's 2.2 output transfer curve, matching the Arduino LUT."""
    return int(255 * (int(value) / 255) ** 2.2 + 0.5)


class BaseControlState:
    """Normalized state accepted by previews and the Arduino forwarder.

    Servo calibration never enters this model: position is always a byte.
    """
    def __init__(self):
        self.rgb = (0, 0, 0)
        self.servo_position = 0
        self.button_mask = 0
        self.button_blink_ms = 0

    @staticmethod
    def _number(value, minimum, maximum):
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if minimum <= number <= maximum else None

    def apply(self, args):
        """Apply `base` command arguments and return its canonical wire line."""
        if not args:
            return None
        command = args[0].decode("ascii", "ignore") if isinstance(args[0], bytes) else str(args[0])
        values = args[1:]
        if command == "leds" and len(values) == 3:
            rgb = tuple(self._number(value, 0, 255) for value in values)
            if None in rgb:
                return None
            self.rgb = rgb
            return "base leds %d %d %d\n" % rgb
        if command == "servo" and len(values) == 1:
            position = self._number(values[0], 0, 255)
            if position is None:
                return None
            self.servo_position = position
            return "base servo %d\n" % position
        if command == "buttons" and len(values) == 2:
            mask = self._number(values[0], 0, BUTTON_LED_ALL)
            blink_ms = self._number(values[1], 0, MAX_BLINK_MS)
            if mask is None or blink_ms is None:
                return None
            if blink_ms:
                blink_ms = max(MIN_BLINK_MS, blink_ms)
            self.button_mask = mask
            self.button_blink_ms = blink_ms
            return "base buttons %d %d\n" % (mask, blink_ms)
        return None

    def button_lit(self, mask, now_ms):
        if not (self.button_mask & mask):
            return False
        if not self.button_blink_ms:
            return True
        return (int(now_ms) % self.button_blink_ms) < (self.button_blink_ms // 2)

    @property
    def led_rgb(self):
        return tuple(gamma_correct(value) for value in self.rgb)
