"""Base side of the serial stress test (docs/internals/serial-stress-test.md).

The rotor app (games/demos/serialstress) drives the run; this end answers
it. It checks every uplink frame against the bytes the rotor must have
sent, generates the downlink load each phase asks for, reads the serial
adapter's own line-error counters, and prints a per-phase report and a
verdict, which it also sends back for the rotor's screen.

Two transports feed it: emulator/comms.py, the production base's own
reader, so the test sees exactly what games see; and tools/serial_stress.py,
a lean chunked reader that takes the emulator out of the picture.
"""

import importlib.util
import pathlib
import struct
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_protocol():
    # By path, as tools/generate_roms.py loads romformat: the rotor's
    # ventilastation package must not shadow anything on the host.
    path = ROOT / "apps" / "micropython" / "ventilastation" / "serial_stress.py"
    spec = importlib.util.spec_from_file_location("vs_serial_stress", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sst = _load_protocol()

# Linux's TIOCGICOUNT (asm-generic/ioctls.h; same on x86 and ARM) fills a
# struct serial_icounter_struct: 11 ints, then 9 reserved.
_TIOCGICOUNT = 0x545D
_ICOUNT_FIELDS = ("cts", "dsr", "rng", "dcd", "rx", "tx",
                  "frame", "overrun", "parity", "brk", "buf_overrun")


def read_icount(fileno):
    """The serial driver's own receive counters, or None where the OS or
    driver can't report them. frame/parity/brk are electrical: bytes that
    arrived malformed. overrun means the adapter's FIFO filled before the
    driver emptied it; buf_overrun that the tty buffer filled because the
    reading program was too slow."""
    try:
        import fcntl
        buffer = bytearray(80)
        fcntl.ioctl(fileno, _TIOCGICOUNT, buffer, True)
    except (ImportError, OSError, ValueError, TypeError):
        return None
    return dict(zip(_ICOUNT_FIELDS, struct.unpack("20i", bytes(buffer))))


def icount_reader(port):
    """A zero-argument icount callable for a pyserial port (or anything
    with fileno()); returns None for transports that aren't serial."""
    def read():
        try:
            return read_icount(port.fileno())
        except (AttributeError, OSError, ValueError):
            return None
    return read


def _icount_delta(start, end):
    if start is None or end is None:
        return None
    return {key: end[key] - start[key] for key in _ICOUNT_FIELDS}


def describe_icount(start, end):
    """One line for the adapter's counters between two read_icount() calls,
    or None if it can't report them."""
    delta = _icount_delta(start, end)
    if delta is None:
        return None
    return "%d framing, %d parity, %d breaks, %d overruns, %d tty overruns" % (
        delta["frame"], delta["parity"], delta["brk"], delta["overrun"], delta["buf_overrun"])


# Load (percent of line rate) at or below which no buffer in either stack
# comes near overflowing: losses there are not a software throughput limit.
LOW_LOAD_PCT = 30
# A rotor receive-buffer peak this close to its size means it overflowed.
RX_FULL_FRACTION = 0.9

VERDICT_TEXT = {
    "clean": "no errors in either direction",
    "hardware": "errors the wire caused: look at the cables/slip ring/connectors",
    "rotor_software": "the rotor dropped input it could not drain in time",
    "base_software": "the base read the serial port too slowly",
    "mixed": "both wire errors and software overruns",
    "inconclusive": "errors without enough evidence to place them (see findings)",
}


class PhaseRecord:
    """Everything known about one phase, from both ends."""

    def __init__(self, index, fields, icount, started):
        self.index = index
        self.name = str(fields.get("name", index))
        self.up_bps = fields.get("up_bps", 0)
        self.up_frame = fields.get("up_frame", 0)
        self.down_bps = fields.get("down_bps", 0)
        self.down_chars = fields.get("down_chars", 0)
        self.ms = fields.get("ms", sst.PHASE_MS)
        self.baud = fields.get("baud", 115200)
        self.up = sst.PhaseCounter(index)
        self.up_junk = 0
        self.down_sent = 0
        self.rotor = None  # the rotor's END fields
        self.icount_start = icount
        self.icount_end = None
        self.icount = None
        self.started = started
        self.last_up = None

    def up_rate(self):
        """Uplink bytes per second actually received: over the time the
        frames took to arrive, which a saturated phase stretches past its
        nominal length."""
        if self.last_up is None:
            return 0
        return self.up.bytes_ok / max(self.last_up - self.started, self.ms / 1000)

    def pct(self, bps):
        return 100 * bps // max(1, sst.line_rate(self.baud))

    def up_lost(self):
        sent = self.rotor.get("frames") if self.rotor else None
        return self.up.lost(sent)

    def down_lost(self):
        """Downlink lines that never arrived. Counted here, where the number
        sent is known for sure: the rotor learns it from the SENT marker,
        which can itself be lost."""
        rotor = self.rotor or {}
        return max(0, self.down_sent - rotor.get("dn_ok", 0) - rotor.get("dn_bad", 0))


class _Downlink:
    """Paces one phase's downlink lines; finishes with the SENT marker."""

    MAX_BURST = 16

    def __init__(self, record, started):
        self.record = record
        self.started = started
        self.seq = 0
        self.sent_bytes = 0
        self.finished = False

    def due(self, now):
        record = self.record
        elapsed = now - self.started
        duration = record.ms / 1000
        lines = []
        if record.down_bps and record.down_chars:
            target = record.down_bps * min(elapsed, duration)
            while self.sent_bytes < target and len(lines) < self.MAX_BURST:
                lines.append(sst.down_line(record.index, self.seq, record.down_chars))
                self.seq += 1
                self.sent_bytes += record.down_chars
        if elapsed >= duration and self.sent_bytes >= record.down_bps * duration:
            record.down_sent = self.seq
            lines.append("%s %d frames=%d" % (sst.SENT, record.index, self.seq))
            self.finished = True
        return lines


class StressHost:
    """The base's end of the test, independent of transport.

    ``send_line(text)`` writes one command line to the rotor (without the
    newline). ``handle()`` takes the rotor's test lines; ``pump()`` sends
    whatever downlink is due and must be called every few milliseconds while
    a phase runs (start_pump_thread() does that).
    """

    def __init__(self, send_line, log=print, icount=None, clock=time.monotonic):
        self.send_line = send_line
        self.log = log
        self.icount = icount
        self.clock = clock
        self.records = []
        self.current = None
        self.run_closed = True
        self.verdict = None
        self.findings = []
        self.hello_count = 0
        self.version_warned = False
        self.stray = 0
        self._downlink = None
        self._lock = threading.Lock()
        self._wake = threading.Event()

    # --- Lines from the rotor ------------------------------------------------

    def handle(self, command, args, payload=b""):
        """Handle one host-protocol line; returns False for non-test lines."""
        if command == sst.UP:
            self._on_up(args, payload)
        elif command == sst.HELLO:
            self._on_hello(args)
        elif command == sst.PHASE:
            self._on_phase(args)
        elif command == sst.END:
            self._on_end(args)
        elif command == sst.DONE:
            self._on_done(args)
        else:
            return False
        return True

    def note_junk(self):
        """A line the reader couldn't make sense of arrived."""
        record = self.current
        if record is not None:
            record.up_junk += 1

    def _on_hello(self, args):
        version = args[0] if args else "?"
        if version != str(sst.PROTOCOL_VERSION):
            # Different test data on each end would read as a broken link.
            # Leave the app waiting rather than run a meaningless test.
            if not self.version_warned:
                self.log("serialtest: the rotor's Serial Stress app speaks protocol %s, this base "
                         "%d: update both before testing" % (version, sst.PROTOCOL_VERSION))
                self.version_warned = True
            return
        self.hello_count += 1
        self.send_line("%s %d" % (sst.READY, sst.PROTOCOL_VERSION))
        if self.hello_count == 1:
            self.log("serialtest: rotor app connected (protocol %s)" % version)

    def _on_up(self, args, payload):
        record = self.current
        try:
            _nbytes, phase, seq = (int(value) for value in args[:3])
        except ValueError:
            self.note_junk()
            return
        if record is None:
            self.stray += 1
            return
        expected = sst.up_payload(phase, seq, record.up_frame)
        record.up.check(phase, seq, expected, payload)
        record.last_up = self.clock()

    def _on_phase(self, args):
        try:
            index = int(args[0])
        except (IndexError, ValueError):
            self.note_junk()
            return
        fields = sst.parse_fields(args[1:])
        with self._lock:
            if self.current is not None:
                self._close(self.current)
            if self.run_closed:
                self.records = []
                self.verdict = None
                self.findings = []
                self.run_closed = False
            record = PhaseRecord(index, fields, self.icount() if self.icount else None, self.clock())
            self.current = record
            self._downlink = _Downlink(record, self.clock())
        self._wake.set()

    def _on_end(self, args):
        try:
            index = int(args[0])
        except (IndexError, ValueError):
            self.note_junk()
            return
        with self._lock:
            record = self.current
            if record is None or record.index != index:
                return
            record.rotor = sst.parse_fields(args[1:])
            self._close(record)
        self.send_line("%s %d %s" % (sst.RESULT, index, sst.format_fields((
            ("ok", record.up.ok), ("bad", record.up.bad), ("lost", record.up_lost()),
            ("junk", record.up_junk), ("wire", record.up.wire_errors()),
            ("dn_lost", record.down_lost()),
        ))))

    def _close(self, record):
        """Finish ``record`` (lock held): stop its downlink, log it."""
        if self._downlink is not None and self._downlink.record is record:
            record.down_sent = self._downlink.seq
            self._downlink = None
        record.icount_end = self.icount() if self.icount else None
        record.icount = _icount_delta(record.icount_start, record.icount_end)
        self.current = None
        self.records.append(record)
        for line in report_phase(record, len(self.records)):
            self.log(line)

    def _on_done(self, args):
        fields = sst.parse_fields(args)
        with self._lock:
            if self.current is not None:
                self._close(self.current)
            self._downlink = None
            self.run_closed = True
            records = list(self.records)
        code, findings = analyze(records)
        self.verdict = code
        self.findings = findings
        for line in report_run(records, code, findings, aborted=bool(fields.get("aborted"))):
            self.log(line)
        self.send_line("%s %s" % (sst.VERDICT, code))

    # --- Downlink -------------------------------------------------------------

    def pump(self):
        """Send the downlink lines that are due. Returns True while a phase
        still has downlink to send."""
        with self._lock:
            downlink = self._downlink
            if downlink is None:
                return False
            lines = downlink.due(self.clock())
            if downlink.finished:
                self._downlink = None
        for line in lines:
            self.send_line(line)
        return not downlink.finished

    def start_pump_thread(self, interval=0.005):
        def run():
            while True:
                if not self.pump():
                    self._wake.wait()
                    self._wake.clear()
                else:
                    time.sleep(interval)
        thread = threading.Thread(target=run, name="serialtest-downlink", daemon=True)
        thread.start()
        return thread


# --- Line-based readers (emulator/comms.py) ----------------------------------------

def dispatch_line(host, read, command, args):
    """Feed one line from a line-based reader to ``host``: ``command`` and
    ``args`` are the line split into bytes tokens, and ``read(n)`` reads a
    payload from the same stream. Returns False for a line it can't use."""
    name = command.decode("ascii", "replace")
    text_args = [arg.decode("ascii", "replace") for arg in args]
    payload = b""
    if name == sst.UP:
        try:
            length = int(text_args[0])
        except (IndexError, ValueError):
            length = -1
        if not 0 <= length <= sst.MAX_UP_FRAME:
            # A corrupted length: reading it would swallow good frames.
            host.note_junk()
            return True
        payload = read(length)
    if host.handle(name, text_args, payload):
        return True
    host.note_junk()
    return False


def recover_line(host, read, command, args):
    """An unknown line reached a line-based reader. Returns True if it was
    the stress test's and has been dealt with.

    Once a byte is lost inside a binary test payload the reader is out of
    step: the length it trusted swallows the start of the next header, and
    the "line" it reads next is a payload tail glued to the following
    header. Left alone it would realign only by luck, when some payload
    happened to end in a newline, and one lost byte would cost hundreds of
    frames. Find the test header in the line and resume from it, so the test
    measures the wire rather than the reader's recovery. Junk is counted, and
    not printed while a phase runs: it is test data.
    """
    if host is None:
        return False
    tokens = (command,) + tuple(args)
    for index, token in enumerate(tokens):
        at = token.find(b"serialtest_")
        if at >= 0:
            host.note_junk()
            dispatch_line(host, read, token[at:], list(tokens[index + 1:]))
            return True
    if host.current is None:
        return False
    host.note_junk()
    return True


# --- Reporting and verdict ------------------------------------------------------

def _kinds_text(counts):
    return ", ".join("%d %s" % (count, kind) for kind, count in sorted(counts.items()) if count)


def report_phase(record, number):
    rotor = record.rotor or {}
    lines = []
    head = "serialtest: #%d %-6s" % (number, record.name)
    if record.up_bps:
        kinds = _kinds_text(record.up.kinds)
        lines.append("%s UP   %3d%% x%-4d %5d ok %3d bad %3d lost  %6.0f B/s%s" % (
            head, record.pct(record.up_bps), record.up_frame, record.up.ok, record.up.bad,
            record.up_lost(), record.up_rate(), " (%s)" % kinds if kinds else ""))
        head = " " * len(head)
    if record.down_bps:
        if record.rotor is None:
            lines.append("%s DOWN %3d%% x%-4d sent %d; the rotor's report never arrived" % (
                head, record.pct(record.down_bps), record.down_chars, record.down_sent))
        else:
            kinds = _kinds_text({kind: rotor.get("dn_" + kind, 0) for kind in sst.KINDS})
            lines.append("%s DOWN %3d%% x%-4d %5d ok %3d bad %3d lost  sent %d%s" % (
                head, record.pct(record.down_bps), record.down_chars, rotor.get("dn_ok", 0),
                rotor.get("dn_bad", 0), record.down_lost(), record.down_sent,
                " (%s)" % kinds if kinds else ""))
        head = " " * len(head)
    if not record.up_bps and not record.down_bps:
        lines.append("%s idle link (joystick frames only)" % head)
        head = " " * len(head)
    indent = " " * len(head)
    if record.rotor is not None:
        rx = ("rx buffer peak %s/%s" % (rotor["rx_hwm"], rotor["rx_buf"])
              if "rx_hwm" in rotor and "rx_buf" in rotor else "rx buffer n/a")
        lines.append("%s rotor: %s, %d bit-7 / %d overlong lines dropped, %d junk, "
                     "%d joystick changes, loop max gap %d ms, tx blocked %d ms" % (
                         indent, rx, rotor.get("nonascii", 0), rotor.get("overlong", 0),
                         rotor.get("dn_junk", 0), rotor.get("joy", 0),
                         rotor.get("tick_max", 0), rotor.get("tx_ms", 0)))
    adapter = describe_icount(record.icount_start, record.icount_end)
    if adapter is not None:
        lines.append("%s base adapter: %s; %d junk lines" % (indent, adapter, record.up_junk))
    elif record.up_junk:
        lines.append("%s base: %d junk lines" % (indent, record.up_junk))
    for example in record.up.examples:
        lines.append("%s UP %s" % (indent, sst.describe_example(example)))
    return lines


def phase_findings(record):
    """[(category, text)] explaining this phase's errors, if any."""
    findings = []
    rotor = record.rotor or {}
    up_pct = record.pct(record.up_bps)
    down_pct = record.pct(record.down_bps)
    up_wire = record.up.wire_errors()
    up_err = record.up.bad + record.up_lost()
    dn_wire = rotor.get("dn_" + sst.BITFLIP, 0) + rotor.get("dn_" + sst.ZEROED, 0)
    dn_err = (rotor.get("dn_bad", 0) + record.down_lost()) if record.rotor else 0
    ic = record.icount or {}
    line_errors = ic.get("frame", 0) + ic.get("parity", 0) + ic.get("brk", 0)
    overruns = ic.get("overrun", 0) + ic.get("buf_overrun", 0)
    rx_hwm = rotor.get("rx_hwm")
    rx_buf = rotor.get("rx_buf")
    rotor_full = bool(rx_buf) and rx_hwm is not None and rx_hwm >= rx_buf * RX_FULL_FRACTION

    if line_errors:
        findings.append(("hardware", "the base's serial adapter counted %d framing/parity errors "
                         "or breaks in what the rotor sent" % line_errors))
    if up_wire:
        findings.append(("hardware", "%d uplink frames arrived with bits changed in place" % up_wire))
    if dn_wire:
        findings.append(("hardware", "%d downlink lines arrived with bits changed in place" % dn_wire))
    if rotor.get("nonascii"):
        findings.append(("hardware", "the rotor dropped %d command lines holding bytes with bit 7 "
                         "set, which the base never sends" % rotor["nonascii"]))
    if record.name == "idle" and (record.up_junk or rotor.get("dn_junk")):
        findings.append(("hardware", "garbage arrived while the link carried no test data"))
    if overruns:
        findings.append(("base_software", "the base's adapter/tty overran %d times: "
                         "it read the port too slowly" % overruns))

    # Lines the rotor's parser dropped for bit 7 never reached the app, so
    # they count as lost too; they are already explained above.
    lost = dn_err - dn_wire - rotor.get("nonascii", 0)
    if lost > 0:
        if rotor_full:
            findings.append(("rotor_software", "%d downlink lines lost with the rotor's receive buffer "
                             "full (peak %d/%d): its main loop drained too slowly" % (lost, rx_hwm, rx_buf)))
        elif rx_buf:
            findings.append(("hardware", "%d downlink lines lost at %d%% load while the rotor's receive "
                             "buffer never filled (peak %d/%d)" % (lost, down_pct, rx_hwm or 0, rx_buf)))
        else:
            findings.append(("inconclusive", "%d downlink lines lost; no receive-buffer figures "
                             "from the rotor to place them" % lost))
    if up_err > up_wire and not overruns:
        lost = up_err - up_wire
        if up_pct <= LOW_LOAD_PCT:
            findings.append(("hardware", "%d uplink frames lost or damaged at only %d%% load" % (lost, up_pct)))
        elif up_wire or line_errors:
            findings.append(("hardware", "%d uplink frames lost or damaged alongside wire corruption in the "
                             "same direction: most likely the same noise garbling their "
                             "headers" % lost))
        else:
            findings.append(("inconclusive", "%d uplink frames lost or damaged at %d%% load with no overrun "
                             "reported; rerun with tools/serial_stress.py rotor to rule out the "
                             "emulator's reader" % (lost, up_pct)))
    if record.rotor is None:
        findings.append(("inconclusive", "the rotor's end-of-phase report never arrived"))
    return findings


def analyze(records):
    """(verdict code, [(category, phase name, text)]) for a run."""
    findings = []
    for record in records:
        for category, text in phase_findings(record):
            findings.append((category, record.name, text))
    categories = set(category for category, _name, _text in findings)
    software = categories & {"rotor_software", "base_software"}
    if not findings:
        code = "clean"
    elif "hardware" in categories and software:
        code = "mixed"
    elif "hardware" in categories:
        code = "hardware"
    elif len(software) == 1 and "inconclusive" not in categories:
        code = software.pop()
    elif software and "inconclusive" not in categories:
        code = "mixed"
    else:
        code = "inconclusive"
    return code, findings


def report_run(records, code, findings, aborted=False):
    lines = ["serialtest: ---- %d phase(s)%s ----" % (len(records), ", aborted" if aborted else "")]
    up_ok = sum(record.up.ok for record in records)
    up_err = sum(record.up.bad + record.up_lost() for record in records)
    dn_ok = sum((record.rotor or {}).get("dn_ok", 0) for record in records)
    dn_err = sum((record.rotor or {}).get("dn_bad", 0) + record.down_lost()
                 for record in records if record.rotor)
    lines.append("serialtest: uplink %d ok / %d bad or lost; downlink %d ok / %d bad or lost" % (
        up_ok, up_err, dn_ok, dn_err))
    for category, name, text in findings:
        lines.append("serialtest:   [%s] %s: %s" % (category, name, text))
    lines.append("serialtest: VERDICT %s -- %s" % (code.upper(), VERDICT_TEXT[code]))
    return lines
