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
    website_root = vsdk_root.parent
    return vsdk_root, website_root.parent


def ensure_file(path, description):
    if not path.exists():
        raise FileNotFoundError(f"{description} not found: {path}")


def maybe_build(args, vsdk_root):
    if not args.build:
        return

    build_script = vsdk_root / "hardware/rotor/build_voom_image.py"
    command = ["python3", str(build_script)]
    if args.micropython_idf_path:
        command.extend(["--micropython-idf-path", str(args.micropython_idf_path)])
    if args.retro_go_idf_path:
        command.extend(["--retro-go-idf-path", str(args.retro_go_idf_path)])
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
        "0x0",
        str(image_path),
    ]
    run_in_idf_env(args.idf_path, command, cwd=image_path.parent)


def main():
    script_path = pathlib.Path(__file__).resolve()
    vsdk_root, parent_root = find_parent_root(script_path)
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
        default=parent_root / "esp-idf-5.4",
        help="ESP-IDF used to provide esptool and flash helpers",
    )
    parser.add_argument(
        "--micropython-idf-path",
        type=pathlib.Path,
        help="Optional override passed through when --build is used",
    )
    parser.add_argument(
        "--retro-go-idf-path",
        type=pathlib.Path,
        help="Optional override passed through when --build is used",
    )
    args = parser.parse_args()

    args.image = args.image.resolve()
    args.idf_path = args.idf_path.resolve()
    if args.micropython_idf_path:
        args.micropython_idf_path = args.micropython_idf_path.resolve()
    if args.retro_go_idf_path:
        args.retro_go_idf_path = args.retro_go_idf_path.resolve()

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
