#!/usr/bin/env python3
"""Write WiFi credentials to the main board's NVS (namespace "devel_wifi").

The board only brings WiFi up when an OTA upgrade is requested over the
serial host link (see apps/micropython/updater.py); these credentials tell
it which network to join for that. NVS survives firmware and filesystem
reflashes, so this only needs to run once per board.

Goes through nvs_partition.py (dump the partition, patch these keys, write
it back over esptool) rather than running code on the board via mpremote --
so this works even if MicroPython isn't currently booted, and never
disturbs other NVS namespaces (e.g. vs_board wiring or vsdk_ota's stored
OTA hashes).

Usage (or `make wifi-provision PORT=... WIFI_SSID=... WIFI_PASS=...`):
  python3 tools/provision_wifi.py --port /dev/cu.usbmodemXXXX \
      --wifi-ssid mynetwork --wifi-password secret
"""

import argparse
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nvs_partition

NVS_NAMESPACE = "devel_wifi"

# Must match the "nvs" row in hardware/rotor/partitions-ventilastation.csv.
NVS_OFFSET = 0x9000
NVS_SIZE = 0x4000


def main():
    parser = argparse.ArgumentParser(description="Write WiFi credentials to the board's NVS")
    parser.add_argument("--port", "-p", required=True, help="Serial port, e.g. /dev/cu.usbmodemXXXX")
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument(
        "--idf-path",
        type=pathlib.Path,
        default=os.environ.get("IDF_PATH"),
        help="Defaults to $IDF_PATH -- source esp-idf's export.sh first",
    )
    parser.add_argument("--wifi-ssid", "-s", required=True, help="WiFi network name")
    parser.add_argument("--wifi-password", "-w", required=True, help="WiFi password")
    args = parser.parse_args()

    if not args.idf_path:
        sys.exit("IDF_PATH is not set -- source esp-idf's export.sh first (see docs/internals/building.md)")

    updates = {
        (NVS_NAMESPACE, "ssid"): args.wifi_ssid,
        (NVS_NAMESPACE, "password"): args.wifi_password,
    }
    nvs_partition.provision(
        args.idf_path.resolve(), args.port, NVS_OFFSET, NVS_SIZE, updates, baud=args.baud,
    )
    print(f"WiFi credentials saved to NVS {NVS_NAMESPACE!r}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
