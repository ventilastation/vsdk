#!/usr/bin/env python3
"""Passive read-only monitor of the rotor's own native USB-CDC port.

That port is flashing/REPL only on this board -- the running MicroPython
app's stdout/print output does not appear here (it's redirected to the
dedicated base-station UART; see serialcomms.py and
led_usage_serial_check.py, which reaches that traffic via the workbench
board instead). This is still useful for watching the plain boot log, or
confirming that assumption after a firmware change.

Usage:
    python3 tools/rotor_console_monitor.py [port] [seconds]

Find the right port with `python3 tools/find_board.py --list`.
"""
import sys
import time

import serial


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbmodem14314101"
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0

    ser = serial.Serial(port, baudrate=115200, timeout=0.2)
    print("--- monitoring %s for %.0fs ---" % (port, duration), flush=True)
    end = time.time() + duration
    while time.time() < end:
        chunk = ser.read(4096)
        if chunk:
            sys.stdout.buffer.write(chunk)
            sys.stdout.flush()
    ser.close()
    print("\n--- monitor done ---")


if __name__ == "__main__":
    main()
