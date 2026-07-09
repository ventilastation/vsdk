#!/usr/bin/env python3
"""vsdk test runner.

Usage: python3 tests/run_tests.py

Runs, from the repo root:
  1. an mpy-cross compile check over every MicroPython source
  2. the CPython test scripts
  3. the MicroPython test scripts (skipped with a warning if no
     `micropython` unix binary is on PATH)

Exits non-zero on the first category that fails.
"""

import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

MPY_SOURCE_ROOTS = [
    ROOT / "apps" / "micropython" / "main.py",
    ROOT / "apps" / "micropython" / "ventilastation",
    ROOT / "system",
    ROOT / "games",
]

CPYTHON_TESTS = [
    "tests/test_shuffler.py",
    "tests/test_ventilagon_parity.py",
    "tests/test_rom_format.py",
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


def main():
    ok = check_mpy_compile()
    ok = run_scripts(sys.executable, CPYTHON_TESTS, "CPython") and ok
    ok = run_scripts("micropython", MICROPYTHON_TESTS, "MicroPython") and ok
    print("ALL PASS" if ok else "FAILURES")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
