#!/usr/bin/env python3
"""
Provision Wi-Fi credentials into the workbench's NVS partition, without
rebuilding or reflashing firmware — the same idea as vsdk/tools/provision_wifi.py
for the DUT, just implemented for a compiled ESP-IDF app instead of a live
MicroPython REPL: there's no `mpremote run` to poke NVS live, so this
generates a small NVS partition image (namespace "devel_wifi", the same
namespace/keys the DUT itself reads) and flashes it directly to the "nvs"
partition's offset from partitions.csv.

Requires an ESP-IDF environment to be sourced first (uses
$IDF_PATH/components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py
and the `esptool` module installed alongside idf.py).

Usage:
  source /path/to/esp-idf/esp-5.5.2/export.sh
  python tools/provision_wifi.py --port /dev/cu.usbmodemXXXX \
      --wifi-ssid mywifi --wifi-password mypassword

After it completes, reset the workbench — it logs its IP (and mDNS name)
over its USB port.
"""

import argparse
import os
import pathlib
import subprocess
import sys
import tempfile

# Must match the "nvs" row in ../partitions.csv.
NVS_OFFSET = "0x9000"
NVS_SIZE = 0x6000


def run(cmd, **kwargs):
    print("$", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kwargs)


def main():
    idf_path = os.environ.get("IDF_PATH")
    if not idf_path:
        sys.exit("IDF_PATH is not set — source esp-idf's export.sh first (see docs/internals/workbench.md)")

    gen_script = pathlib.Path(idf_path) / "components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py"
    if not gen_script.exists():
        sys.exit(f"nvs_partition_gen.py not found at {gen_script} — check IDF_PATH")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", "-p", required=True, help="Workbench serial port (e.g. /dev/cu.usbmodemXXXX)")
    parser.add_argument("--wifi-ssid", "-s", required=True, help="Wi-Fi network name")
    parser.add_argument("--wifi-password", "-w", required=True, help="Wi-Fi password")
    parser.add_argument("--baud", default="460800", help="Flashing baud rate")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        csv_path = tmp / "wifi_nvs.csv"
        bin_path = tmp / "wifi_nvs.bin"

        # "binary" encoding produces a real NVS_TYPE_BLOB entry, matching
        # what MicroPython's esp32.NVS.set_blob() writes on the DUT side —
        # both are read back with nvs_get_blob().
        csv_path.write_text(
            "key,type,encoding,value\n"
            "devel_wifi,namespace,,\n"
            f"ssid,data,binary,{args.wifi_ssid}\n"
            f"password,data,binary,{args.wifi_password}\n"
        )

        print("\n=== Generating NVS partition image ===")
        run([sys.executable, str(gen_script), "generate", str(csv_path), str(bin_path), hex(NVS_SIZE)])

        print("\n=== Flashing NVS partition ===")
        run(
            [
                sys.executable,
                "-m",
                "esptool",
                "--chip",
                "esp32s3",
                "--port",
                args.port,
                "--baud",
                args.baud,
                "write_flash",
                NVS_OFFSET,
                str(bin_path),
            ]
        )

    print("\n=== Done! Reset the workbench to apply. ===")
    print("It will log its IP address (and mDNS name) over its USB port.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        sys.exit(1)
