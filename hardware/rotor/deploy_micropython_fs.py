#!/usr/bin/env python3
"""Build a LittleFS2 image and flash it to the VFS partition."""

import argparse
import pathlib
import subprocess
import sys


def shell_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def run(cmd, cwd=None):
    print("$", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def run_in_idf_env(idf_path, command, cwd=None):
    cmd = [
        "/bin/zsh",
        "-lc",
        f"source {shell_quote(str(idf_path / 'export.sh'))} >/dev/null && {' '.join(shell_quote(part) for part in command)}",
    ]
    run(cmd, cwd=cwd)


def main():
    script_path = pathlib.Path(__file__).resolve()
    vsdk_root = script_path.parents[2]
    ventilastation_root = vsdk_root.parents[1]
    build_dir = vsdk_root / "hardware/rotor/build"
    vfs_bin = build_dir / "vfs.bin"
    build_fs_script = vsdk_root / "hardware/rotor/build_micropython_fs.py"

    parser = argparse.ArgumentParser(description="Build and flash the MicroPython filesystem image")
    parser.add_argument("--port", required=True, help="Serial port, e.g. /dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument(
        "--vfs-offset",
        type=lambda x: int(x, 0),
        default=0x4F0000,
        help="Flash offset of the VFS partition (default: 0x4F0000, matches partitions-voom.csv)",
    )
    parser.add_argument(
        "--partition-size",
        type=lambda x: int(x, 0),
        default=0xB10000,
        help="VFS partition size in bytes (default: 0xB10000, matches partitions-voom.csv)",
    )
    parser.add_argument(
        "--idf-path",
        type=pathlib.Path,
        default=ventilastation_root / "esp-idf/esp-5.5.2",
    )
    parser.add_argument("--skip-build", action="store_true", help="Flash existing vfs.bin without rebuilding")
    args = parser.parse_args()

    args.idf_path = args.idf_path.resolve()

    if not args.skip_build:
        run([
            "python3", str(build_fs_script),
            "--partition-size", hex(args.partition_size),
            "--output", str(vfs_bin),
        ])

    if not vfs_bin.exists():
        print(f"error: {vfs_bin} not found — run without --skip-build", file=sys.stderr)
        sys.exit(1)

    command = [
        "python3", "-m", "esptool",
        "--chip", "esp32s3",
        "-p", args.port,
        "-b", str(args.baud),
        "--before", "default_reset",
        "--after", "hard_reset",
        "write_flash",
        "--flash_mode", "dio",
        "--flash_freq", "80m",
        "--flash_size", "16MB",
        hex(args.vfs_offset),
        str(vfs_bin),
    ]
    run_in_idf_env(args.idf_path, command)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
