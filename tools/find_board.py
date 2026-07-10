#!/usr/bin/env python3
"""Find a connected Ventilastation or workbench USB serial port.

Both boards use the ESP32-S3 native USB-Serial-JTAG device, so their USB
descriptors are identical. This tool uses a firmware-level probe:

* the workbench firmware answers ``VSDK_BOARD_PROBE`` itself;
* the Ventilastation MicroPython firmware answers with its explicit board ID
  through the USB REPL.

Only Python's standard library is used, so this works before an ESP-IDF
virtualenv (and pyserial) is active.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import select
import shutil
import subprocess
import sys
import termios
import time
from dataclasses import dataclass


PROBE = b"VSDK_BOARD_PROBE\n"
WORKBENCH_REPLY = b"VSDK_BOARD_ID=workbench"
ROTOR_REPLY = b"VSDK_BOARD_ID=ventilastation"


@dataclass
class Board:
    port: str
    kind: str | None = None
    mac: str | None = None
    detail: str = ""


def normalize_mac(value: str) -> str:
    return re.sub(r"[^0-9a-f]", "", value.lower())


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


def configure_serial(fd: int) -> list:
    saved = termios.tcgetattr(fd)
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CLOCAL | termios.CREAD | termios.CS8
    attrs[3] = 0
    attrs[4] = termios.B115200
    attrs[5] = termios.B115200
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 1
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    return saved


def restore_serial(fd: int, saved: list) -> None:
    try:
        termios.tcsetattr(fd, termios.TCSANOW, saved)
    except (OSError, termios.error):
        pass


def probe_port(port: str) -> tuple[str | None, str]:
    """Return (board kind, evidence) for one port."""
    try:
        fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError as exc:
        return None, f"cannot open: {exc}"

    saved: list | None = None
    try:
        saved = configure_serial(fd)
        initial = read_for(fd, 0.15)

        write_all(fd, PROBE)
        response = initial + read_for(fd, 0.45)
        # The log fallback keeps already-flashed workbenches selectable while
        # they are being upgraded to the explicit probe protocol.
        if WORKBENCH_REPLY in response or b"Ventilastation workbench" in response or b"led_capture:" in response:
            return "workbench", "workbench probe reply"

        # Ventilastation exposes a normal MicroPython REPL over USB-JTAG.
        # Interrupt the current program, ask for the explicit frozen board ID,
        # and soft-reboot after a successful match so detection is non-sticky.
        write_all(fd, b"\x03")
        read_for(fd, 0.15)
        write_all(fd, b'from vsdk_board import BOARD_ID; print("VSDK_BOARD_ID=" + BOARD_ID)\r\n')
        repl_response = read_for(fd, 0.75)
        # The package fallback keeps an existing rotor selectable before its
        # next MicroPython build includes board_id. It still requires the
        # Ventilastation package, rather than treating every MicroPython REPL
        # as a rotor board.
        if ROTOR_REPLY not in repl_response and b"ImportError" in repl_response:
            write_all(fd, b'import ventilastation.hw_config; print("VSDK_BOARD_ID=ventilastation")\r\n')
            repl_response += read_for(fd, 0.75)
        if ROTOR_REPLY in repl_response or (
            b"Ventilastation with ESP32S3" in repl_response and b">>>" in repl_response
        ):
            write_all(fd, b"\x04")
            # Let the soft reboot finish before releasing the port. On this
            # firmware the USB REPL becomes available after the application
            # starts, not immediately after the ROM boot text; waiting here
            # avoids making the next invocation race USB-REPL enumeration.
            read_for(fd, 2.5)
            return "ventilastation", "MicroPython board ID"
        return None, "no recognized board response"
    except (OSError, termios.error) as exc:
        return None, f"probe failed: {exc}"
    finally:
        if saved is not None:
            restore_serial(fd, saved)
        os.close(fd)


def inspect_ports() -> list[Board]:
    macs = macos_port_macs()
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
        kind, detail = probe_port(port)
        boards.append(Board(port=port, kind=kind, mac=macs.get(port) or linux_port_mac(port), detail=detail))
    return boards


def format_board(board: Board) -> str:
    kind = board.kind or "unknown"
    mac = f"  MAC={board.mac}" if board.mac else ""
    return f"{kind:16} {board.port}{mac}"


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
        print(f"no unique {requested} board found; run 'make list-boards'", file=sys.stderr)
    raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", choices=("ventilastation", "workbench"), help="board type to select")
    parser.add_argument("--mac", help="USB-JTAG serial/MAC to select")
    parser.add_argument("--list", action="store_true", help="list and classify all candidate ports")
    args = parser.parse_args()

    boards = inspect_ports()
    if args.list:
        if boards:
            for board in boards:
                print(format_board(board))
        else:
            print("no USB serial boards found")
        return 0
    if not args.board:
        parser.error("one of --board or --list is required")

    print(choose(boards, args.board, args.mac).port)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
