#!/usr/bin/env python3
"""Flash only the `factory` partition + NVS -- the streamlined bring-up
procedure for a fresh Ventilastation main board (see docs/internals/ota.md).

Unlike flash_vsdk_image.py / `make initial-flash` (which also writes the
ota_2 `micropython` slot and an empty vfs -- now a bench-dev convenience, not
the bring-up procedure), this writes bootloader + partition table +
micropython.bin to `factory` alone. `factory`
is the permanent recovery environment (see apps/micropython/main.py): on a
fresh board there's no vfs `main.py` yet, so it runs vsdk_recovery.py, which
fetches everything else -- vfs, native apps, and the real ota_2 micropython
copy -- over WiFi via the updater. USB flashing never touches those
partitions.

After flashing, provisions NVS if missing (`vs_board` wiring + `devel_wifi`
credentials) via the existing tools/provision_board.py / tools/provision_wifi.py,
read-first so re-running this during bench iteration doesn't clobber an
already-provisioned board. Pass --force to overwrite regardless, or
--skip-nvs to flash factory only.

NVS is read and written entirely over esptool + tools/nvs_partition.py (dump
the partition, decode/patch/re-encode, write it back) -- no dependency on
mpremote running code on a booted MicroPython, so this works even on a board
that isn't running yet. Only the final reset still goes over mpremote.
"""

import argparse
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
import nvs_partition

# Must match the "nvs" row in partitions-ventilastation.csv.
NVS_OFFSET = 0x9000
NVS_SIZE = 0x4000


def run_mpremote(argv):
    print("$", " ".join(argv))
    result = subprocess.run(argv, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        raise subprocess.CalledProcessError(result.returncode, argv, result.stdout, result.stderr)
    return result


def run(cmd, cwd=None):
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def find_parent_root(script_path):
    vsdk_root = script_path.parents[2]
    ventilastation_root = vsdk_root.parents[1]
    return vsdk_root, ventilastation_root


def ensure_file(path, description):
    if not path.exists():
        raise FileNotFoundError(f"{description} not found: {path}")


def generate_partition_table(idf_path, partition_csv, output_path):
    command = [
        "python3",
        str(idf_path / "components/partition_table/gen_esp32part.py"),
        str(partition_csv),
        str(output_path),
    ]
    run(command)


def flash_factory_only(args, bootloader_path, partition_table_path, micropython_path):
    # Only bootloader + partition table + factory (0x10000). No ota_2 write:
    # that partition is installed/updated over WiFi by the updater, never USB.
    command = [
        "python3",
        "-m",
        "esptool",
        "--chip",
        "esp32s3",
        "-p",
        args.port,
        "-b",
        str(args.baud),
        "--before",
        "default_reset",
        "--after",
        "hard_reset",
        "write_flash",
        "--flash_mode",
        "dio",
        "--flash_freq",
        "80m",
        "--flash_size",
        "16MB",
        "0x0",
        str(bootloader_path),
        "0x8000",
        str(partition_table_path),
        "0x10000",
        str(micropython_path),
    ]
    run(command, cwd=micropython_path.parent)


_BOARD_KEYS = (
    "hall_gpio", "irdiode_gpio", "led_spi_host", "led_clk", "led_mosi",
    "led_cs", "led_freq", "serial_uart", "serial_tx", "serial_rx", "serial_baud",
)


def _check_provisioned(idf_path, port, baud):
    """Dump + decode NVS over esptool; returns (board_ok, wifi_ok)."""
    entries = nvs_partition.read_values(idf_path, port, NVS_OFFSET, NVS_SIZE, baud=baud)
    board_ok = all(("vs_board", key) in entries for key in _BOARD_KEYS)
    wifi_ok = all(("devel_wifi", key) in entries for key in ("ssid", "password"))
    return board_ok, wifi_ok


def _provision_board(vsdk_root, args):
    run([
        "python3", str(vsdk_root / "tools" / "provision_board.py"),
        "--port", args.port,
        "--baud", str(args.baud),
        "--hall-gpio", str(args.hall_gpio),
        "--irdiode-gpio", str(args.irdiode_gpio),
        "--led-spi-host", str(args.led_spi_host),
        "--led-clk", str(args.led_clk),
        "--led-mosi", str(args.led_mosi),
        "--led-cs", str(args.led_cs),
        "--led-freq", str(args.led_freq),
        "--serial-uart", str(args.serial_uart),
        "--serial-tx", str(args.serial_tx),
        "--serial-rx", str(args.serial_rx),
        "--serial-baud", str(args.serial_baud),
    ])


def _provision_wifi(vsdk_root, args):
    if not args.wifi_ssid:
        print(
            "flash_recovery_image: no --wifi-ssid given, skipping WiFi provisioning "
            "(run 'make wifi-provision WIFI_SSID=... WIFI_PASS=...' separately)"
        )
        return
    run([
        "python3", str(vsdk_root / "tools" / "provision_wifi.py"),
        "--port", args.port,
        "--baud", str(args.baud),
        "--wifi-ssid", args.wifi_ssid,
        "--wifi-password", args.wifi_password,
    ])


def _reset_board(port):
    with tempfile.TemporaryDirectory() as tmp:
        script_path = pathlib.Path(tmp) / "reset.py"
        script_path.write_text("import machine\nmachine.reset()\n")
        try:
            run_mpremote(["mpremote", "connect", port, "run", str(script_path)])
        except subprocess.CalledProcessError as e:
            # Not fatal: the board is provisioned either way, just sitting at
            # the REPL instead of running. A power cycle also gets it going.
            print(f"flash_recovery_image: final reset failed ({e}); power-cycle the board to start it")


def main():
    script_path = pathlib.Path(__file__).resolve()
    vsdk_root, _ = find_parent_root(script_path)
    default_build_dir = vsdk_root / "hardware/rotor/build"

    parser = argparse.ArgumentParser(description="Flash factory + NVS only (streamlined bring-up)")
    parser.add_argument("--port", required=True, help="Serial port, for example /dev/cu.usbmodemXXXX")
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument(
        "--idf-path",
        type=pathlib.Path,
        default=os.environ.get("IDF_PATH"),
        help="Defaults to $IDF_PATH -- source esp-idf's export.sh first",
    )
    parser.add_argument(
        "--partition-csv",
        type=pathlib.Path,
        default=vsdk_root / "hardware/rotor/partitions-ventilastation.csv",
    )
    parser.add_argument("--board", default="VENTILASTATION")
    parser.add_argument("--board-variant", default="SPIRAM_OCT")
    parser.add_argument(
        "--micropython-root",
        type=pathlib.Path,
        default=vsdk_root / "hardware/rotor/micropython",
    )
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=default_build_dir,
    )
    parser.add_argument("--force", action="store_true", help="Overwrite NVS even if already provisioned")
    parser.add_argument("--skip-nvs", action="store_true", help="Flash factory only, skip NVS entirely")

    # vs_board defaults match `make configure-board`'s Ventilastation III values.
    parser.add_argument("--hall-gpio", type=int, default=7)
    parser.add_argument("--irdiode-gpio", type=int, default=7)
    parser.add_argument("--led-spi-host", type=int, default=2)
    parser.add_argument("--led-clk", type=int, default=12)
    parser.add_argument("--led-mosi", type=int, default=13)
    parser.add_argument("--led-cs", type=int, default=14)
    parser.add_argument("--led-freq", type=int, default=20000000)
    parser.add_argument("--serial-uart", type=int, default=2)
    parser.add_argument("--serial-tx", type=int, default=5)
    parser.add_argument("--serial-rx", type=int, default=6)
    parser.add_argument("--serial-baud", type=int, default=115200)

    parser.add_argument("--wifi-ssid", default="", help="Also provision devel_wifi if missing")
    parser.add_argument("--wifi-password", default="")

    args = parser.parse_args()

    if not args.idf_path:
        sys.exit("IDF_PATH is not set -- source esp-idf's export.sh first (see docs/internals/building.md)")

    args.idf_path = args.idf_path.resolve()
    args.partition_csv = args.partition_csv.resolve()
    args.micropython_root = args.micropython_root.resolve()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    micropython_build_dir = (
        args.micropython_root / "ports/esp32" / f"build-{args.board}-{args.board_variant}"
    )
    bootloader_path = micropython_build_dir / "bootloader/bootloader.bin"
    micropython_path = micropython_build_dir / "micropython.bin"
    partition_table_path = args.output_dir / "partition-table-ventilastation.bin"

    ensure_file(bootloader_path, "MicroPython bootloader")
    ensure_file(micropython_path, "MicroPython application")
    ensure_file(args.partition_csv, "Partition CSV")

    generate_partition_table(args.idf_path, args.partition_csv, partition_table_path)
    flash_factory_only(args, bootloader_path, partition_table_path, micropython_path)

    if args.skip_nvs:
        return

    board_ok, wifi_ok = _check_provisioned(args.idf_path, args.port, args.baud)

    if args.force or not board_ok:
        print("flash_recovery_image: provisioning vs_board NVS...")
        _provision_board(vsdk_root, args)
    else:
        print("flash_recovery_image: vs_board NVS already provisioned, skipping (use --force to overwrite)")

    if args.force or not wifi_ok:
        _provision_wifi(vsdk_root, args)
    else:
        print("flash_recovery_image: devel_wifi NVS already provisioned, skipping (use --force to overwrite)")

    _reset_board(args.port)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
