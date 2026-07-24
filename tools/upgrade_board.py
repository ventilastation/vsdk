#!/usr/bin/env python3
"""Upgrade a connected rotor board's MicroPython filesystem and Voom binary.

Two independent, surgical updates -- neither touches the bootloader,
partition table, MicroPython firmware itself, or the other native apps:

  1. Rebuild and reflash the VFS (LittleFS) partition holding every
     MicroPython .py/.json/.rom file, via the existing
     hardware/rotor/deploy_micropython_fs.py.
  2. Reflash the prboom-go (Voom) native app to its own OTA partition, via
     tools/flash_native_app.py. Build it first (see --build-voom) or pass
     an already-built .bin.

Requires an ESP-IDF Python environment with esptool on PATH (source
esp-idf's export.sh first -- see docs/internals/building.md) and, for
--build-voom, IDF_PATH set the same way.

    python3 tools/upgrade_board.py --port /dev/ttyACM0
"""

import argparse
import pathlib
import subprocess
import sys

VSDK_ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(cmd, cwd=None):
    print("$", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", required=True, help="rotor board's native USB serial port")
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument("--skip-vfs", action="store_true", help="don't rebuild/reflash the MicroPython VFS")
    parser.add_argument("--skip-voom", action="store_true", help="don't reflash prboom-go")
    parser.add_argument(
        "--build-voom", action="store_true",
        help="build prboom-go before flashing it (needs ESP-IDF's IDF_PATH active)",
    )
    args = parser.parse_args()

    if not args.skip_vfs:
        run([
            sys.executable, str(VSDK_ROOT / "hardware/rotor/deploy_micropython_fs.py"),
            "--port", args.port, "--baud", str(args.baud),
        ])

    if not args.skip_voom:
        if args.build_voom:
            run(
                [sys.executable, "rg_tool.py", "--target=ventilastation", "build", "prboom-go"],
                cwd=VSDK_ROOT / "apps/retro-go",
            )
        run([
            sys.executable, str(VSDK_ROOT / "tools/flash_native_app.py"), "prboom-go",
            "--port", args.port, "--baud", str(args.baud),
        ])

    print("Upgrade complete.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)


