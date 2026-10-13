#!/usr/bin/env python3
"""Serial link stress test from the base's side, without the emulator.

Two modes (docs/internals/serial-stress-test.md has the whole procedure):

  loopback  No rotor software at all. Bridge TX to RX somewhere along the
            link -- on the base's USB-serial adapter, or at the rotor end of
            the cable or slip ring -- and this streams test frames out and
            checks what comes back. Clean at the adapter but not at the far
            end: the cable path is corrupting or losing data.

  rotor     The whole link with the rotor running the Serial Stress app
            (launched from here), but this lean reader standing in for the
            emulator. Errors from the emulator's run but not from this one
            point at the emulator's reader.

Stop the emulator on the base first: only one program can own the port.

    python3 tools/serial_stress.py loopback --port /dev/ttyUSB0 --rate 90
    python3 tools/serial_stress.py rotor --port /dev/ttyUSB0
    python3 tools/serial_stress.py rotor --phase up50 --loop   # soak, Ctrl-C ends
"""

import argparse
import pathlib
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "emulator"))

import host_protocol  # noqa: E402
from serial_stress_host import (  # noqa: E402
    StressHost, describe_icount, icount_reader, sst,
)

APP_SLUG = "demos.serialstress"
JOYSTICK_IDLE = b"*\x00\x00\x00"
JOYSTICK_HZ = 30
# With the plan running, the rotor talks at least every phase (~11 s).
SILENCE_S = 30
# A stop request lets the current phase finish and report.
STOP_WAIT_S = sst.PHASE_MS / 1000 + 10


class StreamParser:
    """Host-protocol framing (docs/internals/host-protocol.md) over a raw
    byte stream, built to survive corruption.

    A line that doesn't parse becomes a junk event, but if a test header is
    glued to its end (a payload tail followed by the next header) parsing
    resumes at that header. A serialtest_up payload that turns out shorter
    than its header claimed -- the next header shows up inside it -- ends
    there, so one dropped byte costs one frame instead of two.
    """

    MAX_LINE = 256
    MAX_PAYLOAD = 512 * 1024
    MARKERS = (b"serialtest_", b"info ")
    # A header starting inside a payload can end past it (one lost byte puts
    # it one byte early), so look that much further before deciding.
    LOOKAHEAD = max(len(marker) for marker in MARKERS) - 1

    def __init__(self):
        self.buffer = bytearray()
        self.pending = None
        self.junk = 0

    def _first_marker(self, start, end):
        found = -1
        for marker in self.MARKERS:
            at = self.buffer.find(marker, start, end)
            if at >= 0 and (found < 0 or at < found):
                found = at
        return found

    def feed(self, data, flush=False):
        """Returns [(command, args, payload)]; command "" marks junk.
        ``flush`` stops holding a complete payload back for the lookahead,
        for when the stream has gone quiet."""
        self.buffer += data
        events = []
        while True:
            if self.pending is not None:
                command, args, length = self.pending
                cut = -1
                needed = length
                if command == sst.UP:
                    needed = length + self.LOOKAHEAD
                    cut = self._first_marker(0, min(needed, len(self.buffer)))
                    if cut >= length:
                        cut = -1
                if cut < 0 and len(self.buffer) < needed and not flush:
                    break
                if cut < 0 and len(self.buffer) < length:
                    break
                end = length if cut < 0 else cut
                payload = bytes(self.buffer[:end])
                del self.buffer[:end]
                self.pending = None
                events.append((command, args, payload))
                continue

            newline = self.buffer.find(b"\n")
            if newline < 0:
                if len(self.buffer) > self.MAX_LINE:
                    at = self._first_marker(1, len(self.buffer))
                    self._junk(events, at if at > 0 else len(self.buffer))
                    continue
                break
            at = self._first_marker(0, newline)
            if at > 0:
                # Garbage glued to the front of a header: drop just that.
                self._junk(events, at)
                continue
            raw = bytes(self.buffer[:newline]).strip()
            del self.buffer[:newline + 1]
            if not raw:
                continue
            try:
                parts = raw.decode("ascii").split()
                length = host_protocol.payload_length(parts[0], tuple(parts[1:]))
            except (UnicodeDecodeError, host_protocol.HostProtocolError, IndexError):
                self.junk += 1
                events.append(("", [], raw))
                continue
            if length > self.MAX_PAYLOAD:
                self.junk += 1
                events.append(("", [], raw))
            elif length:
                self.pending = (parts[0], parts[1:], length)
            else:
                events.append((parts[0], parts[1:], b""))
        return events

    def _junk(self, events, count):
        self.junk += 1
        events.append(("", [], bytes(self.buffer[:count])))
        del self.buffer[:count]


def open_port(port, baud):
    import serial
    if port is None:
        port = guess_port()
    if port is None:
        raise SystemExit("serial_stress: no serial port found; pass --port")
    # A short timeout keeps the reader responsive; writes may block.
    return serial.Serial(port, baud, timeout=0.02)


def guess_port():
    try:
        from serial.tools import list_ports
    except ImportError:
        return None
    candidates = sorted(
        info.device for info in list_ports.comports()
        if any(tag in info.device for tag in ("usbmodem", "usbserial", "ttyACM", "ttyUSB"))
    )
    return candidates[0] if candidates else None


class Writer:
    """Serialises writes from several threads, one whole line at a time."""

    def __init__(self, port):
        self.port = port
        self.lock = threading.Lock()

    def write(self, data):
        with self.lock:
            self.port.write(data)

    def line(self, text):
        self.write(text.encode("ascii") + b"\n")


# --- loopback -------------------------------------------------------------------

def run_loopback(args):
    port = open_port(args.port, args.baud)
    writer = Writer(port)
    read_icount = icount_reader(port)
    rate = sst.line_rate(args.baud) * args.rate // 100
    frame = min(args.frame, sst.MAX_UP_FRAME)
    print("loopback on %s at %d baud: %d%% of the line (%d B/s) in %d-byte frames, %d s rounds" % (
        port.port, args.baud, args.rate, rate, frame, args.seconds))
    print("TX must be bridged to RX somewhere along the link; nothing else may be attached.")
    port.reset_input_buffer()
    round_number = 0
    failed = False
    try:
        while True:
            round_number += 1
            failed |= not loopback_round(port, writer, read_icount, round_number, rate, frame, args.seconds)
            if not args.loop:
                break
    except KeyboardInterrupt:
        print()
    port.close()
    return 1 if failed else 0


def loopback_round(port, writer, read_icount, phase, rate, frame, seconds):
    counter = sst.PhaseCounter(phase)
    parser = StreamParser()
    state = {"sent": 0}
    icount_start = read_icount()

    def send():
        started = time.monotonic()
        sent_bytes = 0
        while True:
            elapsed = time.monotonic() - started
            if elapsed >= seconds:
                break
            if sent_bytes < rate * elapsed:
                seq = state["sent"]
                writer.write(sst.up_header(frame, phase, seq) + b"\n"
                             + bytes(sst.up_payload(phase, seq, frame)))
                state["sent"] += 1
                sent_bytes += frame
            else:
                time.sleep(0.002)

    def check(events):
        for command, fields, payload in events:
            if command != sst.UP:
                if command:
                    parser.junk += 1  # nothing but test frames should come back
                continue
            try:
                _nbytes, frame_phase, seq = (int(value) for value in fields[:3])
            except ValueError:
                parser.junk += 1
                continue
            counter.check(frame_phase, seq, sst.up_payload(frame_phase, seq, frame), payload)

    sender = threading.Thread(target=send, daemon=True)
    sender.start()
    quiet_since = None
    while True:
        data = port.read(port.in_waiting or 1)
        if data:
            quiet_since = None
            check(parser.feed(data))
        elif not sender.is_alive():
            quiet_since = quiet_since or time.monotonic()
            if time.monotonic() - quiet_since > 0.5:
                check(parser.feed(b"", flush=True))
                break
    icount = read_icount()
    sent = state["sent"]
    lost = counter.lost(sent)
    received = counter.ok + counter.bad
    print("round %d: sent %d, %d ok, %d bad, %d lost, %d junk lines, %.0f B/s back" % (
        phase, sent, counter.ok, counter.bad, lost, parser.junk, counter.bytes_ok / seconds))
    if counter.kinds:
        print("  bad frames: " + ", ".join("%d %s" % (n, kind) for kind, n in sorted(counter.kinds.items())))
    for example in counter.examples:
        print("  " + sst.describe_example(example))
    adapter = describe_icount(icount_start, icount)
    if adapter:
        print("  adapter: " + adapter)
    if received == 0:
        print("  nothing came back: is TX bridged to RX?")
        return False
    return counter.bad == 0 and lost == 0 and parser.junk == 0


# --- rotor ----------------------------------------------------------------------

def run_rotor(args):
    port = open_port(args.port, args.baud)
    writer = Writer(port)
    host = StressHost(writer.line, icount=icount_reader(port))
    host.start_pump_thread()
    stop = threading.Event()

    def joystick():
        # What the base sends between games: idle controllers.
        while not stop.is_set():
            writer.write(JOYSTICK_IDLE)
            time.sleep(1 / JOYSTICK_HZ)

    threading.Thread(target=joystick, daemon=True).start()
    if args.phase != "plan":
        index = sst.phase_index(args.phase)
        if index is None:
            raise SystemExit("serial_stress: no phase %r (choose from %s)" % (
                args.phase, ", ".join(phase[0] for phase in sst.PHASES)))
    run_line = "%s %s%s" % (sst.RUN, args.phase, " loop" if args.loop else "")
    if not args.no_launch:
        # Back to the menu first, so the app isn't stacked on itself.
        writer.line("exit")
        time.sleep(1.0)
        writer.line("launch " + APP_SLUG)
        print("launched %s on the rotor; waiting for it to answer..." % APP_SLUG)
    parser = StreamParser()
    started = None
    hello_seen = 0
    last_rx = time.monotonic()
    deadline = last_rx + args.timeout
    if args.no_launch:
        writer.line(run_line)
        started = time.monotonic()
    try:
        while started is None or host.verdict is None:
            now = time.monotonic()
            if started is None and now > deadline:
                print("no answer from the Serial Stress app; is the rotor running a build with it?")
                return 2
            if started is not None and now - last_rx > SILENCE_S:
                print("nothing from the rotor for %d s; giving up" % SILENCE_S)
                return 2
            data = port.read(port.in_waiting or 1)
            if data:
                last_rx = now
            handle_events(parser.feed(data), host)
            if host.hello_count != hello_seen:
                hello_seen = host.hello_count
                if started is None:
                    writer.line(run_line)
                    started = now
                    print("running %s%s" % (args.phase, " in a loop (Ctrl-C stops)" if args.loop else ""))
    except KeyboardInterrupt:
        # The app finishes the phase it is in, then reports as usual.
        print("\nstopping after the current phase (Ctrl-C again to quit now)...")
        writer.line("%s stop" % sst.RUN)
        try:
            deadline = time.monotonic() + STOP_WAIT_S
            while host.verdict is None and time.monotonic() < deadline:
                handle_events(parser.feed(port.read(port.in_waiting or 1)), host)
        except KeyboardInterrupt:
            pass
    finally:
        stop.set()
    port.close()
    return 0 if host.verdict == "clean" else 1


def handle_events(events, host):
    for command, fields, payload in events:
        if not command:
            host.note_junk()
        elif host.handle(command, fields, payload):
            pass
        elif command in ("info", "traceback"):
            print("rotor: " + payload.decode("utf-8", "replace"))
        else:
            host.note_junk()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    for name in ("loopback", "rotor"):
        mode = sub.add_parser(name)
        mode.add_argument("--port", help="serial port (default: first USB serial port)")
        mode.add_argument("--baud", type=int, default=115200,
                          help="must match the rotor's serial_baud in rotor mode (default 115200)")
        mode.add_argument("--loop", action="store_true", help="repeat until Ctrl-C")
    loopback = sub.choices["loopback"]
    loopback.add_argument("--rate", type=int, default=90, help="percent of the line rate (default 90)")
    loopback.add_argument("--frame", type=int, default=512, help="frame payload bytes (default 512)")
    loopback.add_argument("--seconds", type=int, default=10, help="length of each round (default 10)")
    rotor = sub.choices["rotor"]
    rotor.add_argument("--phase", default="plan",
                       help="'plan' (default) or one phase: %s" % ", ".join(p[0] for p in sst.PHASES))
    rotor.add_argument("--no-launch", action="store_true", help="the app is already open on the rotor")
    rotor.add_argument("--timeout", type=float, default=20, help="seconds to wait for the app")
    args = parser.parse_args(argv)
    if args.mode == "loopback":
        return run_loopback(args)
    return run_rotor(args)


if __name__ == "__main__":
    sys.exit(main())
