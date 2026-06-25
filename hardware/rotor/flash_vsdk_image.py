#!/usr/bin/env python3

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


def flash_images(args, bootloader_path, partition_table_path, micropython_path):
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
        default=vsdk_root / "hardware/rotor/partitions-voom.csv",
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
    partition_table_path = args.output_dir / "partition-table-voom.bin"

    ensure_file(bootloader_path, "MicroPython bootloader")
    ensure_file(micropython_path, "MicroPython application")
    ensure_file(args.partition_csv, "Partition CSV")

    generate_partition_table(args.idf_path, args.partition_csv, partition_table_path)
    flash_images(args, bootloader_path, partition_table_path, micropython_path)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
