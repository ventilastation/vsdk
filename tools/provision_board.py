#!/usr/bin/env python3
"""Write the Ventilastation main-board wiring configuration to NVS.

NVS survives firmware and filesystem reflashes, and is shared by MicroPython
and the native Retro-Go apps. Use through ``make configure-board`` unless a
different board revision needs explicit values.

Goes through nvs_partition.py (dump the partition, patch these keys, write
it back over esptool) rather than running code on the board via mpremote --
so this works even if MicroPython isn't currently booted, and never
disturbs other NVS namespaces (e.g. vsdk_ota's stored OTA hashes).
"""

import argparse
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nvs_partition

NVS_NAMESPACE = "vs_board"
NVS_KEYS = (
    "hall_gpio",
    "irdiode_gpio",
    "led_spi_host",
    "led_clk",
    "led_mosi",
    "led_cs",
    "led_freq",
    "serial_uart",
    "serial_tx",
    "serial_rx",
    "serial_baud",
)

# Must match the "nvs" row in hardware/rotor/partitions-ventilastation.csv.
NVS_OFFSET = 0x9000
NVS_SIZE = 0x4000


def main():
    parser = argparse.ArgumentParser(description="Write main-board wiring to NVS")
    parser.add_argument("--port", "-p", required=True, help="Serial port, e.g. /dev/cu.usbmodemXXXX")
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument(
        "--idf-path",
        type=pathlib.Path,
        default=os.environ.get("IDF_PATH"),
        help="Defaults to $IDF_PATH -- source esp-idf's export.sh first",
    )
    for key in NVS_KEYS:
        parser.add_argument("--" + key.replace("_", "-"), type=int, required=True)
    args = parser.parse_args()

    if not args.idf_path:
        sys.exit("IDF_PATH is not set -- source esp-idf's export.sh first (see docs/internals/building.md)")

    updates = {(NVS_NAMESPACE, key): getattr(args, key) for key in NVS_KEYS}
    nvs_partition.provision(
        args.idf_path.resolve(), args.port, NVS_OFFSET, NVS_SIZE, updates, baud=args.baud,
    )
    print(f"Main-board configuration saved to NVS {NVS_NAMESPACE!r}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(error, file=sys.stderr)
        sys.exit(1)
