"""RESYNC marker scanner for the rotor's native USB/UART0 console (the REPL
wire), independent of the dedicated base-station UART handled by
input_parser.py. See docs/internals/input-protocol-v2.md#resync--device-identification
for the wire format and why bit 7 makes the marker unambiguous.

The console is a single logical stream spanning both UART0-REPL and the
native USB-Serial-JTAG interface (mphalport.c feeds both into one shared
ring buffer and dual-writes stdout to both) -- so scanning sys.stdin here
covers a RESYNC sent over either physical wire without telling them apart.
"""

import select
import sys

_RESYNC_SEQUENCE = b"\n\n\xd2ESYNC\n"


class ConsoleResyncScanner:
    def __init__(self):
        self._poller = select.poll()
        self._poller.register(sys.stdin, select.POLLIN)
        self._match = 0

    def poll_pending(self):
        """Non-blocking: drains whatever console bytes are currently
        available and reports whether they completed the RESYNC marker."""
        pending = False
        while self._poller.poll(0):
            byte = sys.stdin.buffer.read(1)[0]
            if byte == _RESYNC_SEQUENCE[self._match]:
                self._match += 1
                if self._match == len(_RESYNC_SEQUENCE):
                    pending = True
                    self._match = 0
            else:
                self._match = 1 if byte == _RESYNC_SEQUENCE[0] else 0
        return pending
