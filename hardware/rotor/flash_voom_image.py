#!/usr/bin/env python3

import argparse
import os
import pathlib
import subprocess
import sys


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


def maybe_build(args, vsdk_root):
    if not args.build:
        return

    build_script = vsdk_root / "hardware/rotor/build_voom_image.py"
    command = ["python3", str(build_script), "--idf-path", str(args.idf_path)]
    run(command, cwd=vsdk_root)


def flash_image(args, image_path):
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
        # patch the bootloader header: the built image may carry a smaller
        # flash size, and the 16MB board fails to boot with it (same flag as
        # deploy_micropython_fs.py)
        "--flash_size",
        "16MB",
        "0x0",
        str(image_path),
    ]
    run(command, cwd=image_path.parent)


def main():
    script_path = pathlib.Path(__file__).resolve()
    vsdk_root, _ = find_parent_root(script_path)
    default_image = vsdk_root / "hardware/rotor/build/vsdk-voom-esp32s3.bin"

    parser = argparse.ArgumentParser(description="Flash the combined vsdk + voom ESP32 image")
    parser.add_argument("--port", required=True, help="Serial port, for example /dev/cu.usbmodemXXXX")
    parser.add_argument("--baud", type=int, default=1500000)
    parser.add_argument("--build", action="store_true", help="Build the combined image before flashing")
    parser.add_argument(
        "--image",
        type=pathlib.Path,
        default=default_image,
        help="Path to the combined image produced by build_voom_image.py",
    )
    parser.add_argument(
        "--idf-path",
        type=pathlib.Path,
        default=os.environ.get("IDF_PATH"),
        help="Defaults to $IDF_PATH -- source esp-idf's export.sh first",
    )
    args = parser.parse_args()

    if not args.idf_path:
        sys.exit("IDF_PATH is not set -- source esp-idf's export.sh first (see docs/internals/building.md)")

    args.image = args.image.resolve()
    args.idf_path = args.idf_path.resolve()

    maybe_build(args, vsdk_root)
    ensure_file(args.image, "Combined image")
    flash_image(args, args.image)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
