#!/usr/bin/env python3

import argparse
import csv
import pathlib
import subprocess
import sys


def run(cmd, cwd=None, env=None):
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def run_in_idf_env(idf_path, command, cwd):
    cmd = [
        "/bin/zsh",
        "-lc",
        f"source {shell_quote(str(idf_path / 'export.sh'))} >/dev/null && {' '.join(shell_quote(part) for part in command)}",
    ]
    run(cmd, cwd=cwd)


def shell_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def parse_partition_table(csv_path):
    partitions = {}
    with csv_path.open(newline="") as handle:
        for row in csv.reader(handle):
            if not row or row[0].startswith("#"):
                continue
            name = row[0].strip()
            partitions[name] = {
                "type": row[1].strip(),
                "subtype": row[2].strip(),
                "offset": int(row[3].strip(), 0),
                "size": int(row[4].strip(), 0),
            }
    return partitions


def find_parent_root(script_path):
    rotor_root = script_path.parent
    vsdk_root = script_path.parents[2]
    ventilastation_root = vsdk_root.parents[1]
    return rotor_root, vsdk_root, ventilastation_root


def ensure_file(path, description):
    if not path.exists():
        raise FileNotFoundError(f"{description} not found: {path}")


def build_micropython(args, vsdk_root):
    command = [
        "make",
        "V=1",
        f"BOARD={args.board}",
        f"BOARD_VARIANT={args.board_variant}",
        f"USER_C_MODULES={vsdk_root / 'hardware/rotor/modules/micropython.cmake'}",
        f"FROZEN_MANIFEST={vsdk_root / 'apps/micropython/manifest.py'}",
        "all",
    ]
    run_in_idf_env(args.micropython_idf_path, command, args.micropython_root / "ports/esp32")


def build_retro_go(args):
    command = [
        "python3",
        "rg_tool.py",
        f"--target={args.retro_go_target}",
        "build",
        "launcher",
        "prboom-go",
    ]
    run_in_idf_env(args.retro_go_idf_path, command, args.retro_go_root)


def generate_partition_table(args, output_path):
    command = [
        "python3",
        str(args.micropython_idf_path / "components/partition_table/gen_esp32part.py"),
        str(args.partition_csv),
        str(output_path),
    ]
    run(command)


def create_image(image_path, bootloader_path, partition_table_path, micropython_path, prboom_path, partitions):
    bootloader_offset = 0x0
    partition_offset = 0x8000
    factory = partitions["factory"]
    prboom = partitions["prboom-go"]

    bootloader = bootloader_path.read_bytes()
    partition_table = partition_table_path.read_bytes()
    micropython = micropython_path.read_bytes()
    prboom_bin = prboom_path.read_bytes()

    if len(micropython) > factory["size"]:
        raise ValueError(
            f"MicroPython image overflows factory partition by {len(micropython) - factory['size']} bytes"
        )
    if len(prboom_bin) > prboom["size"]:
        raise ValueError(
            f"prboom-go image overflows prboom-go partition by {len(prboom_bin) - prboom['size']} bytes"
        )

    image_size = max(
        [bootloader_offset + len(bootloader), partition_offset + len(partition_table)]
        + [partition["offset"] + partition["size"] for partition in partitions.values()]
    )
    image = bytearray(b"\xff" * image_size)

    image[bootloader_offset : bootloader_offset + len(bootloader)] = bootloader
    image[partition_offset : partition_offset + len(partition_table)] = partition_table
    image[factory["offset"] : factory["offset"] + len(micropython)] = micropython
    image[prboom["offset"] : prboom["offset"] + len(prboom_bin)] = prboom_bin

    image_path.write_bytes(image)

    print(f"Created {image_path}")
    print(f"  bootloader @ 0x{bootloader_offset:06x} size={len(bootloader)}")
    print(f"  partitions @ 0x{partition_offset:06x} size={len(partition_table)}")
    print(
        f"  factory    @ 0x{factory['offset']:06x} size={len(micropython)} / {factory['size']}"
    )
    print(
        f"  prboom-go  @ 0x{prboom['offset']:06x} size={len(prboom_bin)} / {prboom['size']}"
    )
    if "vfs" in partitions:
        vfs = partitions["vfs"]
        print(f"  vfs        @ 0x{vfs['offset']:06x} size={vfs['size']}")


def main():
    script_path = pathlib.Path(__file__).resolve()
    rotor_root, vsdk_root, ventilastation_root = find_parent_root(script_path)
    default_build_dir = vsdk_root / "hardware/rotor/build"

    parser = argparse.ArgumentParser(description="Build a combined vsdk + voom ESP32 image")
    parser.add_argument(
        "--micropython-idf-path",
        type=pathlib.Path,
        default=ventilastation_root / "esp-idf/esp-5.5.2",
    )
    parser.add_argument(
        "--retro-go-idf-path",
        type=pathlib.Path,
        default=ventilastation_root / "esp-idf/esp-5.0.4",
    )
    parser.add_argument("--micropython-root", type=pathlib.Path, default=rotor_root / "micropython")
    parser.add_argument("--retro-go-root", type=pathlib.Path, default=vsdk_root / "apps/retro-go")
    parser.add_argument("--retro-go-target", default="ventilastation")
    parser.add_argument("--board", default="ESP32_GENERIC_S3")
    parser.add_argument("--board-variant", default="SPIRAM_OCT")
    parser.add_argument(
        "--partition-csv",
        type=pathlib.Path,
        default=vsdk_root / "hardware/rotor/partitions-ventilastation.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=default_build_dir,
    )
    parser.add_argument("--skip-micropython", action="store_true")
    parser.add_argument("--skip-retro-go", action="store_true")
    parser.add_argument("--skip-pack", action="store_true")
    parser.add_argument("--prboom-bin", type=pathlib.Path)
    args = parser.parse_args()

    args.micropython_idf_path = args.micropython_idf_path.resolve()
    args.retro_go_idf_path = args.retro_go_idf_path.resolve()
    args.micropython_root = args.micropython_root.resolve()
    args.retro_go_root = args.retro_go_root.resolve()
    args.partition_csv = args.partition_csv.resolve()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    micropython_build_dir = (
        args.micropython_root / "ports/esp32" / f"build-{args.board}-{args.board_variant}"
    )
    micropython_bootloader = micropython_build_dir / "bootloader/bootloader.bin"
    micropython_bin = micropython_build_dir / "micropython.bin"
    prboom_bin = args.prboom_bin or (args.retro_go_root / "prboom-go/build/prboom-go.bin")
    partition_bin = args.output_dir / "partition-table-ventilastation.bin"
    image_bin = args.output_dir / "vsdk-voom-esp32s3.bin"
    legacy_vfs_bin = args.output_dir / "vfs.bin"

    if not args.skip_micropython:
        build_micropython(args, vsdk_root)

    if not args.skip_retro_go:
        build_retro_go(args)

    if args.skip_pack:
        return

    ensure_file(args.partition_csv, "Partition CSV")
    ensure_file(micropython_bootloader, "MicroPython bootloader")
    ensure_file(micropython_bin, "MicroPython application")
    ensure_file(prboom_bin, "prboom-go application")

    generate_partition_table(args, partition_bin)
    partitions = parse_partition_table(args.partition_csv)
    if legacy_vfs_bin.exists():
        legacy_vfs_bin.unlink()
    create_image(image_bin, micropython_bootloader, partition_bin, micropython_bin, prboom_bin, partitions)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
