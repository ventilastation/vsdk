#!/usr/bin/env python3
"""Bench-dev bring-up: flash MicroPython to `factory` + `micropython` (ota_2)
and an empty, formatted LittleFS image to `vfs`, all over USB in one shot.

This is the `make initial-flash` target. It is NOT the bring-up procedure
for a new board -- use `make flash-recovery` for that (see
docs/internals/ota.md); this script exists for fast local iteration without
waiting on WiFi/OTA.
"""

import argparse
import pathlib
import subprocess
import sys


def shell_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def run(cmd, cwd=None):
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def run_in_idf_env(idf_path, command, cwd):
    cmd = [
        "/bin/zsh",
        "-lc",
        f"source {shell_quote(str(idf_path / 'export.sh'))} >/dev/null && {' '.join(shell_quote(part) for part in command)}",
    ]
    run(cmd, cwd=cwd)


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


# Offset/size of the `vfs` partition, matching partitions-ventilastation.csv.
VFS_OFFSET = "0x690000"
VFS_PARTITION_SIZE = 0x970000


def build_empty_vfs_image(build_fs_script, output_path):
    # A freshly formatted, file-less LittleFS image -- so a bench-flashed
    # board mounts a valid (if empty) filesystem immediately, without relying
    # on any device-side auto-format-on-first-boot fallback. Recovery/OTA
    # populates it with real content over WiFi from here.
    command = [
        "python3",
        str(build_fs_script),
        "--empty",
        "--partition-size", hex(VFS_PARTITION_SIZE),
        "--output", str(output_path),
    ]
    run(command)


def flash_images(args, bootloader_path, partition_table_path, micropython_path, vfs_image_path):
    # Always flash micropython to both the factory slot (0x10000) and the
    # updatable micropython slot (ota_2, 0x490000).  On first boot from
    # factory, main.py detects it's running on factory and runs recovery,
    # which hands off to ota_2 once it's ready.
    MICROPYTHON_OTA2_OFFSET = "0x490000"
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
        MICROPYTHON_OTA2_OFFSET,
        str(micropython_path),
        VFS_OFFSET,
        str(vfs_image_path),
    ]
    run_in_idf_env(args.idf_path, command, cwd=micropython_path.parent)


def main():
    script_path = pathlib.Path(__file__).resolve()
    vsdk_root, ventilastation_root = find_parent_root(script_path)
    default_build_dir = vsdk_root / "hardware/rotor/build"

    parser = argparse.ArgumentParser(description="Flash MicroPython with the Ventilastation partition table")
    parser.add_argument("--port", required=True, help="Serial port, for example /dev/cu.usbmodemXXXX")
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument(
        "--idf-path",
        type=pathlib.Path,
        default=ventilastation_root / "esp-idf/esp-5.5.2",
    )
    parser.add_argument(
        "--partition-csv",
        type=pathlib.Path,
        default=vsdk_root / "hardware/rotor/partitions-ventilastation.csv",
    )
    parser.add_argument(
        "--board",
        default="ESP32_GENERIC_S3",
    )
    parser.add_argument(
        "--board-variant",
        default="SPIRAM_OCT",
    )
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
    args = parser.parse_args()

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
    vfs_image_path = args.output_dir / "vfs-empty.bin"
    build_fs_script = vsdk_root / "hardware/rotor/build_micropython_fs.py"

    ensure_file(bootloader_path, "MicroPython bootloader")
    ensure_file(micropython_path, "MicroPython application")
    ensure_file(args.partition_csv, "Partition CSV")

    generate_partition_table(args.idf_path, args.partition_csv, partition_table_path)
    build_empty_vfs_image(build_fs_script, vfs_image_path)
    flash_images(args, bootloader_path, partition_table_path, micropython_path, vfs_image_path)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
