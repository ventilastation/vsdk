class InputParser:
    _STATE_SCAN    = 0
    _STATE_JOY     = 1
    _STATE_COMMAND = 2
    _CMD_MAX       = 256

    def __init__(self):
        self.joy1  = 0
        self.joy2  = 0
        self.extra = 0
        self._state     = self._STATE_SCAN
        self._joy_buf   = bytearray(3)
        self._joy_pos   = 0
        self._cmd_buf   = bytearray()
        self._cmd_queue = []

    def reset(self):
        self.joy1  = 0
        self.joy2  = 0
        self.extra = 0
        self._state = self._STATE_SCAN
        self._cmd_buf = bytearray()
        self._cmd_queue = []

    def feed(self, data):
        for b in data:
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
