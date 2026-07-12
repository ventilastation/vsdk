#!/usr/bin/env python3
"""Assemble a fixed-layout OTA release bundle from a completed dev build.

Bundle layout: <output>/manifest.json + <output>/files/<device_path> +
<output>/partitions/<name>. Serve it on a production base (no ESP-IDF/
Retro-Go toolchain needed there) with:

    python3 emulator/upgrade_server.py --bundle <output> --port 5653

Reuses emulator/upgrade_server.py's own manifest/file-content logic (which
itself reuses hardware/rotor/build_micropython_fs.py's iter_copy_jobs()), so
there's exactly one source of truth for "what files go on the device" --
the bundle always matches what a live dev-loop OTA or a fresh USB flash
would install.
"""

import argparse
import importlib.util
import json
import pathlib
import sys

_VSDK_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_upgrade_server():
    spec = importlib.util.spec_from_file_location(
        "upgrade_server", _VSDK_ROOT / "emulator" / "upgrade_server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_bundle(upgrade_server, output):
    files_dir = output / "files"
    partitions_dir = output / "partitions"
    files_dir.mkdir(parents=True, exist_ok=True)
    partitions_dir.mkdir(parents=True, exist_ok=True)

    manifest = upgrade_server._build_manifest()

    written_files = 0
    for entry in manifest["files"]:
        device_path = entry["path"]
        data = upgrade_server._read_device_file(device_path)
        if data is None:
            print(f"package_release: warning: missing file {device_path}, skipping", file=sys.stderr)
            continue
        dest = files_dir / device_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        written_files += 1

    written_partitions = 0
    for name in manifest["partitions"]:
        bin_path = upgrade_server._PARTITION_BINS.get(name)
        if not bin_path or not bin_path.is_file():
            print(f"package_release: warning: missing partition {name}, skipping", file=sys.stderr)
            continue
        (partitions_dir / name).write_bytes(bin_path.read_bytes())
        written_partitions += 1

    (output / "manifest.json").write_text(json.dumps(manifest))
    return written_files, written_partitions


def main():
    parser = argparse.ArgumentParser(description="Assemble a fixed-layout OTA release bundle")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    output = args.output.resolve()
    upgrade_server = _load_upgrade_server()
    written_files, written_partitions = build_bundle(upgrade_server, output)

    print(f"package_release: wrote bundle to {output}")
    print(f"  {written_files} files, {written_partitions} partitions")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
