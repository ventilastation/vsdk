#!/usr/bin/env python3
"""Flash every partition over USB in one shot -- the fastest way to bring up
a board from scratch.

`make flash-recovery` (USB-flash `factory` + NVS only, everything else over
WiFi OTA) is the normal bring-up procedure, but a from-scratch OTA has to
download and write the *entire* LFS content tree and every native app
partition over WiFi at ~1 MB/s with per-file HTTP round trips (see
docs/internals/ota.md's "Incremental partition writes" note) -- much slower
than one big USB burst at `--baud`. This script instead writes `factory`,
`prboom-go`, `retro-core`, `micropython` (ota_2), `fmsx` and a fully
populated `vfs` in a single `esptool write_flash` call, then primes the
on-device OTA state (NVS `vsdk_ota` partition hashes + the vfs's
`.vsdk_lfs_cache.json`, the latter baked in by build_micropython_fs.py
itself) to match exactly what was just flashed -- so the board's first
OTA/recovery pass afterwards finds every tier already up to date and only
verifies it (local flash reads + hashing), instead of re-downloading
everything it was just given over USB.

This is `make flash-full`. WiFi credentials and board-wiring NVS are
deliberately not touched here -- run `make wifi-provision` / `make
configure-board` (or their -v2/-eu variants) separately, same as after
`make flash-recovery`.
"""

import argparse
import csv
import hashlib
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
import nvs_partition

# Must match the "nvs" row in partitions-ventilastation.csv.
NVS_OFFSET = 0x9000
NVS_SIZE = 0x4000

# NVS namespace "vsdk_ota" keys, matching apps/micropython/updater.py's
# _NVS_KEYS -- the SHA256 of the last-known-good write of each partition.
_OTA_NVS_KEYS = {
    "prboom-go": "prboom_sha",
    "retro-core": "retro_sha",
    "fmsx": "fmsx_sha",
    "micropython": "mp_sha",
}


def run(cmd, cwd=None):
    print(f"Running: {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def find_parent_root(script_path):
    vsdk_root = script_path.parents[2]
    ventilastation_root = vsdk_root.parents[1]
    return vsdk_root, ventilastation_root


def ensure_file(path, description):
    if not path.exists():
        raise FileNotFoundError(f"{description} not found: {path}")


def parse_partition_csv(path):
    """name -> (offset, size) from a standard ESP-IDF partitions CSV. Reads
    the CSV itself rather than hardcoding offsets here, so this never drifts
    from partitions-ventilastation.csv the way flash_vsdk_image.py's old
    hand-copied VFS_OFFSET/VFS_PARTITION_SIZE constants once did."""
    partitions = {}
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            name = row[0].strip()
            if not name or name.startswith("#"):
                continue
            partitions[name] = (int(row[3].strip(), 0), int(row[4].strip(), 0))
    return partitions


def generate_partition_table(idf_path, partition_csv, output_path):
    run([
        "python3",
        str(idf_path / "components/partition_table/gen_esp32part.py"),
        str(partition_csv),
        str(output_path),
    ])


def build_vfs_image(build_fs_script, partition_size, output_path):
    # No --empty: a real, fully populated image (code, ROMs, game assets),
    # with its OTA hash cache baked in by build_micropython_fs.py itself.
    run([
        "python3", str(build_fs_script),
        "--partition-size", hex(partition_size),
        "--output", str(output_path),
    ])


def write_flash_all(args, bootloader_path, partition_table_path, micropython_path,
                     native_app_bins, vfs_image_path, partitions):
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
        "0x0", str(bootloader_path),
        "0x8000", str(partition_table_path),
        hex(partitions["factory"][0]), str(micropython_path),
        hex(partitions["prboom-go"][0]), str(native_app_bins["prboom-go"]),
        hex(partitions["retro-core"][0]), str(native_app_bins["retro-core"]),
        hex(partitions["micropython"][0]), str(micropython_path),
        hex(partitions["fmsx"][0]), str(native_app_bins["fmsx"]),
        hex(partitions["vfs"][0]), str(vfs_image_path),
    ]
    run(command, cwd=micropython_path.parent)


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def prime_ota_nvs(idf_path, port, baud, partition_bins):
    """Write vsdk_ota's stored partition hashes to match exactly what was
    just flashed, preserving every other existing NVS key (vs_board wiring,
    devel_wifi credentials) -- same read-merge-write as provision_board.py /
    provision_wifi.py / flash_recovery_image.py. Without this, the board's
    first OTA/recovery pass would see no stored hash for any of these four
    partitions and re-flash all of them over WiFi even though their content
    already matches the manifest exactly."""
    updates = {}
    print("flash_full_image: priming vsdk_ota NVS hashes to match the just-flashed partitions:")
    for name, path in partition_bins.items():
        sha = _sha256_file(path)
        updates[("vsdk_ota", _OTA_NVS_KEYS[name])] = sha
        print(f"  {_OTA_NVS_KEYS[name]} = {sha}  ({name})")
    nvs_partition.provision(idf_path, port, NVS_OFFSET, NVS_SIZE, updates, baud=baud)


def main():
    script_path = pathlib.Path(__file__).resolve()
    vsdk_root, _ = find_parent_root(script_path)
    default_build_dir = vsdk_root / "hardware/rotor/build"

    parser = argparse.ArgumentParser(
        description="Flash every partition over USB in one shot (fastest from-scratch bring-up)"
    )
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
        "--retro-go-dir",
        type=pathlib.Path,
        default=vsdk_root / "apps/retro-go",
    )
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=default_build_dir,
    )
    args = parser.parse_args()

    if not args.idf_path:
        sys.exit("IDF_PATH is not set -- source esp-idf's export.sh first (see docs/internals/building.md)")

    args.idf_path = args.idf_path.resolve()
    args.partition_csv = args.partition_csv.resolve()
    args.micropython_root = args.micropython_root.resolve()
    args.retro_go_dir = args.retro_go_dir.resolve()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    micropython_build_dir = (
        args.micropython_root / "ports/esp32" / f"build-{args.board}-{args.board_variant}"
    )
    bootloader_path = micropython_build_dir / "bootloader/bootloader.bin"
    micropython_path = micropython_build_dir / "micropython.bin"
    partition_table_path = args.output_dir / "partition-table-ventilastation.bin"
    vfs_image_path = args.output_dir / "vfs.bin"
    build_fs_script = vsdk_root / "hardware/rotor/build_micropython_fs.py"

    native_app_bins = {
        "prboom-go": args.retro_go_dir / "prboom-go/build/prboom-go.bin",
        "retro-core": args.retro_go_dir / "retro-core/build/retro-core.bin",
        "fmsx": args.retro_go_dir / "fmsx/build/fmsx.bin",
    }

    ensure_file(bootloader_path, "MicroPython bootloader")
    ensure_file(micropython_path, "MicroPython application")
    ensure_file(args.partition_csv, "Partition CSV")
    for name, path in native_app_bins.items():
        ensure_file(path, f"{name} binary")

    partitions = parse_partition_csv(args.partition_csv)
    for name in ("factory", "prboom-go", "retro-core", "micropython", "fmsx", "vfs"):
        if name not in partitions:
            sys.exit(f"partition {name!r} not found in {args.partition_csv}")

    generate_partition_table(args.idf_path, args.partition_csv, partition_table_path)
    build_vfs_image(build_fs_script, partitions["vfs"][1], vfs_image_path)
    write_flash_all(args, bootloader_path, partition_table_path, micropython_path,
                     native_app_bins, vfs_image_path, partitions)

    partition_bins = dict(native_app_bins)
    partition_bins["micropython"] = micropython_path
    # prime_ota_nvs()'s NVS write is the last flash operation; esptool
    # hard-resets by default after every call (its --after default), so the
    # board is already rebooting into the fresh image by the time this
    # returns -- no separate reset step needed. (An earlier version of this
    # script added one anyway, over mpremote: `mpremote run` a script that
    # calls machine.reset() hangs forever, since the hard reset yanks the
    # USB-CDC port away mid-command with no clean return for mpremote to see
    # -- confirmed hanging on real hardware, not a hypothetical.)
    prime_ota_nvs(args.idf_path, args.port, args.baud, partition_bins)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
