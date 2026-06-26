#!/usr/bin/env python3
"""
Set up an ESP32-S3 board for the WiFi dev loop.

Uploads to the board:
  - vsdk_platform.txt  (tells firmware to use the desktop/WiFi platform)
  - wifi_config.json   (WiFi credentials)
  - All Python app files from apps/micropython/ (so edits don't need a reflash)

After running this, reset the board. It will print its IP over USB serial.
Then start the desktop emulator with:
  cd emulator && python emu.py <board_ip> --remote
"""

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile


def run(cmd, **kwargs):
    print("$", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kwargs)


def mpremote(*args, port=None):
    cmd = ["mpremote"]
    if port:
        cmd += ["connect", port]
    cmd += list(args)
    run(cmd)


def mpremote_mkdir(path, port=None):
    try:
        mpremote("fs", "mkdir", path, port=port)
    except subprocess.CalledProcessError:
        pass  # directory already exists


def main():
    script_path = pathlib.Path(__file__).resolve()
    vsdk_root = script_path.parent.parent
    upy_root = vsdk_root / "apps/micropython"

    parser = argparse.ArgumentParser(description="Deploy dev-mode config to ESP32 board")
    parser.add_argument("--port", "-p", help="Serial port (e.g. /dev/ttyACM0). Auto-detected if omitted.")
    parser.add_argument("--wifi-ssid", "-s", required=True, help="WiFi network name")
    parser.add_argument("--wifi-password", "-w", required=True, help="WiFi password")
    parser.add_argument(
        "--skip-files",
        action="store_true",
        help="Skip uploading Python app files (only upload config files)",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)

        # vsdk_platform.txt — tells resolve_platform_name() to use 'desktop' (WiFi+TCP)
        platform_file = tmp / "vsdk_platform.txt"
        platform_file.write_text("desktop\n")

        # wifi_config.json — fallback for desktop/emulator mode (no esp32 NVS module)
        wifi_file = tmp / "wifi_config.json"
        wifi_file.write_text(json.dumps({"ssid": args.wifi_ssid, "password": args.wifi_password}))

        # setup_wifi_nvs.py — writes credentials to NVS namespace "voom_wifi" so both
        # MicroPython (comms.py) and prboom-go (wb_init) read from the same place.
        wifi_script = tmp / "setup_wifi_nvs.py"
        wifi_script.write_text(
            "import esp32\n"
            "nvs = esp32.NVS('voom_wifi')\n"
            f"nvs.set_blob('ssid', {args.wifi_ssid.encode()!r})\n"
            f"nvs.set_blob('password', {args.wifi_password.encode()!r})\n"
            "nvs.commit()\n"
            "print('WiFi credentials saved to NVS voom_wifi')\n"
        )

        print("\n=== Uploading config files ===")
        mpremote("cp", str(platform_file), ":vsdk_platform.txt", port=args.port)
        mpremote("cp", str(wifi_file), ":wifi_config.json", port=args.port)
        print("\n=== Writing WiFi credentials to NVS ===")
        mpremote("run", str(wifi_script), port=args.port)

    if not args.skip_files:
        print("\n=== Uploading Python app files ===")
        for src in sorted(upy_root.rglob("*.py")):
            rel = src.relative_to(upy_root)
            dst = ":" + str(rel)
            # Ensure parent directory exists on board
            parent = rel.parent
            if str(parent) != ".":
                mpremote_mkdir(":" + str(parent), port=args.port)
            mpremote("cp", str(src), dst, port=args.port)

    print("\n=== Done! Reset the board to apply. ===")
    print("The board will print its IP address over USB serial.")
    print("Then connect the emulator:")
    board_ip = "<board_ip>"
    print(f"  cd emulator && python emu.py {board_ip} --remote")
    print("\nFor console monitoring in a separate terminal:")
    port_arg = args.port or "<port>"
    print(f"  mpremote connect {port_arg}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        sys.exit(1)
