#!/usr/bin/env python3
"""Screenshot the live POV display: capture what the rotor is driving onto the
LED strips (via the workbench's LED-bus spy), decode the APA102 words, and
render them back into the circular ring the spinning display actually shows.

Optionally launches a game/app first and taps controller buttons so it reaches
a real scene rather than a title/attract screen.

Talks to the DUT over the workbench's USB-serial bridge (launch + button
frames, input-protocol v2 -- see docs/internals/input-protocol-v2.md) and
reads the workbench's Wi-Fi ``frame_apa102`` UDP telemetry (see
docs/internals/workbench.md) for the pixels. The APA102 decode reuses the
desktop emulator's decoder (emulator/apa102.py); colours use the emulator's
default profile, which approximates the board's calibrated one closely enough
to eyeball illumination.

    # NES, pressing Start+A to get past the title screen:
    python3 tools/pov_screenshot.py --slug native.nes \\
        --rom "/vfs/roms/nes/Super Mario Bros. (World).zip" \\
        --press start a --out smb.png

    # Whatever is on the display right now, no launch:
    python3 tools/pov_screenshot.py --no-launch --out now.png
"""

import argparse
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

VSDK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VSDK_ROOT / "tools"))
sys.path.insert(0, str(VSDK_ROOT / "emulator"))

import pov_profile_report as pr  # noqa: E402

COLUMNS = 256
PIXELS = 54
WORKBENCH_TELEMETRY_PORT = 5005
WB_CHUNKS = 64  # a full frame_apa102 arrives as this many chunks

# Button name -> (joy1 mask, extra mask), per input-protocol v2. joy1 bits:
# left=0 right=1 up=2 down=3 A=4 B=5 C=6. extra bits: 2=Start 3=Back(Select)
# 0=Joy1 Y (a.k.a. BUTTON_D).
BUTTONS = {
    "left": (0x01, 0), "right": (0x02, 0), "up": (0x04, 0), "down": (0x08, 0),
    "a": (0x10, 0), "b": (0x20, 0), "c": (0x40, 0), "x": (0x40, 0),
    "y": (0, 0x01), "start": (0, 0x04), "select": (0, 0x08), "back": (0, 0x08),
}


def find_workbench_port():
    out = subprocess.run(
        [sys.executable, str(VSDK_ROOT / "tools/find_board.py"), "--board", "workbench"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        sys.exit(out.stderr.strip() or "could not find the workbench's serial port")
    return out.stdout.strip()


def tap(ser, joy1=0, extra=0, hold=0.12, gap=0.12):
    """Press then release a controller combination (one edge)."""
    pr.send_joystick(ser, joy1=joy1, extra=extra)
    time.sleep(hold)
    pr.send_joystick(ser)
    time.sleep(gap)


def capture_frame(host, timeout=4.0):
    """Return one complete frame_apa102 buffer (COLUMNS*PIXELS*4 bytes) from the
    workbench, or None. The buffer is column-major/led-minor: byte offset for
    (column, led) is (column * PIXELS + led) * 4, each a [GB, B, G, R] datum."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.3)
    frames = {}
    deadline = time.time() + timeout
    sock.sendto(b"hello", (host, WORKBENCH_TELEMETRY_PORT))
    best = None
    while time.time() < deadline:
        try:
            data, _ = sock.recvfrom(2048)
        except socket.timeout:
            sock.sendto(b"hello", (host, WORKBENCH_TELEMETRY_PORT))
            continue
        if len(data) < 6 or data[0] != 0xA1:
            continue
        seq = struct.unpack("<I", data[1:5])[0]
        frames.setdefault(seq, {})[data[5]] = data[6:]
        if len(frames[seq]) == WB_CHUNKS:
            best = seq
            break
    sock.close()
    if best is None:
        if not frames:
            return None
        best = max(frames, key=lambda s: len(frames[s]))
        if len(frames[best]) != WB_CHUNKS:
            return None
    return b"".join(frames[best][k] for k in sorted(frames[best]))


def render_polar(raw, size=480):
    """Render a captured frame_apa102 buffer as the circular POV image (PIL).

    Geometry mirrors web/led-render-core.js: column c is at angle
    -c*2pi/COLUMNS + pi, LED 0 is the ring centre and LED PIXELS-1 the outer
    rim (radius linear in the LED index, matching the driver's projection
    table)."""
    import numpy as np
    from PIL import Image
    from apa102 import decode_frame

    rgb = decode_frame(raw)  # uint32 0xFFBBGGRR, one per LED, index col*PIXELS+led
    grid = np.stack([rgb & 0xFF, (rgb >> 8) & 0xFF, (rgb >> 16) & 0xFF], axis=1)
    grid = grid.astype(np.uint8).reshape(COLUMNS, PIXELS, 3)

    centre = size / 2.0
    radius = size / 2.0 - 2
    ys, xs = np.mgrid[0:size, 0:size]
    dx = xs - centre
    dy = ys - centre
    rr = np.sqrt(dx * dx + dy * dy)
    ang = np.arctan2(dy, dx)
    col = np.mod(np.round((np.pi - ang) * COLUMNS / (2 * np.pi)).astype(np.int64), COLUMNS)
    led = np.clip((rr / radius * PIXELS).astype(np.int64), 0, PIXELS - 1)
    inside = rr <= radius
    out = np.zeros((size, size, 3), dtype=np.uint8)
    out[inside] = grid[col[inside], led[inside]]
    return Image.fromarray(out, "RGB")


def lit_fraction(raw):
    import numpy as np
    arr = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 4)
    return float(np.mean((arr[:, 1:] != 0).any(axis=1)))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, help="output PNG path")
    parser.add_argument("--port", help="workbench serial port (default: auto-detect)")
    parser.add_argument("--host", default="ventilastation-workbench.local",
                        help="workbench Wi-Fi host/IP for the frame_apa102 UDP telemetry")
    parser.add_argument("--rpm", type=int, default=600, help="simulated hall RPM")
    parser.add_argument("--slug", help="app/game slug to launch, e.g. native.nes, alecu.vixeous")
    parser.add_argument("--rom", help="ROM path on the board for native ROM-library apps")
    parser.add_argument("--press", nargs="+", default=[], metavar="BTN",
                        help="controller buttons to tap after launch: " + ", ".join(sorted(BUTTONS)))
    parser.add_argument("--press-count", type=int, default=6, help="how many times to tap the --press buttons")
    parser.add_argument("--no-launch", action="store_true", help="capture the current display without launching anything")
    parser.add_argument("--boot-timeout", type=float, default=25.0, help="seconds to wait for a native app's boot banner")
    parser.add_argument("--settle", type=float, default=3.0, help="seconds to wait after the button taps before capturing")
    parser.add_argument("--size", type=int, default=480, help="output image size in pixels (square)")
    args = parser.parse_args()

    unknown = [b for b in args.press if b.lower() not in BUTTONS]
    if unknown:
        parser.error("unknown button(s): %s (known: %s)" % (", ".join(unknown), ", ".join(sorted(BUTTONS))))
    if not args.no_launch and not args.slug:
        parser.error("--slug is required unless --no-launch is given")

    # mDNS (.local) resolution can be flaky; retry a few times before giving up.
    host = args.host
    for attempt in range(5):
        try:
            host = socket.gethostbyname(args.host)
            break
        except OSError:
            if attempt == 4:
                print(f"warning: could not resolve {args.host}; using it as-is "
                      "(pass --host <ip> if telemetry never arrives)", file=sys.stderr)
            else:
                time.sleep(0.5)

    import serial  # local import: only needed for a real run
    port = args.port or find_workbench_port()
    print(f"workbench serial: {port}   telemetry host: {host}")

    ser = serial.Serial(port, 115200, timeout=0.1)
    reader = pr.WireReader(ser)
    try:
        pr.set_rpm(host, args.rpm)
        time.sleep(1.0)
        if not args.no_launch:
            pr.return_to_menu(ser, reader, came_from_native=True, banner_timeout=3)
            line = "launch " + args.slug + (" " + args.rom if args.rom else "")
            print(">> " + line)
            pr.send_line(ser, line)
            is_native = args.slug.startswith("native.")
            if is_native and not reader.wait_for(pr.BOOT_BANNER, timeout=args.boot_timeout):
                print("  warning: no boot banner seen", file=sys.stderr)
            time.sleep(3.0)  # reach the title screen
            for _ in range(args.press_count if args.press else 0):
                for name in args.press:
                    joy1, extra = BUTTONS[name.lower()]
                    tap(ser, joy1=joy1, extra=extra)
                time.sleep(0.4)
            time.sleep(args.settle)

        raw = capture_frame(host)
        if raw is None:
            sys.exit("no complete frame captured from the workbench (is it streaming? is the DUT spinning?)")
        img = render_polar(raw, size=args.size)
        img.save(args.out)
        print(f"saved {args.out}  ({lit_fraction(raw) * 100:.0f}% of LEDs lit)")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
