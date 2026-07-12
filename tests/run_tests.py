#!/usr/bin/env python3
"""vsdk test runner.

Usage: python3 tests/run_tests.py

Runs, from the repo root:
  1. an mpy-cross compile check over every MicroPython source
  2. the CPython test scripts
  3. the MicroPython test scripts (skipped with a warning if no
     `micropython` unix binary is on PATH)
  4. the native renderer host tests (skipped with a warning if no C
     compiler is on PATH)

Exits non-zero on the first category that fails.
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

MPY_SOURCE_ROOTS = [
    ROOT / "apps" / "micropython" / "main.py",
    ROOT / "apps" / "micropython" / "boot.py",
    ROOT / "apps" / "micropython" / "vs2.py",
    ROOT / "apps" / "micropython" / "updater.py",
    ROOT / "apps" / "micropython" / "vsdk_recovery.py",
    ROOT / "apps" / "micropython" / "vsdk_logo_strip.py",
    ROOT / "apps" / "micropython" / "ventilastation",
    ROOT / "system",
    ROOT / "games",
]

CPYTHON_TESTS = [
    "tests/test_shuffler.py",
    "tests/test_ventilagon_parity.py",
    "tests/test_rom_format.py",
    "tests/test_vs2_api.py",
    "tests/test_base_control.py",
    "tests/test_uart_logging.py",
    "tests/test_tutorial_vs2.py",
    "tests/test_emulator_vs2_render.py",
    "tests/test_mapdemo_vs2.py",
    "tests/test_vixeous_vs2.py",
    "tests/test_recovery.py",
    "tests/test_updater.py",
    "tests/test_boot.py",
]

MICROPYTHON_TESTS = [
    "tests/test_director_headless.py",
]


def iter_mpy_sources():
    for root in MPY_SOURCE_ROOTS:
        if root.is_file():
            yield root
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" not in path.parts:
                yield path


def check_mpy_compile():
    mpy_cross = shutil.which("mpy-cross")
    if not mpy_cross:
        print("SKIP mpy-cross compile check (mpy-cross not on PATH)")
        return True
    failures = 0
    count = 0
    out = ROOT / "build"
    out.mkdir(exist_ok=True)
    for path in iter_mpy_sources():
        count += 1
        result = subprocess.run(
            [mpy_cross, str(path), "-o", str(out / "check.mpy")],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            failures += 1
            print(f"COMPILE FAIL {path.relative_to(ROOT)}\n{result.stderr}")
    print(f"mpy-cross: {count} files, {failures} failures")
    return failures == 0


def run_scripts(interpreter, scripts, label):
    if not shutil.which(interpreter):
        print(f"SKIP {label} tests ({interpreter} not on PATH)")
        return True
    ok = True
    for script in scripts:
        if not (ROOT / script).exists():
            print(f"SKIP {script} (missing)")
            continue
        print(f"--- {interpreter} {script}")
        result = subprocess.run([interpreter, script], cwd=ROOT)
        if result.returncode != 0:
            ok = False
            print(f"FAIL {script}")
    return ok


NATIVE_TEST_SOURCES = [
    "hardware/rotor/modules/povdisplay/gpu.c",
    "tests/native/test_render_vs2.c",
]


def run_native_tests():
    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        print("SKIP native renderer tests (no C compiler on PATH)")
        return True
    with tempfile.TemporaryDirectory() as tmpdir:
        binary = pathlib.Path(tmpdir) / "test_render_vs2"
        compile_cmd = [
            compiler, "-std=c11", "-Wall",
            "-I", "tests/native/stubs",
            "-I", "hardware/rotor/modules/povdisplay",
            "-o", str(binary),
        ] + NATIVE_TEST_SOURCES + ["-lm"]
        print(f"--- {compiler} tests/native/test_render_vs2.c")
        result = subprocess.run(compile_cmd, cwd=ROOT)
        if result.returncode != 0:
            print("FAIL native renderer tests (compile)")
            return False
        result = subprocess.run([str(binary)], cwd=ROOT)
        if result.returncode != 0:
            print("FAIL native renderer tests")
            return False
    return True


def main():
    ok = check_mpy_compile()
    ok = run_scripts(sys.executable, CPYTHON_TESTS, "CPython") and ok
    ok = run_scripts("micropython", MICROPYTHON_TESTS, "MicroPython") and ok
    ok = run_native_tests() and ok
    print("ALL PASS" if ok else "FAILURES")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
