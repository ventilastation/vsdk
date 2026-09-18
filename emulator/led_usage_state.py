"""Host-side state reflected by acknowledged ``ledusage_state`` messages."""


class LedUsageState:
    """Keep the companion panel synchronized with the board, not optimistic
    guesses -- mirrors povcal_state.PovCalibrationState's shape."""

    def __init__(self):
        self.active = False
        self.count = 0
        self.r = 0
        self.g = 0
        self.b = 0
        self.global_brightness = 0
        self.error = None

    def apply(self, active, count, r, g, b, global_brightness):
        self.active = active
        self.count = count
        self.r = r
        self.g = g
        self.b = b
        self.global_brightness = global_brightness
        self.error = None

    def reject(self, message):
        self.error = str(message)

    def status_text(self):
        if self.error:
            return "LED USAGE: " + self.error
        if not self.active:
            return "LED USAGE: app not running — launch it from the system menu"
        return "LED USAGE: count=%d rgb=(%d,%d,%d) global=%d" % (
            self.count, self.r, self.g, self.b, self.global_brightness)
