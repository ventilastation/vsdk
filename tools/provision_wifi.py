#!/usr/bin/env python3
"""Write WiFi credentials to the main board's NVS (namespace "devel_wifi").

The board only brings WiFi up when an OTA upgrade is requested over the
serial host link (see apps/micropython/updater.py); these credentials tell
it which network to join for that. NVS survives firmware and filesystem
reflashes, so this only needs to run once per board.

Usage (or `make wifi-provision PORT=... WIFI_SSID=... WIFI_PASS=...`):
  python3 tools/provision_wifi.py --port /dev/cu.usbmodemXXXX \
      --wifi-ssid mynetwork --wifi-password secret
"""

import argparse
import pathlib
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description="Write WiFi credentials to the board's NVS")
    parser.add_argument("--port", "-p", help="Serial port (auto-detected by mpremote if omitted)")
    parser.add_argument("--wifi-ssid", "-s", required=True, help="WiFi network name")
    parser.add_argument("--wifi-password", "-w", required=True, help="WiFi password")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        script = pathlib.Path(tmp) / "setup_wifi_nvs.py"
        script.write_text(
            "import esp32\n"
            "nvs = esp32.NVS('devel_wifi')\n"
            f"nvs.set_blob('ssid', {args.wifi_ssid.encode()!r})\n"
            f"nvs.set_blob('password', {args.wifi_password.encode()!r})\n"
            "nvs.commit()\n"
            "print('WiFi credentials saved to NVS devel_wifi')\n"
        )
        cmd = ["mpremote"]
        if args.port:
            cmd += ["connect", args.port]
        cmd += ["run", str(script)]
        print("$", " ".join(cmd))
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        sys.exit(1)
