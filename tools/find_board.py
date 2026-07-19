#!/usr/bin/env python3
"""Find a connected Ventilastation rotor, workbench, or base serial port.

Board selection (--board) is a registry lookup: a one-time `--register`
records a board's USB serial number (its factory MAC -- see normalize_mac())
against a kind in a small local file (see registry_path()), and from then on
selecting that kind is pure USB-descriptor enumeration -- no serial I/O, no
multi-second wait. `make register-rotor` / `register-workbench` /
`register-base` populate it.

Boards that aren't registered fall back to the RESYNC protocol (see
docs/internals/input-protocol-v2.md#resync--device-identification): all
three Ventilastation devices answer the same marker the same way -- stop,
reset, and print ``VENTILASTATION <NAME> <version> <githash>`` as the first
thing after that reset. This is a uniform, always-recognized probe that
works regardless of what a device happens to be doing (including a rotor
running a native retro-go app instead of MicroPython, or a wedged device of
any kind), but it costs a per-port round trip -- seconds, not
milliseconds -- so `--board` only falls back to it when asked
(probe_unknown); `--list` always does, to fully identify whatever's plugged
in.

The rotor and workbench both expose ESP32-S3 native USB-Serial-JTAG (baud
rate is effectively ignored by that USB-CDC interface); the base Arduino is
a real UART at 57600 baud, typically reached via its own USB-to-serial
adapter during bench testing. Each port is probed at 115200 first, then
57600 if nothing answered.

Only Python's standard library is used, so this works before an ESP-IDF
virtualenv (and pyserial) is active.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import re
import select
import shutil
import subprocess
import sys
import termios
import time
from dataclasses import dataclass


RESYNC = b"\n\n\xd2ESYNC\n"
ID_PREFIX = b"VENTILASTATION "
BOARD_KIND_BY_NAME = {
    b"WORKBENCH": "workbench",
    b"ROTOR": "ventilastation",  # kept as the existing --board value
    b"BASE": "base",
}
PROBE_BAUD_RATES = (115200, 57600)


@dataclass
class Board:
    port: str
    kind: str | None = None
    mac: str | None = None
    detail: str = ""


def normalize_mac(value: str) -> str:
    return re.sub(r"[^0-9a-f]", "", value.lower())


# --- USB id -> board kind registry ---------------------------------------
# Populated by `--register` (see register_board()). Keyed by normalize_mac()
# so lookups don't care about colon/dash formatting.

def registry_path() -> pathlib.Path:
    if sys.platform == "darwin":
        base = pathlib.Path.home() / "Library" / "Application Support"
    else:
        base = pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or (pathlib.Path.home() / ".config"))
    return base / "vsdk" / "boards.json"


def load_registry() -> dict[str, str]:
    try:
        return json.loads(registry_path().read_text())
    except (OSError, ValueError):
        return {}


def save_registry(registry: dict[str, str]) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n")


def candidate_ports() -> list[str]:
    """Return preferred, non-duplicate USB serial device names."""
    if sys.platform == "darwin":
        patterns = ["/dev/cu.usbmodem*", "/dev/cu.SLAB_USBtoUART*", "/dev/cu.usbserial*"]
    elif sys.platform.startswith("linux"):
        by_id = sorted(glob.glob("/dev/serial/by-id/*"))
        if by_id:
            return by_id
        patterns = ["/dev/ttyACM*", "/dev/ttyUSB*"]
    else:
        patterns = ["/dev/ttyACM*", "/dev/ttyUSB*", "/dev/cu.*"]

    ports: list[str] = []
    for pattern in patterns:
        for port in sorted(glob.glob(pattern)):
            if port not in ports:
                ports.append(port)
    return ports


def macos_port_macs() -> dict[str, str]:
    """Map macOS callout devices to USB serial numbers using IOKit output."""
    if sys.platform != "darwin" or not shutil.which("ioreg"):
        return {}
    try:
        output = subprocess.check_output(
            ["ioreg", "-p", "IOService", "-l", "-w", "0"],
            text=True,
            # ioreg can include arbitrary USB descriptor bytes that are not
            # valid UTF-8.  We only inspect its ASCII property names and
            # device paths, so preserve those while replacing malformed data.
            errors="replace",
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return {}

    result: dict[str, str] = {}
    current_mac: str | None = None
    for line in output.splitlines():
        serial_match = re.search(r'USB Serial Number"\s*=\s*"([^"]+)"', line)
        if serial_match:
            current_mac = serial_match.group(1)
        port_match = re.search(r'IOCalloutDevice"\s*=\s*"(/dev/cu\.[^"]+)"', line)
        if port_match and current_mac:
            result[port_match.group(1)] = current_mac
    return result


def linux_port_mac(port: str) -> str | None:
    if not sys.platform.startswith("linux"):
        return None
    name = os.path.basename(port)
    match = re.search(r"([0-9a-f]{2}(?:[^0-9a-f][0-9a-f]{2}){5})", name, re.I)
    if not match:
        match = re.search(r"(?<![0-9a-f])([0-9a-f]{12})(?![0-9a-f])", name, re.I)
    return match.group(1) if match else None


def read_available(fd: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        try:
            chunk = os.read(fd, 4096)
        except (BlockingIOError, OSError):
            break
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def read_for(fd: int, seconds: float) -> bytes:
    end = time.monotonic() + seconds
    data = bytearray()
    while time.monotonic() < end:
        remaining = max(0.0, end - time.monotonic())
        try:
            readable, _, _ = select.select([fd], [], [], min(0.05, remaining))
        except (OSError, ValueError):
            break
        if readable:
            data.extend(read_available(fd))
    return bytes(data)


def write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        try:
            offset += os.write(fd, data[offset:])
        except BlockingIOError:
            time.sleep(0.01)


_BAUD_CONSTANTS = {115200: termios.B115200, 57600: termios.B57600}


def configure_serial(fd: int, baud: int) -> list:
    saved = termios.tcgetattr(fd)
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CLOCAL | termios.CREAD | termios.CS8
    attrs[3] = 0
    attrs[4] = _BAUD_CONSTANTS[baud]
    attrs[5] = _BAUD_CONSTANTS[baud]
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 1
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    return saved


def restore_serial(fd: int, saved: list) -> None:
    try:
        termios.tcsetattr(fd, termios.TCSANOW, saved)
    except (OSError, termios.error):
        pass


def parse_identification(response: bytes) -> str | None:
    """Extract the board kind from a RESYNC identification line, if present."""
    index = response.find(ID_PREFIX)
    if index == -1:
        return None
    rest = response[index + len(ID_PREFIX):]
    name = rest.split(b" ", 1)[0].split(b"\n", 1)[0].split(b"\r", 1)[0]
    return BOARD_KIND_BY_NAME.get(name)


def probe_port_at_baud(fd: int, baud: int) -> str | None:
    saved = configure_serial(fd, baud)
    try:
        read_for(fd, 0.15)  # drain whatever was already buffered
        write_all(fd, RESYNC)
        # Generous window: every device actually resets (the base Arduino
        # reinitializes in place instead, but the window doesn't need to
        # distinguish the two) before printing its identification line.
        response = read_for(fd, 2.5)
        return parse_identification(response)
    finally:
        restore_serial(fd, saved)


def probe_port(port: str) -> tuple[str | None, str]:
    """Return (board kind, evidence) for one port."""
    try:
        fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError as exc:
        return None, f"cannot open: {exc}"

    try:
        for baud in PROBE_BAUD_RATES:
            kind = probe_port_at_baud(fd, baud)
            if kind:
                return kind, f"RESYNC identification at {baud} baud"
        return None, "no recognized board response"
    except (OSError, termios.error) as exc:
        return None, f"probe failed: {exc}"
    finally:
        os.close(fd)


def inspect_ports(probe_unknown: bool = True) -> list[Board]:
    """Return one Board per candidate port. A port whose USB id is in the
    registry resolves instantly from there (no serial I/O). A port that
    isn't registered falls back to the RESYNC probe when probe_unknown is
    set; otherwise it's reported unresolved rather than paying the probe's
    multi-second worst case."""
    macs = macos_port_macs()
    registry = load_registry()
    boards: list[Board] = []
    ports = candidate_ports()
    if sys.platform == "darwin":
        # A native USB-JTAG reset can briefly leave a stale usbmodem node
        # behind. Espressif exposes the chip MAC as a 12-hex-digit USB serial;
        # discard transient nodes with a different serial shape.
        ports = [
            port
            for port in ports
            if port not in macs or len(normalize_mac(macs[port])) == 12
        ]
    for port in ports:
        mac = macs.get(port) or linux_port_mac(port)
        kind = registry.get(normalize_mac(mac)) if mac else None
        if kind:
            boards.append(Board(port=port, kind=kind, mac=mac, detail="registry"))
            continue
        if probe_unknown:
            kind, detail = probe_port(port)
        else:
            kind, detail = None, "not registered (see 'make register-rotor/workbench/base')"
        boards.append(Board(port=port, kind=kind, mac=mac, detail=detail))
    return boards


def register_board(kind: str, port: str | None) -> None:
    """Remember the connected board's USB id as `kind` in the registry, so
    future --board selection skips probing it entirely. Trusts the caller:
    with exactly one candidate port attached its id is used as-is; with
    several, `port` must say which one (no RESYNC verification either way --
    registration is a deliberate, one-time, human-driven action)."""
    macs = macos_port_macs()
    ports = candidate_ports()
    if sys.platform == "darwin":
        ports = [p for p in ports if p not in macs or len(normalize_mac(macs[p])) == 12]

    if port:
        if port not in ports:
            print(f"{port} is not a candidate serial port; run 'make list-boards'", file=sys.stderr)
            raise SystemExit(2)
        chosen = port
    elif len(ports) == 1:
        chosen = ports[0]
    elif not ports:
        print("no USB serial boards found; is it connected?", file=sys.stderr)
        raise SystemExit(2)
    else:
        print("more than one board is attached; pass PORT=... to choose one:", file=sys.stderr)
        for p in ports:
            mac = macs.get(p) or linux_port_mac(p)
            print(f"  {p}" + (f"  MAC={mac}" if mac else ""), file=sys.stderr)
        raise SystemExit(2)

    mac = macs.get(chosen) or linux_port_mac(chosen)
    if not mac:
        print(f"{chosen} has no readable USB serial number; can't register it this way", file=sys.stderr)
        raise SystemExit(2)

    registry = load_registry()
    registry[normalize_mac(mac)] = kind
    save_registry(registry)
    print(f"Registered {kind}: {mac} ({chosen}) -> {registry_path()}")


def format_board(board: Board) -> str:
    kind = board.kind or "unknown"
    mac = f"  MAC={board.mac}" if board.mac else ""
    return f"{kind:16} {board.port}{mac}"


_REGISTER_TARGET = {"ventilastation": "register-rotor", "workbench": "register-workbench", "base": "register-base"}


def choose(boards: list[Board], requested: str, mac: str | None) -> Board:
    matches = [board for board in boards if board.kind == requested]
    if mac:
        wanted = normalize_mac(mac)
        matches = [board for board in matches if board.mac and normalize_mac(board.mac) == wanted]

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"more than one {requested} board is attached; pass PORT=... to choose one:", file=sys.stderr)
        for board in matches:
            print(f"  {board.port}" + (f"  MAC={board.mac}" if board.mac else ""), file=sys.stderr)
    elif mac:
        print(f"no {requested} board matches MAC={mac}; run 'make list-boards'", file=sys.stderr)
    else:
        print(
            f"no registered {requested} board attached; run 'make {_REGISTER_TARGET[requested]}' "
            "(or 'make list-boards' to probe what's connected)",
            file=sys.stderr,
        )
    raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", choices=("ventilastation", "workbench", "base"), help="board type to select")
    parser.add_argument("--mac", help="USB-JTAG serial/MAC to select")
    parser.add_argument("--list", action="store_true", help="list and classify all candidate ports")
    parser.add_argument(
        "--register",
        choices=("ventilastation", "workbench", "base"),
        help="remember the connected board's USB id as this kind (see registry_path())",
    )
    parser.add_argument("--port", help="with --register: which port to register, when several are attached")
    args = parser.parse_args()

    if args.register:
        register_board(args.register, args.port)
        return 0

    if args.list:
        boards = inspect_ports()
        if boards:
            for board in boards:
                print(format_board(board))
        else:
            print("no USB serial boards found")
        return 0
    if not args.board:
        parser.error("one of --board, --list or --register is required")

    # No RESYNC fallback here: --board is the hot path every flash/provision
    # target goes through, and a registered board should never pay for a
    # multi-second probe just to find its own port again.
    boards = inspect_ports(probe_unknown=False)
    print(choose(boards, args.board, args.mac).port)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
