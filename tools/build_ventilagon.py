#!/usr/bin/env python3
"""Build the original rotor Ventilagon sources for the desktop or web host."""
import argparse
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
HOST = ROOT / "emulator" / "ventilagon"
CORE = ROOT / "hardware" / "rotor" / "modules" / "povdisplay"
EXPORTS = ["enter", "exit", "update", "is_idle", "sending", "frame"]


def sources():
    manifest = (CORE / "micropython.cmake").read_text()
    return [CORE / name for name in re.findall(
        r"\$\{CMAKE_CURRENT_LIST_DIR\}/(ventilagon/\S+\.c)", manifest)] + [HOST / "host.c"]


def library_name():
    return "ventilagon.dll" if sys.platform == "win32" else (
        "libventilagon.dylib" if sys.platform == "darwin" else "libventilagon.so")


def build(wasm=False, output_dir=None, force=False, testing=False):
    output = Path(output_dir) if output_dir else (
        ROOT / "web" / "vendor" / "ventilagon" if wasm else HOST)
    output.mkdir(parents=True, exist_ok=True)
    target = output / ("ventilagon.mjs" if wasm else library_name())
    inputs = sources() + list((HOST / "compat").rglob("*.h")) + [
        HOST / "host.h", CORE / "ventilagon" / "ventilagon.h", CORE / "micropython.cmake",
        Path(__file__),
    ]
    if not force and not testing and target.exists() and all(
        path.stat().st_mtime <= target.stat().st_mtime for path in inputs
    ) and (not wasm or target.with_suffix(".wasm").exists()):
        return target
    compiler = os.environ.get("EMCC" if wasm else "CC") or shutil.which(
        "emcc" if wasm else "cc") or (None if wasm else shutil.which("clang"))
    if not compiler:
        raise RuntimeError("Ventilagon needs %s; run python3 tools/build_ventilagon.py%s" % (
            "Emscripten (emcc)" if wasm else "a C compiler or a prebuilt native library",
            " --wasm" if wasm else ""))
    args = shlex.split(compiler) + ["-std=c11", "-O2", "-Wall", "-Wextra",
        "-Wno-unused-parameter", "-Wno-sign-compare", "-I" + str(HOST / "compat"), "-I" + str(CORE / "ventilagon"),
        "-Drand=ventilagon_host_rand", "-Dsrand=ventilagon_host_srand"]
    exports = ["_ventilagon_host_" + name for name in EXPORTS]
    if testing:
        args.append("-DVENTILAGON_TEST")
        exports += ["_ventilagon_test_" + name for name in (
            "play", "empty", "wall", "state", "position", "row", "section", "drift", "set_drift", "reference_frame")]
    if wasm:
        args += ["-sMODULARIZE=1", "-sEXPORT_ES6=1", "-sENVIRONMENT=web,worker,node",
            "-sEXPORTED_FUNCTIONS=" + str(exports),
            "-sEXPORTED_RUNTIME_METHODS=['UTF8ToString','HEAPU8']"]
    else:
        args += ["-shared", "-fPIC"]
    args += [str(path) for path in sources()]
    # Never truncate a library another emulator process has mapped. Keep WASM
    # filenames stable so the generated loader resolves its sibling correctly.
    with tempfile.TemporaryDirectory(prefix=".ventilagon-build-", dir=output) as temp:
        built = Path(temp) / target.name
        subprocess.run(args + ["-o", str(built)], check=True)
        if wasm:
            os.replace(built.with_suffix(".wasm"), target.with_suffix(".wasm"))
        os.replace(built, target)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wasm", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--testing", action="store_true")
    parser.add_argument("--output-dir")
    opts = parser.parse_args()
    print(build(opts.wasm, opts.output_dir, opts.force, opts.testing))
