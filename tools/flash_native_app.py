#!/usr/bin/env python3
"""Flash one already-built retro-go native app to its own OTA partition.

Each native app (prboom-go, retro-core, fmsx) has a dedicated partition in
hardware/rotor/partitions-ventilastation.csv. This writes just that app's
built .bin at its partition offset, leaving the bootloader, partition table,
MicroPython, other native apps, and the VFS untouched -- much faster and
lower-risk than hardware/rotor/flash_voom_image.py's full combined-image
reflash at offset 0x0, when only one native app changed.

Build the app first with retro-go's own tool, e.g.:
    cd apps/retro-go && python3 rg_tool.py --target=ventilastation build prboom-go
"""

import argparse
import csv
import pathlib
import subprocess
import sys

VSDK_ROOT = pathlib.Path(__file__).resolve().parents[1]
PARTITION_CSV = VSDK_ROOT / "hardware/rotor/partitions-ventilastation.csv"


def read_partition_offset(app_name):
    with PARTITION_CSV.open(newline="") as handle:
        for row in csv.reader(handle):
            if not row or row[0].strip().startswith("#"):
                continue
            if row[0].strip() == app_name:
                return int(row[3].strip(), 0), int(row[4].strip(), 0)
    raise KeyError(f"{app_name!r} not found in {PARTITION_CSV}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", help="partition/app name, e.g. prboom-go, retro-core, fmsx")
    parser.add_argument("--port", required=True, help="serial port, e.g. /dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument(
        "--image",
        type=pathlib.Path,
        help="path to the built .bin (default: apps/retro-go/<app>/build/<app>.bin)",
    )
    args = parser.parse_args()

    image = args.image or (VSDK_ROOT / "apps/retro-go" / args.app / "build" / f"{args.app}.bin")
    if not image.exists():
        sys.exit(f"error: {image} not found -- build {args.app} first (see module docstring)")

    offset, size = read_partition_offset(args.app)
    image_size = image.stat().st_size
    if image_size > size:
        sys.exit(f"error: {image} is {image_size} bytes, larger than the "
                  f"{args.app} partition ({size} bytes)")

    print(f"Flashing {image} ({image_size} bytes) to {args.app} partition "
          f"at {hex(offset)} (size {hex(size)})")
    command = [
        sys.executable, "-m", "esptool",
        "--chip", "esp32s3",
        "-p", args.port,
        "-b", str(args.baud),
        "--before", "default_reset",
        "--after", "hard_reset",
        "write_flash",
        "--flash_size", "16MB",
        hex(offset), str(image),
    ]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
    except (KeyError, OSError) as exc:
        sys.exit(str(exc))
