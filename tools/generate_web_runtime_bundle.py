#!/usr/bin/env python3
"""Build web/runtime-manifest.json and web/runtime-bundle.json.

The browser emulator's worker mounts its MicroPython filesystem from the
bundle; the manifest lists every runtime file, including the PNGs and sounds
the worker fetches over HTTP when it needs them. Both are build output and
are not committed: the desktop emulator's web server rebuilds them when the
page asks for them, and publishing rebuilds them
(docs/internals/deploying-web-emulator.md).

The bundle embeds the sprite ROMs, so every build first brings them up to
date with tools/generate_roms.py. When no input changed since the last build
nothing is rewritten, which keeps this cheap enough to run on every page
load.

Usage: python3 tools/generate_web_runtime_bundle.py [--force]
"""

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT_DIR / "tools"
MANIFEST_PATH = ROOT_DIR / "web" / "runtime-manifest.json"
BUNDLE_PATH = ROOT_DIR / "web" / "runtime-bundle.json"
ROMS_DIR = ROOT_DIR / "apps" / "micropython" / "roms"
SOURCE_ROOTS = ("apps/micropython", "games", "system")
NOT_BUNDLED_SUFFIXES = {".png", ".yaml", ".yml", ".mp3", ".wav", ".ogg"}


class MissingDependencies(RuntimeError):
    """The ROM generator's Python packages are not installed."""


def load_generate_roms():
    """tools/generate_roms.py as a module, loaded by path so callers outside
    tools/ (the desktop emulator) can use it too."""
    module = sys.modules.get("generate_roms")
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location("generate_roms", TOOLS_DIR / "generate_roms.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_roms"] = module
    try:
        spec.loader.exec_module(module)
    except ImportError as error:
        del sys.modules["generate_roms"]
        raise MissingDependencies(
            f"building sprite ROMs needs numpy, Pillow and PyYAML ({error}); "
            "install them with: pip install -r requirements.txt"
        ) from error
    return module


def generate_roms():
    """Bring apps/micropython/roms up to date (only changed ROMs are rebuilt)."""
    load_generate_roms().generate_all()


def visible_files():
    """Repo-relative paths under SOURCE_ROOTS that git would show: tracked,
    or new and not ignored. That keeps local leftovers (the emulator's
    *.mp3.wav decode caches, save files, deleted games) out of the
    published runtime, while a game that isn't committed yet still runs."""
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *SOURCE_ROOTS],
            cwd=ROOT_DIR, capture_output=True, check=True,
        ).stdout.decode("utf-8")
        candidates = {path for path in listing.split("\0") if path}
    except (OSError, subprocess.CalledProcessError):
        # Not a git checkout (or no git on PATH): fall back to the tree,
        # minus the leftovers we know about.
        candidates = set()
        for root_name in SOURCE_ROOTS:
            for dirpath, dirnames, filenames in os.walk(ROOT_DIR / root_name):
                dirnames[:] = [name for name in dirnames if name != "__pycache__"]
                for filename in filenames:
                    if filename.endswith(".mp3.wav"):
                        continue
                    candidates.add((Path(dirpath) / filename).relative_to(ROOT_DIR).as_posix())
    # The index still lists files deleted from the working tree.
    return sorted(path for path in candidates if (ROOT_DIR / path).is_file())


ASSET_DIR_NAMES = {"images", "sounds", "src", "sources"}


def is_runtime_source(path):
    parts = path.split("/")
    if parts[0] == "apps":
        # apps/micropython/*.py and the ventilastation and vs2 packages;
        # the roms folder holds generated files and is handled below.
        return path.endswith(".py") and (len(parts) == 3 or parts[2] in ("ventilastation", "vs2"))
    # Code, meta.json and the data files games read at run time (song
    # charts, score tables), outside the asset folders: the same files the
    # console's filesystem image gets (hardware/rotor/build_micropython_fs.py).
    return path.endswith((".py", ".json", ".txt")) and not ASSET_DIR_NAMES.intersection(parts)


def is_workspace_asset(path):
    parts = path.split("/")
    if parts[0] == "apps":
        return False
    if parts[0] == "games" and len(parts) == 4 and parts[3] == "menu.png":
        return True
    if "/images/" in path and (parts[-1] == "__images__.yaml" or path.lower().endswith(".png")):
        return True
    return "/sounds/" in path


def rom_files(files):
    """The ROMs some current __images__.yaml produces, so a ROM left behind
    by a renamed or deleted game is not published."""
    rom_name_for_folder = load_generate_roms().rom_name_for_folder
    paths = []
    for path in files:
        if Path(path).name != "__images__.yaml":
            continue
        rom = ROMS_DIR / (rom_name_for_folder((ROOT_DIR / path).parent) + ".rom")
        if rom.is_file():
            paths.append(rom.relative_to(ROOT_DIR).as_posix())
    return sorted(set(paths))


def manifest_files():
    files = visible_files()
    runtime_sources = [path for path in files if is_runtime_source(path)]
    assets = [path for path in files if is_workspace_asset(path)]
    return runtime_sources + rom_files(files) + assets


def is_bundled(path):
    return Path(path).suffix.lower() not in NOT_BUNDLED_SUFFIXES


def fingerprint(files):
    """Hash of everything the two outputs are made from: the file list, the
    bytes of every bundled file, and this script."""
    digest = hashlib.sha256(Path(__file__).read_bytes())
    for path in files:
        digest.update(path.encode("utf-8") + b"\0")
        if is_bundled(path):
            digest.update(hashlib.sha256((ROOT_DIR / path).read_bytes()).digest())
    return digest.hexdigest()


def current_fingerprint():
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("fingerprint")
    except (OSError, ValueError, AttributeError):
        return None


def write_atomically(path, text):
    """Readers (the web server, a publish copy) never see half a file."""
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


def build(force=False):
    """Bring the ROMs, the manifest and the bundle up to date. Returns True
    when the manifest and bundle were rewritten, False when they already
    matched their inputs."""
    generate_roms()
    files = manifest_files()
    new_fingerprint = fingerprint(files)
    if not force and BUNDLE_PATH.is_file() and current_fingerprint() == new_fingerprint:
        return False

    entries = [
        {"path": path, "base64": base64.b64encode((ROOT_DIR / path).read_bytes()).decode("ascii")}
        for path in files
        if is_bundled(path)
    ]
    write_atomically(BUNDLE_PATH, json.dumps({"version": 1, "files": entries}, ensure_ascii=True, separators=(",", ":")))
    # Written last: its fingerprint vouches for the bundle beside it.
    manifest = {"fingerprint": new_fingerprint, "files": files}
    write_atomically(MANIFEST_PATH, json.dumps(manifest, ensure_ascii=True, indent=2) + "\n")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="rewrite the manifest and bundle even if nothing changed")
    args = parser.parse_args(argv)
    try:
        rebuilt = build(force=args.force)
    except MissingDependencies as error:
        raise SystemExit(f"generate_web_runtime_bundle: {error}")
    if rebuilt:
        print(f"Wrote {MANIFEST_PATH.relative_to(ROOT_DIR)} and {BUNDLE_PATH.relative_to(ROOT_DIR)}")
    else:
        print("Web runtime bundle is up to date")


if __name__ == "__main__":
    main()
