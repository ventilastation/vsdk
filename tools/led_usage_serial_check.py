#!/usr/bin/env python3
"""Bench check for the "LED Usage" diagnostic app (system/led_usage),
driven live against a real board -- no pyglet window needed.

Talks to the rotor's director-level text-command protocol (what
"launch"/"ledusage ..." ride on) over the *workbench* board's own
USB-serial connection, which transparently bridges the rotor's dedicated
base-station UART (see docs/internals/workbench.md) -- not the rotor's own
USB-CDC port, which is flashing/REPL only and carries none of this traffic.

Usage (from the repo root, with the workbench and rotor both on USB):
    python3 tools/led_usage_serial_check.py
    python3 tools/led_usage_serial_check.py --workbench-port /dev/cu.usbmodem14201

Find the right port with `python3 tools/find_board.py --list`.
"""
import argparse
import pathlib
import sys
import time

EMULATOR_DIR = pathlib.Path(__file__).resolve().parent.parent / "emulator"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workbench-port", default=None,
                        help="workbench board's serial port (default: autodetect, see find_board.py)")
    parser.add_argument("--settle", type=float, default=2.0,
                        help="seconds to wait after each command before checking state")
    return parser.parse_args()


def main():
    args = parse_args()
    sys.path.insert(0, str(EMULATOR_DIR))

    import config
    config.SERIAL_PORT = args.workbench_port
    config.USE_IP = True
    config.HARDWARE_MODE = True
    config.DISPLAY_ENABLED = False

    # Match emu.py's own guard for DISPLAY_ENABLED=False: comms.py pulls in
    # pyglet.media (for audio), which otherwise creates an invisible shadow
    # window as an import side effect -- and a shell session's display
    # isn't always reliably available for that.
    import pyglet
    pyglet.options['shadow_window'] = False

    import comms

    def show_state(label):
        print("%s -> %s" % (label, comms.led_usage_state.status_text()))

    comms.start()
    try:
        print("--- waiting for the workbench serial link ---")
        time.sleep(3)

        print("--- launching led_usage (system app slug) ---")
        comms.send_command("launch led_usage")
        time.sleep(args.settle)
        comms.send_led_usage("get")
        time.sleep(1)
        show_state("after launch")

        print("--- count=40 red=255 green=0 blue=0 global=16 ---")
        comms.send_led_usage("set 40 255 0 0 16")
        time.sleep(args.settle)
        show_state("count=40 r=255")

        print("--- count=107 (every LED) red=0 green=255 blue=0 global=31 ---")
        comms.send_led_usage("set 107 0 255 0 31")
        time.sleep(args.settle)
        show_state("count=107 g=255")

        print("--- count=0 (all off) ---")
        comms.send_led_usage("set 0 0 0 0 0")
        time.sleep(args.settle)
        show_state("count=0")

        print("--- exit back to the menu ---")
        comms.send_command("exit")
        time.sleep(args.settle)
    finally:
        comms.shutdown()
        print("--- done ---")


if __name__ == "__main__":
    main()
