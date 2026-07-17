class InputParser:
    _STATE_SCAN    = 0
    _STATE_JOY     = 1
    _STATE_COMMAND = 2
    _CMD_MAX       = 256
    # See docs/internals/input-protocol-v2.md#resync--device-identification.
    # Only the leading 'R' has its high bit set (0x52 | 0x80); bit 7 is never
    # set on a legitimate data byte, so this sequence is always safe to
    # recognize regardless of parser state.
    _RESYNC_SEQUENCE = b"\n\n\xd2ESYNC\n"

    def __init__(self):
        self.joy1  = 0
        self.joy2  = 0
        self.extra = 0
        self.resync_pending = False
        self._state     = self._STATE_SCAN
        self._joy_buf   = bytearray(3)
        self._joy_pos   = 0
        self._cmd_buf   = bytearray()
        self._cmd_queue = []
        self._resync_match = 0

    def reset(self):
        self.joy1  = 0
        self.joy2  = 0
        self.extra = 0
        self._state = self._STATE_SCAN
        self._cmd_buf = bytearray()
        self._cmd_queue = []
        self._resync_match = 0
        # resync_pending is intentionally left alone: reset() clears
        # frame/command state on reconnect, but a caller that hasn't yet
        # observed a pending resync request must still see it.

    def feed(self, data):
        for b in data:
            # Track a possible RESYNC match in parallel with normal parsing,
            # rather than instead of it: a partial or failed match must not
            # swallow bytes the state machine still needs (0x0A is both the
            # marker's first byte and a legitimate command terminator/raw
            # joystick payload byte). Only the byte that *completes* the
            # match is consumed here instead of being fed through below.
            # Bytes on the way to a match are otherwise processed normally:
            # the marker's leading '\n' terminates (and queues) whatever
            # command happened to be in flight exactly like a real newline
            # would, and its own "ESYNC" text turns into a throwaway
            # COMMAND-state accumulation that gets discarded the instant the
            # match completes. Both are harmless -- the device resets right
            # after a completed match anyway.
            if b == self._RESYNC_SEQUENCE[self._resync_match]:
                self._resync_match += 1
                if self._resync_match == len(self._RESYNC_SEQUENCE):
                    self.resync_pending = True
                    self._resync_match = 0
                    self._state = self._STATE_SCAN
                    self._cmd_buf = bytearray()
                    continue
            else:
                self._resync_match = 1 if b == self._RESYNC_SEQUENCE[0] else 0

            if self._state == self._STATE_SCAN:
                if b == 0x2A:
                    self._state   = self._STATE_JOY
                    self._joy_pos = 0
                elif 0x30 <= b <= 0x39 or 0x41 <= b <= 0x5A or 0x61 <= b <= 0x7A:
                    self._state   = self._STATE_COMMAND
                    self._cmd_buf = bytearray([b])
            elif self._state == self._STATE_JOY:
                self._joy_buf[self._joy_pos] = b
                self._joy_pos += 1
                if self._joy_pos == 3:
                    self.joy1  = self._joy_buf[0] & 0x7F
                    self.joy2  = self._joy_buf[1] & 0x7F
                    self.extra = self._joy_buf[2] & 0x7F
                    self._state = self._STATE_SCAN
            elif self._state == self._STATE_COMMAND:
                if b == 0x0A:
                    line = self._cmd_buf.decode("ascii", "replace").strip()
                    if line:
                        self._cmd_queue.append(line)
                    self._state = self._STATE_SCAN
                elif len(self._cmd_buf) >= self._CMD_MAX:
                    self._state = self._STATE_SCAN
                else:
                    self._cmd_buf.append(b)

    def pop_command(self):
        return self._cmd_queue.pop(0) if self._cmd_queue else None

    def pop_resync(self):
        """Return True once, then False, for each RESYNC marker seen."""
        pending = self.resync_pending
        self.resync_pending = False
        return pending
