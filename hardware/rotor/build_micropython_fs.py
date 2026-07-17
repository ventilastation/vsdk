#!/usr/bin/env python3
"""Build a LittleFS2 image pre-populated with MicroPython app files."""

import argparse
import gzip
import os
import pathlib
import struct
import sys

BLOCK_SIZE = 4096  # SPI flash sector size on ESP32

SKIP_FILE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "README.md",
    "boot.json",
    "settings.json",
    "wifi_config.json",  # device-specific, managed outside the repo
}

SKIP_DIR_NAMES = {
    "__pycache__",
    "images",
    "sounds",
    "src",
    "sources",
}

ALLOWED_SUFFIXES = {
    ".json",
    ".py",
    ".rom",
    ".txt",
    ".wad",  # Doom WAD files for prboom-go
    ".yaml",
    ".yml",
}

# Console ROM extensions accepted under the emulator "roms/<system>" trees (read
# by gwenesis / retro-core). Scoped to those trees so .bin/.zip elsewhere aren't
# swept in. README.md is excluded via SKIP_FILE_NAMES.
ROM_SUFFIXES = {
    ".nes", ".sms", ".gg", ".col", ".gb", ".gbc", ".zip",
    ".rom", ".mx1", ".mx2", ".dsk", ".cas", ".fdi", ".gz",
}
EMU_ROM_ROOTS = {"roms/nes", "roms/sms", "roms/gb", "roms/msx"}

# Paths under EMU_ROM_ROOTS that end in ".rom" (MSX cartridge/BIOS dumps) are
# read directly by fMSX via zlib's gzFile (see MSX.c's fread->gzread remap),
# which expects a bare gzip stream -- so they keep the old plain-gzip,
# ".rom.gz" on-flash form. Sprite ROMs (ventilastation's own image format,
# read by director.load_rom()/menurom.py) get the length-prefixed ".romz"
# form instead; see compress_sprite_rom() and docs/internals/rom-format.md.
_NON_SPRITE_ROM_PREFIXES = ("roms/msx/", "retro-go/bios/msx/")


def is_sprite_rom_path(remote_path):
    return remote_path.endswith(".rom") and not remote_path.startswith(_NON_SPRITE_ROM_PREFIXES)


def compress_sprite_rom(data):
    """<uint32 LE uncompressed size><gzip data>. The size lets director.py
    preallocate one exact-sized buffer and deflate.DeflateIO.readinto() it
    directly, instead of DeflateIO.read()'s unsized read -- which reallocates
    and copies repeatedly as it grows, the slow path this format replaces."""
    return struct.pack("<I", len(data)) + gzip.compress(data, compresslevel=9, mtime=0)


def iter_copy_jobs(vsdk_root):
    roots = [
        ("main.py", vsdk_root / "apps/micropython/main.py"),
        ("vs2.py", vsdk_root / "apps/micropython/vs2.py"),
        ("ventilastation", vsdk_root / "apps/micropython/ventilastation"),
        ("roms", vsdk_root / "apps/micropython/roms"),
        ("roms/doom", vsdk_root / "apps/retro-go/prboom-go/components/prboom/data"),
        # Console ROMs, served from /vfs/roms/<system> (gitignored locally).
        ("roms/nes", vsdk_root / "apps/retro-go/roms/nes"),    # retro-core (NES)
        ("roms/sms", vsdk_root / "apps/retro-go/roms/sms"),    # retro-core (Master System)
        ("roms/gb", vsdk_root / "apps/retro-go/roms/gb"),      # retro-core (Game Boy / Color)
        ("roms/msx", vsdk_root / "apps/retro-go/roms/msx"),    # fMSX
        ("retro-go/bios/msx", vsdk_root / "apps/retro-go/roms/bios/msx"),
        ("games", vsdk_root / "games"),
        ("system", vsdk_root / "system"),
    ]

    for remote_root, local_root in roots:
        if local_root.is_file():
            yield ("file", remote_root, local_root)
            continue

        yielded_dirs = {remote_root}
        yield ("dir", remote_root, local_root)

        for dirpath, dirnames, filenames in os.walk(local_root):
            dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIR_NAMES)
            filenames.sort()

            current_dir = pathlib.Path(dirpath)
            for filename in filenames:
                path = current_dir / filename
                relative = path.relative_to(local_root)
                if path.name in SKIP_FILE_NAMES or path.name.startswith("test_"):
                    continue
                allowed = ROM_SUFFIXES if remote_root in EMU_ROM_ROOTS else ALLOWED_SUFFIXES
                if path.suffix.lower() not in allowed:
                    continue

                parent = relative.parent
                if parent != pathlib.Path("."):
                    missing_parts = []
                    cumulative = []
                    for part in parent.parts:
                        cumulative.append(part)
                        dir_key = f"{remote_root}/{'/'.join(cumulative)}"
                        if dir_key not in yielded_dirs:
                            missing_parts.append((dir_key, local_root / pathlib.Path(*cumulative)))
                            yielded_dirs.add(dir_key)
                    for dir_key, dir_path in missing_parts:
                        yield ("dir", dir_key, dir_path)

                yield ("file", f"{remote_root}/{relative.as_posix()}", path)


def build_image(vsdk_root, partition_size, output_path, empty=False):
    try:
        from littlefs import LittleFS
    except ImportError:
        print("error: littlefs-python not installed. Run: pip install littlefs-python", file=sys.stderr)
        sys.exit(1)

    block_count = partition_size // BLOCK_SIZE
    fs = LittleFS(block_size=BLOCK_SIZE, block_count=block_count)

    if empty:
        output_path.write_bytes(fs.context.buffer)
        print(f"Created {output_path}")
        print(f"  0 files (empty), {len(fs.context.buffer):,} bytes ({block_count} blocks × {BLOCK_SIZE})")
        return

    for retro_go_dir in ("retro-go", "retro-go/cache", "retro-go/saves", "retro-go/config"):
        print(f"  mkdir /{retro_go_dir}")
        fs.makedirs(f"/{retro_go_dir}", exist_ok=True)

    for kind, remote_path, local_path in iter_copy_jobs(vsdk_root):
        lfs_path = "/" + remote_path
        if kind == "dir":
            print(f"  mkdir {lfs_path}")
            fs.makedirs(lfs_path, exist_ok=True)
        else:
            with open(local_path, "rb") as f_in:
                data = f_in.read()
            # Sprite ROMs are palette-indexed image data and compress ~85% with
            # deflate. Store them length-prefixed-gzip-compressed under a
            # ".romz" name (so they are not confused with raw ROMs) to save
            # flash; director.py/menurom.py find the ".romz" file and inflate
            # it via the `deflate` module.
            if is_sprite_rom_path(remote_path):
                payload = compress_sprite_rom(data)
                lfs_path += "z"
                print(f"  add   {lfs_path}  ({len(data):,} -> {len(payload):,} incl. header, gzip)")
                data = payload
            elif lfs_path.endswith(".rom"):
                # MSX cartridge/BIOS dumps: fMSX reads these as a bare gzip
                # stream (see is_sprite_rom_path()), so no length header.
                compressed = gzip.compress(data, compresslevel=9, mtime=0)
                lfs_path += ".gz"
                print(f"  add   {lfs_path}  ({len(data):,} -> {len(compressed):,} gzip)")
                data = compressed
            else:
                print(f"  add   {lfs_path}")
            with fs.open(lfs_path, "wb") as f_out:
                f_out.write(data)

    output_path.write_bytes(fs.context.buffer)
    used = sum(1 for _ in iter_copy_jobs(vsdk_root) if _[0] == "file")
    print(f"Created {output_path}")
    print(f"  {used} files, {len(fs.context.buffer):,} bytes ({block_count} blocks × {BLOCK_SIZE})")


def main():
    script_path = pathlib.Path(__file__).resolve()
    vsdk_root = script_path.parents[2]
    default_output = vsdk_root / "hardware/rotor/build/vfs.bin"

    parser = argparse.ArgumentParser(description="Build a LittleFS2 image from MicroPython app files")
    parser.add_argument(
        "--partition-size",
        type=lambda x: int(x, 0),
        default=0x8C0000,
        help="VFS partition size in bytes (default: 0x8c0000 = 9,175,040 bytes, matches partitions-ventilastation.csv)",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=default_output,
    )
    parser.add_argument(
        "--empty",
        action="store_true",
        help="Produce a formatted image with no files (for bench bring-up; see make initial-flash)",
    )
    args = parser.parse_args()

    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    build_image(vsdk_root, args.partition_size, args.output, empty=args.empty)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
