#!/usr/bin/env python3
"""Profile POV render timing across RPMs and games, and print a report.

For each RPM in --rpms and each game in --games: launch it, let it settle
for --settle seconds, run the on-device povperf profiler for --duration
seconds, and record the timing it reports (see the "povperf" commands in
docs/internals/input-protocol-v2.md -- the same profiler and wire protocol
work for both MicroPython games and native retro-go apps like Voom, see
hardware/rotor/modules/povdisplay/povdisplay.c and
apps/retro-go/components/retro-go/drivers/display/ventilastation_pov.c).

Talks to the DUT over the workbench's USB-serial bridge (transparent to the
DUT's base-station UART -- see docs/internals/workbench.md) and, by default,
controls the workbench's simulated hall-sensor RPM through a reserved
USB-local command channel. Requires:
  - the rotor board flashed with a povperf/launch-command-capable image
    (see tools/upgrade_board.py);
  - the workbench connected over USB. Wi-Fi is optional and only used with
    ``--rpm-control wifi``.

Game slugs match ventilastation.native_apps.APP_REGISTRY / app_loader
slugs, e.g. "native.voom" (Voom/prboom-go) or "alecu.vixeous" (Vixeous).

    python3 tools/pov_profile_report.py \\
        --rpms 600 650 700 \\
        --games prboom=native.voom vixious=alecu.vixeous
"""

import argparse
import socket
import subprocess
import sys
import time
import zlib
from pathlib import Path

VSDK_ROOT = Path(__file__).resolve().parents[1]

# povstress (games/demos/povstress) is a fixed, reproducible heavy vs2 scene
# built for profiling -- constant sprite/tilemap load every run, unlike a real
# game whose load varies with play. Replaces the earlier ad hoc use of Vixeous
# as the MicroPython profiling subject.
DEFAULT_GAMES = ["prboom=native.voom", "povstress=demos.povstress"]
DEFAULT_RPMS = [600, 650, 700]
WORKBENCH_TELEMETRY_PORT = 5005
BOOT_BANNER = "VENTILASTATION ROTOR"
# Any joystick byte with a bit set works; JOY_UP (bit 2) is harmless in every
# menu/game and never triggers a shot/bomb/back edge.
WIGGLE_JOY1 = 1 << 2
WORKBENCH_USB_CONTROL_ESCAPE = 0xD3


def find_workbench_port():
    out = subprocess.run(
        [sys.executable, str(VSDK_ROOT / "tools/find_board.py"), "--board", "workbench"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        sys.exit(out.stderr.strip() or "could not find the workbench's serial port")
    return out.stdout.strip()


class WireReader:
    """Parses the board's line(+length-prefixed payload) wire protocol.

    ``info N``, ``traceback N``, ``povcal_state ... N``, and the workbench's
    checksummed ``wb_frame N CRC32`` response are binary payload frames.
    Everything else is a plain text line.
    """

    def __init__(self, ser):
        self.ser = ser
        self.buf = bytearray()
        self.pending = None

    def _fill(self, timeout):
        deadline = time.time() + timeout
        got_any = False
        while time.time() < deadline:
            chunk = self.ser.read(4096)
            if chunk:
                self.buf += chunk
                got_any = True
            else:
                time.sleep(0.01)
        return got_any

    def _pop_line(self):
        nl = self.buf.find(b"\n")
        if nl < 0:
            return None
        line = bytes(self.buf[:nl])
        del self.buf[:nl + 1]
        try:
            return line.decode("ascii")
        except UnicodeDecodeError:
            return ""

    def read_for(self, duration, on_event=None):
        """Read for `duration` seconds, returning a list of (kind, value)."""
        events = []
        deadline = time.time() + duration
        while time.time() < deadline:
            self._fill(min(0.2, max(0.0, deadline - time.time())))
            while True:
                if self.pending is not None:
                    kind, n, metadata = self.pending
                    if len(self.buf) < n:
                        break
                    payload = bytes(self.buf[:n])
                    del self.buf[:n]
                    self.pending = None
                    if kind in ("info", "traceback"):
                        try:
                            value = payload.decode("utf-8")
                        except UnicodeDecodeError:
                            value = repr(payload)
                        event = (kind, value)
                    elif kind == "wb_frame":
                        expected_crc = metadata
                        actual_crc = zlib.crc32(payload) & 0xffffffff
                        if actual_crc == expected_crc:
                            event = (kind, payload)
                        else:
                            event = (
                                "wb_frame_crc_error",
                                "expected=%08x actual=%08x" % (expected_crc, actual_crc),
                            )
                    else:
                        event = (kind, payload)
                    events.append(event)
                    if on_event:
                        on_event(event)
                    continue

                text = self._pop_line()
                if text is None:
                    break
                parts = text.split()
                if len(parts) == 2 and parts[0] in ("info", "traceback") and parts[1].isdigit():
                    self.pending = (parts[0], int(parts[1]), None)
                    continue
                elif (len(parts) == 4 and parts[0] == "povcal_state"
                      and all(part.isdigit() for part in parts[1:])):
                    self.pending = ("povcal_state", int(parts[3]), tuple(map(int, parts[1:3])))
                    continue
                elif (len(parts) == 3 and parts[0] == "wb_frame"
                      and parts[1].isdigit()):
                    try:
                        crc = int(parts[2], 16)
                    except ValueError:
                        event = ("line", text)
                    else:
                        self.pending = ("wb_frame", int(parts[1]), crc)
                        continue
                elif text.strip():
                    event = ("line", text)
                else:
                    continue
                events.append(event)
                if on_event:
                    on_event(event)
        return events

    def wait_for(self, needle, timeout):
        """Block until a line containing `needle` is seen, or timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            found = []
            self.read_for(min(0.5, max(0.0, deadline - time.time())),
                           on_event=lambda ev: found.append(ev))
            for kind, text in found:
                if kind == "line" and needle in text:
                    return True
        return False

    def wait_for_event(self, kind, timeout):
        """Return the next value for an event kind, or ``None`` on timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            events = self.read_for(min(0.5, max(0.0, deadline - time.time())))
            for event_kind, value in events:
                if event_kind == kind:
                    return value
                if kind == "wb_frame" and event_kind == "wb_frame_crc_error":
                    raise RuntimeError("workbench frame CRC mismatch: " + value)
        return None


def send_line(ser, text):
    ser.write((text + "\n").encode("ascii"))
    ser.flush()


def send_workbench_command(ser, text):
    ser.write(bytes([WORKBENCH_USB_CONTROL_ESCAPE]) + text.encode("ascii") + b"\n")
    ser.flush()


def set_workbench_rpm_usb(ser, reader, rpm, timeout=2.0):
    send_workbench_command(ser, "rpm %d" % rpm)
    if not reader.wait_for("wb_ok rpm=%d" % min(max(rpm, 0), 700), timeout):
        raise RuntimeError("workbench did not acknowledge USB RPM command")


def capture_workbench_frame(ser, reader, timeout=8.0):
    send_workbench_command(ser, "capture")
    frame = reader.wait_for_event("wb_frame", timeout)
    if frame is None:
        raise RuntimeError("workbench did not return a USB frame capture")
    return frame


def send_joystick(ser, joy1=0, joy2=0, extra=0):
    ser.write(bytes([0x2A, joy1 & 0x7F, joy2 & 0x7F, extra & 0x7F]))
    ser.flush()


def wiggle(ser):
    """Send a press+release edge so the board's 30s input-idle timeout
    (see director.py's INPUT_TIMEOUT / director.timedout, which several
    games including Vixeous check to auto-return to the menu) never fires
    mid-profile just because this script isn't a real joystick."""
    send_joystick(ser, joy1=WIGGLE_JOY1)
    time.sleep(0.05)
    send_joystick(ser)


def set_rpm(host, rpm):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(f"rpm {rpm}\n".encode("ascii"), (host, WORKBENCH_TELEMETRY_PORT))
    finally:
        sock.close()


def parse_kv_line(text, prefix):
    if not text.startswith(prefix):
        return None
    fields = {}
    for token in text[len(prefix):].split():
        if "=" in token:
            key, value = token.split("=", 1)
            fields[key] = value
    return fields


def return_to_menu(ser, reader, came_from_native, banner_timeout=20):
    """Send "exit" and, only if it's expected to trigger a reboot (leaving a
    native app), wait for the post-reboot banner. Harmless no-op wait
    otherwise: "exit" from MicroPython just pops to the menu root in place,
    no reboot -- see docs/internals/input-protocol-v2.md's Command
    Reference. A short, non-fatal probe covers "don't actually know yet"
    (e.g. at startup): a banner arriving still short-circuits the wait, a
    timeout is simply treated as "was already on MicroPython"."""
    send_line(ser, "exit")
    if came_from_native:
        if not reader.wait_for(BOOT_BANNER, timeout=banner_timeout):
            print(f"  warning: no boot banner seen within {banner_timeout}s after exit",
                  file=sys.stderr)
    else:
        reader.wait_for(BOOT_BANNER, timeout=1.0)


def profile_run(
        ser, reader, label, slug, is_native, settle, duration,
        keep_awake=True, before_exit=None, after_launch=None):
    send_line(ser, "launch " + slug)
    if is_native:
        # Native launches show a brief loading scene (NativeLaunchScene's
        # 1s call_later) before the actual partition-switch reboot, then
        # boot prboom-go from scratch (WAD load, intro music, ...) -- all
        # of that needs to finish, and the boot banner is our signal that
        # vs_host_bridge's command handler is alive again, before the
        # user-requested "wait N seconds so it settles" even starts
        # counting. See vs_host_bridge_init() in vs_host_bridge.c.
        if not reader.wait_for(BOOT_BANNER, timeout=20):
            print(f"  warning: no boot banner seen within 20s after launching {slug}",
                  file=sys.stderr)
    wiggle(ser)
    time.sleep(settle)
    if after_launch is not None:
        after_launch()

    send_line(ser, "povperf start")
    # Every povperf command (start/stop/status/...) echoes its own
    # povperf_state/povperf_timing pair (see pov_profiling.py's
    # _send_stats() and vs_povperf_send_stats() in vs_host_bridge.c) --
    # "start"'s is always samples=0, right after the reset it just did.
    # Drain it here so it can't be mistaken for the real reading below.
    reader.read_for(0.3)
    if keep_awake:
        half = max(0.0, duration / 2)
        time.sleep(half)
        wiggle(ser)
        time.sleep(duration - half)
    else:
        time.sleep(duration)

    send_line(ser, "povperf stop")
    events = reader.read_for(2.0)

    # Keep the *last* match of each: belt-and-braces against any stray
    # leftover povperf_state/timing lines from other commands sharing this
    # read window (e.g. the drain above racing a slow reply).
    state = None
    timing = None
    for kind, text in events:
        if kind != "line":
            continue
        state = parse_kv_line(text, "povperf_state ") or state
        timing = parse_kv_line(text, "povperf_timing ") or timing

    # Hardware acceptance uses this hook for an illustrative frame capture.
    # It runs after profiling has stopped, so USB transfer time cannot affect
    # the measured window, and before leaving the scene being reported.
    if before_exit is not None:
        before_exit()
    return_to_menu(ser, reader, came_from_native=is_native)
    return state, timing


def to_int(fields, key, default=0):
    try:
        return int(fields.get(key, default))
    except (TypeError, ValueError):
        return default


def build_report_row(rpm, label, slug, state, timing):
    row = {"rpm": rpm, "game": label, "slug": slug, "ok": bool(timing and state)}
    if not row["ok"]:
        return row
    samples = to_int(timing, "samples")
    overruns = to_int(timing, "overruns")
    skipped = to_int(timing, "skipped")
    row.update({
        "encoder": state.get("encoder", "?"),
        "samples": samples,
        "deadline_us": to_int(timing, "deadline_us"),
        "overrun_pct": (100.0 * overruns / samples) if samples else 0.0,
        "overruns": overruns,
        "skipped": skipped,
        # skipped columns are extra angle steps the GPU task never visited
        # between two updates -- express as a fraction of the full column
        # count actually covered (samples + the ones jumped over).
        "skip_pct": (100.0 * skipped / (samples + skipped)) if (samples + skipped) else 0.0,
        "avg_total_us": to_int(timing, "avg_total_us"),
        "max_total_us": to_int(timing, "max_total_us"),
        # MicroPython calls the render phase avg_render_us; retro-go calls
        # it avg_project_us (two project_angle() calls per column). Same
        # meaning, different field name -- see the profiler struct comments
        # in povdisplay.c / ventilastation_pov.h.
        "avg_render_us": to_int(timing, "avg_render_us", to_int(timing, "avg_project_us")),
        "max_render_us": to_int(timing, "max_render_us", to_int(timing, "max_project_us")),
        "avg_spi_us": to_int(timing, "avg_spi_wait_us", to_int(timing, "avg_spi_us")),
        "max_spi_us": to_int(timing, "max_spi_wait_us", to_int(timing, "max_spi_us")),
        "worst_slack_us": to_int(timing, "worst_slack_us"),
        "project_samples": to_int(timing, "project_samples"),
        "frames": to_int(timing, "frames"),
        "frame_deadline_us": to_int(timing, "frame_deadline_us"),
        "frame_overruns": to_int(timing, "frame_overruns"),
        "avg_frame_render_us": to_int(timing, "avg_frame_render_us"),
        "max_frame_render_us": to_int(timing, "max_frame_render_us"),
        "heap_start": to_int(state, "heap_start", -1),
        "heap_free": to_int(state, "heap_free", -1),
        "heap_delta": to_int(state, "heap_delta", -1),
    })
    return row


def print_report(rows):
    print()
    print("=" * 100)
    print("POV render timing report")
    print("=" * 100)
    header = (
        f"{'RPM':>5} {'game':<10} {'enc':<10} {'samples':>8} {'deadline':>9} "
        f"{'overrun%':>9} {'skip%':>7} {'avg_tot':>8} {'max_tot':>8} "
        f"{'frames':>7} {'avg_frm':>8} {'max_frm':>8} {'heap_d':>8} {'worst_slk':>10}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        if not row["ok"]:
            print(f"{row['rpm']:>5} {row['game']:<10} FAILED (no povperf response)")
            continue
        print(
            f"{row['rpm']:>5} {row['game']:<10} {row['encoder']:<10} {row['samples']:>8} "
            f"{row['deadline_us']:>9} {row['overrun_pct']:>8.2f}% {row['skip_pct']:>6.2f}% "
            f"{row['avg_total_us']:>8} {row['max_total_us']:>8} {row['frames']:>7} "
            f"{row['avg_frame_render_us']:>8} {row['max_frame_render_us']:>8} "
            f"{row['heap_delta']:>8} {row['worst_slack_us']:>10}"
        )
    print("-" * len(header))
    print(
        "overrun% = columns whose render+SPI time exceeded the rotation's per-column budget "
        "(deadline_us). skip% = angle steps the GPU task never visited at all between two "
        "updates, as a share of columns actually covered. avg_frm/max_frm are complete "
        "256-column projection times, including the calibrated output path. heap_d is the "
        "change in free MicroPython heap after a collection (negative means retained growth)."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="workbench serial port (default: auto-detect via find_board.py)")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--workbench-host", default="ventilastation-workbench.local",
                         help="workbench Wi-Fi hostname/IP for RPM control (UDP)")
    parser.add_argument(
        "--rpm-control", choices=("usb", "wifi"), default="usb",
        help="how to control the workbench hall simulator (default: usb)",
    )
    parser.add_argument("--rpms", type=int, nargs="+", default=DEFAULT_RPMS)
    parser.add_argument(
        "--games", nargs="+", default=DEFAULT_GAMES,
        help="label=slug pairs, e.g. prboom=native.voom vixious=alecu.vixeous",
    )
    parser.add_argument("--settle", type=float, default=2.0, help="seconds to wait after launch before profiling")
    parser.add_argument("--duration", type=float, default=5.0, help="seconds to run the profiler for")
    args = parser.parse_args()

    games = []
    for spec in args.games:
        label, _, slug = spec.partition("=")
        if not slug:
            parser.error(f"--games entry must be label=slug, got {spec!r}")
        games.append((label, slug))

    import serial  # local import: only needed once args are known to be sane

    port = args.port or find_workbench_port()
    print(f"Using workbench serial port: {port}")
    if args.rpm_control == "wifi":
        print(f"Using workbench host for RPM control: {args.workbench_host}")
    else:
        print("Using the workbench USB-local channel for RPM control")

    ser = serial.Serial(port, args.baud, timeout=0.1)
    reader = WireReader(ser)
    try:
        # Normalize starting state: pop back to the MicroPython menu root
        # regardless of what's currently running. Don't know yet whether
        # that means a reboot (a native app was running) or an instant
        # no-op (already on MicroPython) -- a short probe covers both
        # without a scary wait/warning for the common case.
        return_to_menu(ser, reader, came_from_native=True, banner_timeout=3)

        rows = []
        for rpm in args.rpms:
            print(f"\n--- RPM {rpm} ---")
            if args.rpm_control == "usb":
                set_workbench_rpm_usb(ser, reader, rpm)
            else:
                set_rpm(args.workbench_host, rpm)
            time.sleep(1.0)
            for label, slug in games:
                is_native = slug.startswith("native.")
                print(f"  {label} ({slug}): launch, settle {args.settle}s, "
                      f"profile {args.duration}s ...")
                state, timing = profile_run(
                    ser, reader, label, slug, is_native, args.settle, args.duration,
                )
                row = build_report_row(rpm, label, slug, state, timing)
                rows.append(row)
                if row["ok"]:
                    print(f"    samples={row['samples']} overrun%={row['overrun_pct']:.2f} "
                          f"skip%={row['skip_pct']:.2f}")
                else:
                    print("    FAILED to get a povperf response", file=sys.stderr)
    finally:
        ser.close()

    print_report(rows)
    return 0 if all(row["ok"] for row in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
