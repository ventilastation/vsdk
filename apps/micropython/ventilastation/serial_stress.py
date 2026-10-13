"""Serial link stress test: wire format, test data and error diagnosis.

Shared by both ends of the base<->rotor link so they derive identical
expected bytes:

- the rotor app, games/demos/serialstress (MicroPython), which drives the
  run phase by phase;
- the base-side checker, emulator/serial_stress_host.py, used by the
  emulator (the production base path) and by tools/serial_stress.py.

Every test frame's content is a pure function of (phase, seq), so a
receiver can tell exactly how a bad frame differs from what was sent: bits
flipped in place point at the wire, whole runs of missing bytes at a buffer
that overflowed. docs/internals/serial-stress-test.md has the protocol and
how to read the results.

Runs on MicroPython and CPython alike.
"""

PROTOCOL_VERSION = 1

# --- Commands --------------------------------------------------------------
# rotor -> base (host protocol lines, docs/internals/host-protocol.md)
HELLO = "serialtest_hello"      # <version>: the app is up; base answers READY
PHASE = "serialtest_phase"      # <phase> k=v...: a phase starts, with its load
UP = "serialtest_up"            # <nbytes> <phase> <seq> + <nbytes> raw bytes
END = "serialtest_end"          # <phase> k=v...: rotor-side counters
DONE = "serialtest_done"        # the run is over; base answers VERDICT
# base -> rotor (input protocol command lines, docs/internals/input-protocol-v2.md)
READY = "serialtest_ready"      # <version>
RUN = "serialtest_run"          # <"plan" | phase name> ["loop"]: remote start
DOWN = "serialtest_down"        # <phase> <seq> <payload>: payload inline
SENT = "serialtest_sent"        # <phase> frames=<n>: downlink for it is over
RESULT = "serialtest_result"    # <phase> k=v...: base-side counters
VERDICT = "serialtest_verdict"  # <code>

# --- Test plan -------------------------------------------------------------
# 8N1: a start bit, eight data bits, a stop bit.
BITS_PER_BYTE = 10
PHASE_MS = 8000

# (name, uplink % of line rate, uplink frame bytes,
#  downlink % of line rate, downlink payload chars, part of the full plan)
#
# Uplink above 100% is offered faster than the wire carries it: the rotor's
# writes block, so the phase measures the real ceiling and whether the base
# keeps up with a saturated line.
#
# Downlink is bounded by the rotor, not the wire: its main loop drains 3 x 64
# bytes and pops one command line per ~30 ms tick, out of a 256-byte UART
# receive buffer. Plan phases keep lines short enough that two arriving back
# to back still fit, and under one line per tick. That is far beyond what
# the base really sends (4-byte joystick frames), so it measures the wire
# without tripping a limit production traffic never reaches. "down60" --
# outside the plan -- overruns the rotor on purpose: the positive control
# showing what a rotor-side overrun looks like in the report.
PHASES = (
    ("idle", 0, 0, 0, 0, True),
    ("up10", 10, 128, 0, 0, True),
    ("up50", 50, 256, 0, 0, True),
    ("up90", 90, 512, 0, 0, True),
    ("upmax", 150, 1024, 0, 0, True),
    ("down10", 0, 0, 10, 100, True),
    ("down20", 0, 0, 20, 100, True),
    ("both", 40, 256, 15, 100, True),
    ("down60", 0, 0, 60, 200, False),
)

PLAN = tuple(index for index, phase in enumerate(PHASES) if phase[5])


def phase_index(name):
    for index, phase in enumerate(PHASES):
        if phase[0] == name:
            return index
    return None


def line_rate(baud):
    """Payload bytes per second the wire can carry at ``baud``."""
    return baud // BITS_PER_BYTE


def phase_load(index, baud):
    """(up_bps, up_frame, down_bps, down_chars) for phase ``index``."""
    _name, up_pct, up_frame, down_pct, down_chars, _in_plan = PHASES[index]
    rate = line_rate(baud)
    return rate * up_pct // 100, up_frame, rate * down_pct // 100, down_chars


# --- Test data -------------------------------------------------------------
PATTERN_SIZE = 1024
MAX_UP_FRAME = 1024
# Downlink lines must fit the input parser's 256-byte command cap together
# with "serialtest_down <phase> <seq> ".
MAX_DOWN_PAYLOAD = 200


def _xorshift16(x):
    # 16-bit state keeps every intermediate a MicroPython small int.
    x ^= (x << 7) & 0xFFFF
    x ^= x >> 9
    x ^= (x << 8) & 0xFFFF
    return x


_binary = None
_ascii = None


def binary_pattern():
    """Uplink test bytes: every byte value in a shuffled order, led by runs
    that are hard on a marginal line (0x55 toggles every bit; 0x00 and 0xFF
    hold it low or high). Stored twice back to back, so a frame starting at
    any offset is one slice."""
    global _binary
    if _binary is None:
        data = bytearray(PATTERN_SIZE)
        for i in range(PATTERN_SIZE):
            data[i] = i & 0xFF
        x = 0xACE1
        for i in range(PATTERN_SIZE - 1, 0, -1):
            x = _xorshift16(x)
            j = x % (i + 1)
            data[i], data[j] = data[j], data[i]
        data[0:48] = b"\x55" * 16 + b"\x00" * 16 + b"\xff" * 16
        _binary = data + data
    return _binary


# Printable ASCII without the space (command fields are space separated)
# and without "*": once line framing is lost the input parser reads a "*"
# as the start of a joystick frame, and test text must not turn into
# phantom button presses.
_ASCII_CHARS = bytes(c for c in range(0x21, 0x7F) if c != 0x2A)


def ascii_pattern():
    """Downlink test text, doubled like binary_pattern()."""
    global _ascii
    if _ascii is None:
        chars = bytearray(PATTERN_SIZE)
        x = 0x1D2B
        for i in range(PATTERN_SIZE):
            x = _xorshift16(x)
            chars[i] = _ASCII_CHARS[x % len(_ASCII_CHARS)]
        chars[0:16] = b"U" * 16
        _ascii = bytes(chars + chars).decode()
    return _ascii


def payload_offset(phase, seq):
    return (seq * 389 + phase * 101) % PATTERN_SIZE


def up_header(nbytes, phase, seq):
    return b"%s %d %d %d" % (UP.encode(), nbytes, phase, seq)


def up_payload(phase, seq, nbytes):
    """The bytes uplink frame (phase, seq) carries, as a memoryview."""
    offset = payload_offset(phase, seq)
    return memoryview(binary_pattern())[offset:offset + nbytes]


def down_payload(phase, seq, nchars):
    offset = payload_offset(phase, seq)
    return ascii_pattern()[offset:offset + nchars]


def down_line(phase, seq, nchars):
    return "%s %d %d %s" % (DOWN, phase, seq, down_payload(phase, seq, nchars))


def format_fields(pairs):
    """``k=v`` tokens from (key, value) pairs, in order."""
    return " ".join("%s=%s" % (key, value) for key, value in pairs)


def parse_fields(tokens):
    """Inverse of format_fields(); integer values come back as ints.
    Malformed tokens are skipped: a corrupted control line yields fewer
    fields, never an exception."""
    fields = {}
    for token in tokens:
        at = token.find("=")
        if at <= 0:
            continue
        value = token[at + 1:]
        try:
            value = int(value)
        except ValueError:
            pass
        fields[token[:at]] = value
    return fields


# --- Diagnosis -------------------------------------------------------------
OK = "ok"
BITFLIP = "bitflip"      # same length, a few bytes with flipped bits
ZEROED = "zeroed"        # same length, every bad byte arrived as 0x00
DROPPED = "dropped"      # bytes missing; what follows realigns
INSERTED = "inserted"    # extra bytes; what follows realigns
SHORT = "short"          # ends early, nothing left to realign
GARBLED = "garbled"      # none of the above

KINDS = (BITFLIP, ZEROED, DROPPED, INSERTED, SHORT, GARBLED)
# Corruption in place can only happen on the wire: no buffer in either
# software stack rewrites bytes, it can only lose them.
WIRE_KINDS = (BITFLIP, ZEROED)

MAX_SHIFT = 64
MIN_REALIGN = 8


def _popcount8(value):
    count = 0
    while value:
        value &= value - 1
        count += 1
    return count


def diagnose(expected, received):
    """Classify how ``received`` differs from ``expected`` (bytes-likes).

    Returns ``(kind, offset, nbytes, nbits)``: the first differing offset,
    how many bytes are affected (differing, dropped or inserted), and for
    same-length corruption how many bits flipped in total. Downlink payloads
    arrive as (ASCII) str and are compared as bytes.
    """
    if isinstance(expected, str):
        expected = expected.encode()
    if isinstance(received, str):
        received = received.encode()
    n_exp = len(expected)
    n_rec = len(received)
    n = min(n_exp, n_rec)
    i = 0
    while i < n and expected[i] == received[i]:
        i += 1
    if i == n:
        if n_exp == n_rec:
            return (OK, 0, 0, 0)
        if n_rec < n_exp:
            return (SHORT, i, n_exp - n_rec, 0)
        return (INSERTED, i, n_rec - n_exp, 0)

    if n_exp == n_rec:
        differing = 0
        bits = 0
        zeroed = True
        for j in range(i, n):
            e = expected[j]
            r = received[j]
            if e != r:
                differing += 1
                bits += _popcount8(e ^ r)
                if r:
                    zeroed = False
        if differing * 4 <= n:
            return (ZEROED if zeroed else BITFLIP, i, differing, bits)

    for k in range(1, MAX_SHIFT + 1):
        # k bytes lost at i: received[i:] lines up with expected[i+k:]. When
        # the reader trusted the header's length (the emulator does), the
        # frame was padded out with the next frame's first k bytes.
        tail = min(n_exp - i - k, n_rec - i)
        if tail >= MIN_REALIGN and received[i:i + tail] == expected[i + k:i + k + tail]:
            return (DROPPED, i, k, 0)
        tail = min(n_rec - i - k, n_exp - i)
        if tail >= MIN_REALIGN and received[i + k:i + k + tail] == expected[i:i + tail]:
            return (INSERTED, i, k, 0)

    if n_rec < n_exp:
        return (SHORT, i, n_exp - n_rec, 0)
    return (GARBLED, i, n - i, 0)


class PhaseCounter:
    """Receive-side accounting for one direction of one phase."""

    MAX_SEQ = 4096
    MAX_EXAMPLES = 5

    def __init__(self, phase):
        self.phase = phase
        self.ok = 0
        self.bad = 0
        self.dup = 0
        self.stale = 0
        self.bytes_ok = 0
        self.bits = 0
        self.kinds = {}
        # (seq, kind, offset, nbytes, nbits) for the first few bad frames.
        self.examples = []
        self.max_seq = -1
        self._seen = bytearray(self.MAX_SEQ // 8)

    def check(self, phase, seq, expected, received):
        """Account one received frame; returns its diagnosis kind (or
        "stale"/"dup" for frames that belong to another phase or repeat)."""
        if phase != self.phase:
            self.stale += 1
            return "stale"
        if not 0 <= seq < self.MAX_SEQ:
            # Only a corrupted header gets here; nothing to compare with.
            self._bad(seq, (GARBLED, 0, len(received), 0))
            return GARBLED
        bit = 1 << (seq & 7)
        if self._seen[seq >> 3] & bit:
            self.dup += 1
            return "dup"
        self._seen[seq >> 3] |= bit
        if seq > self.max_seq:
            self.max_seq = seq
        if len(received) == len(expected) and received == expected:
            self.ok += 1
            self.bytes_ok += len(received)
            return OK
        result = diagnose(expected, received)
        if result[0] == OK:
            self.ok += 1
            self.bytes_ok += len(received)
            return OK
        self._bad(seq, result)
        return result[0]

    def _bad(self, seq, result):
        kind = result[0]
        self.bad += 1
        self.bits += result[3]
        self.kinds[kind] = self.kinds.get(kind, 0) + 1
        if len(self.examples) < self.MAX_EXAMPLES:
            self.examples.append((seq,) + tuple(result))

    def lost(self, sent=None):
        """Frames never seen. Without the sender's count only gaps below the
        highest sequence number seen can be counted."""
        if sent is None:
            sent = self.max_seq + 1
        return max(0, sent - self.ok - self.bad)

    def wire_errors(self):
        return sum(self.kinds.get(kind, 0) for kind in WIRE_KINDS)


def describe_example(example):
    seq, kind, offset, nbytes, nbits = example
    if kind in WIRE_KINDS:
        return "seq %d: %d bytes changed in place (%d bits) from offset %d" % (
            seq, nbytes, nbits, offset)
    if kind == DROPPED:
        return "seq %d: %d bytes missing at offset %d" % (seq, nbytes, offset)
    if kind == INSERTED:
        return "seq %d: %d extra bytes at offset %d" % (seq, nbytes, offset)
    if kind == SHORT:
        return "seq %d: %d bytes short, cut at offset %d" % (seq, nbytes, offset)
    return "seq %d: garbled from offset %d" % (seq, offset)
