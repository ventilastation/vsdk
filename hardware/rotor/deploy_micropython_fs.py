#!/usr/bin/env python3

import argparse
import os
import pathlib
import sys


SKIP_FILE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "README.md",
    "boot.json",
    "settings.json",
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
    ".yaml",
    ".yml",
}

FS_PUT_CHUNK_SIZE = 4096


FORMAT_SCRIPT = """
import uos
import vfs
from flashbdev import bdev

try:
    vfs.umount("/")
except OSError:
    pass

uos.VfsLfs2.mkfs(bdev)
vfs.mount(bdev, "/")
print("formatted vfs")
"""


def find_parent_root(script_path):
    vsdk_root = script_path.parents[2]
    website_root = vsdk_root.parent
    return vsdk_root, website_root.parent


def load_pyboard_module(micropython_root):
    sys.path.insert(0, str(micropython_root / "tools"))
    import pyboard  # type: ignore

    return pyboard


def iter_copy_jobs(vsdk_root):
    roots = [
        ("main.py", vsdk_root / "apps/micropython/main.py"),
        ("ventilastation", vsdk_root / "apps/micropython/ventilastation"),
        ("roms", vsdk_root / "apps/micropython/roms"),
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
                if path.suffix.lower() not in ALLOWED_SUFFIXES:
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


def deploy_filesystem(args):
    pyboard = load_pyboard_module(args.micropython_root)
    board = pyboard.Pyboard(
        args.port,
        args.baud,
        wait=args.wait,
        exclusive=not args.no_exclusive,
    )
    try:
        board.enter_raw_repl(soft_reset=True, timeout_overall=args.wait)
        print("Formatting vfs as Lfs2...")
        board.exec(FORMAT_SCRIPT, timeout=30)

        created_dirs = set()
        for kind, remote_path, local_path in iter_copy_jobs(args.vsdk_root):
            if kind == "dir":
                if remote_path in created_dirs:
                    continue
                print(f"mkdir :{remote_path}")
                board.fs_mkdir(remote_path)
                created_dirs.add(remote_path)
                continue

            parent = remote_path.rsplit("/", 1)[0] if "/" in remote_path else ""
            if parent and parent not in created_dirs:
                raise RuntimeError(f"Parent directory was not created for {remote_path}")
            print(f"cp {local_path} :{remote_path}")
            board.fs_put(str(local_path), remote_path, chunk_size=FS_PUT_CHUNK_SIZE)

        board.exec(
            "import os\n"
            "try:\n"
            "    os.sync()\n"
            "except AttributeError:\n"
            "    pass\n"
            "print('filesystem synced')\n",
            timeout=10,
        )
        try:
            board.exec_raw_no_follow("import machine\nmachine.reset()\n")
        except Exception:
            pass
    finally:
        try:
            board.close()
        except Exception:
            pass


def main():
    script_path = pathlib.Path(__file__).resolve()
    vsdk_root, parent_root = find_parent_root(script_path)

    parser = argparse.ArgumentParser(description="Format and upload the MicroPython filesystem tree")
    parser.add_argument("--port", required=True, help="Serial port, for example /dev/cu.usbmodemXXXX")
    parser.add_argument("--baud", type=int, default=2000000)
    parser.add_argument("--wait", type=int, default=15, help="Seconds to wait for the board to reappear")
    parser.add_argument(
        "--micropython-root",
        type=pathlib.Path,
        default=parent_root / "micropython",
    )
    parser.add_argument("--no-exclusive", action="store_true")
    args = parser.parse_args()

    args.vsdk_root = vsdk_root
    args.micropython_root = args.micropython_root.resolve()
    deploy_filesystem(args)


if __name__ == "__main__":
    main()
