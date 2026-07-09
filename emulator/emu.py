"""Desktop emulator entry point.

Modes (see also config.py):
  (default)      run the local desktop MicroPython as the frame source and render it
  --remote       connect to the hardware workbench and render the POV frames it
                 captures from the real board; no local MicroPython
  --no-display   connect to a real board for button input only; render nothing
                 (the physical spinning LEDs are the display)
"""

import argparse
import platform
import subprocess

UPY_ROOT = "../apps/micropython"
UPY_EXEC = "micropython.exe" if platform.system() == "Windows" else "micropython"
LED_COUNT = 54


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("host", nargs="?", default=None,
                        help="board IP/hostname when talking to hardware, or SERIAL "
                             "for the legacy serial-only transport (default: local simulation)")
    parser.add_argument("--remote", action="store_true",
                        help="render frames streamed from a real board; no local MicroPython")
    parser.add_argument("--no-display", action="store_true",
                        help="input/audio host only; the spinning LEDs are the display")
    parser.add_argument("--serial-port", default=None,
                        help="workbench USB bridge serial port (default: autodetect)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    import config
    config.configure(args)

    # Imported after configure(): these modules read config at import time
    # to build windows/connections matching the selected mode.
    import comms
    from pygletengine import PygletEngine

    comms.start()

    # Spawn the local desktop MicroPython only when it is our frame source.
    spawn_upy = not (args.no_display or args.remote)
    upy = None
    try:
        if spawn_upy:
            upy = subprocess.Popen(
                [UPY_EXEC, "-X", "heapsize=8m", "main.py", "--platform=desktop"],
                cwd=UPY_ROOT,
            )
        PygletEngine(LED_COUNT, comms.send, config.DISPLAY_ENABLED)
    finally:
        comms.shutdown()
        if upy is not None:
            upy.kill()


if __name__ == "__main__":
    main()
