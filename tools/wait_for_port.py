#!/usr/bin/env python3
"""Wait until a serial port exists and can be opened.

The board's USB-CDC console re-enumerates after every flash/reset, so a
flashing step that runs right after another one can find the port node
missing or half-dead ("Device not configured"). Poll until a plain open
succeeds twice around a settle delay, so chained Makefile flash targets
don't race the re-enumeration.
"""

import argparse
import os
import sys
import time


def try_open(port):
    try:
        fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError:
        return False
    os.close(fd)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--settle", type=float, default=2.0,
        help="seconds to wait after the port first opens; it must still be "
        "openable afterwards (the node can flap during re-enumeration)",
    )
    args = parser.parse_args()

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        if try_open(args.port):
            time.sleep(args.settle)
            if try_open(args.port):
                return 0
        else:
            time.sleep(0.5)
    print(f"timed out waiting for {args.port}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
