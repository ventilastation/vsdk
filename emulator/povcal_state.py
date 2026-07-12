"""Host-side state reflected by acknowledged ``povcal_state`` messages."""


class PovCalibrationState:
    """Keep UI controls synchronized with the board, not optimistic guesses."""

    def __init__(self):
        self.profile = None
        self.error = None

    @property
    def generation(self):
        return None if self.profile is None else self.profile.generation

    @property
    def ready(self):
        return self.profile is not None

    def apply(self, profile):
        self.profile = profile
        self.error = None

    def reject(self, message):
        self.error = str(message)

    def status_text(self):
        if self.error:
            return "POV CAL: " + self.error
        if self.profile is None:
            return "POV CAL: waiting for board profile"
        return "POV CAL: profile #%d" % self.profile.generation
