#!/usr/bin/env python3
"""Find a connected Ventilastation rotor, workbench, or base serial port.

Board selection (--board) is a registry lookup: a one-time `--register`
records a board's USB serial number (its factory MAC -- see normalize_mac())
against a kind in a small local file (see registry_path()), and from then on
selecting that kind is pure USB-descriptor enumeration -- no serial I/O, no
per-invocation wait. `make register-rotor` / `register-workbench` /
`register-base` populate it; `--list` shows anything not yet registered as
`unknown` rather than probing for it (see
docs/internals/input-protocol-v2.md#resync--device-identification for the
RESYNC protocol this used to probe with, and why it was dropped here -- the
per-port round trip made every board-selecting Makefile target pay seconds
it didn't need to. RESYNC itself hasn't gone anywhere; it's just no longer
how this tool identifies a board).

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
import shutil
import subprocess
import sys
from dataclasses import dataclass


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


def inspect_ports() -> list[Board]:
    """Return one Board per candidate port, resolved from the registry (pure
    USB-descriptor enumeration -- no serial I/O). A port whose id isn't in
    the registry comes back with kind=None; register it with `make
    register-rotor`/`register-workbench`/`register-base` to identify it."""
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
        detail = "registry" if kind else "not registered (see 'make register-rotor/workbench/base')"
        boards.append(Board(port=port, kind=kind, mac=mac, detail=detail))
    return boards


def register_board(kind: str, port: str | None) -> None:
    """Remember the connected board's USB id as `kind` in the registry, so
    future --board selection can find it. Trusts the caller: with exactly
    one candidate port attached its id is used as-is; with several, `port`
    must say which one (registration is a deliberate, one-time, human-driven
    action, not something to auto-verify)."""
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
            "(or 'make list-boards' to see what's connected)",
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

    boards = inspect_ports()
    if args.list:
        if boards:
            for board in boards:
                print(format_board(board))
        else:
            print("no USB serial boards found")
        return 0
    if not args.board:
        parser.error("one of --board, --list or --register is required")

    print(choose(boards, args.board, args.mac).port)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
