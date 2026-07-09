#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_ROOT="${BUILD_ROOT:-/tmp/vsdk-micropython-webassembly}"
MICROPYTHON_DIR="${MICROPYTHON_DIR:-$BUILD_ROOT/micropython}"
EMSDK_DIR="${EMSDK_DIR:-$BUILD_ROOT/emsdk}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/web/vendor/micropython}"
MICROPYTHON_REPO="${MICROPYTHON_REPO:-https://github.com/micropython/micropython.git}"
MICROPYTHON_REF="${MICROPYTHON_REF:-d901e9834939372f68974010f32e146596a69bb0}"
EMSDK_REPO="${EMSDK_REPO:-https://github.com/emscripten-core/emsdk.git}"
EMSDK_REF="${EMSDK_REF:-d223ae73c6998296e3ab27cf81dc2c2c9fd383de}"
EMSDK_VERSION="${EMSDK_VERSION:-6.0.0}"
BUILD_JOBS="${BUILD_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"
VERSION_TAG="${VERSION_TAG:-$(date -u +%Y%m%dT%H%M%SZ)}"
TRACE_VARIANT_DIR="$ROOT_DIR/tools/micropython-webassembly/trace"
PATCH_FILE="$ROOT_DIR/tools/patches/micropython-webassembly-settrace.patch"

log() {
  printf '[build-micropython-webassembly] %s\n' "$*"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'Missing required command: %s\n' "$1" >&2
    exit 1
  }
}

ensure_checkout() {
  local repo_url="$1"
  local checkout_dir="$2"
  local ref="$3"

  if [[ ! -d "$checkout_dir/.git" ]]; then
    log "Cloning $repo_url into $checkout_dir"
    git clone "$repo_url" "$checkout_dir"
  fi

  log "Checking out $(basename "$checkout_dir") at $ref"
  git -C "$checkout_dir" fetch origin
  git -C "$checkout_dir" checkout "$ref"
  git -C "$checkout_dir" reset --hard "$ref"
  git -C "$checkout_dir" clean -fd
}

apply_patch_once() {
  local repo_dir="$1"
  local patch_file="$2"

  if git -C "$repo_dir" apply --check "$patch_file" >/dev/null 2>&1; then
    log "Applying patch $(basename "$patch_file")"
    git -C "$repo_dir" apply "$patch_file"
    return
  fi

  if git -C "$repo_dir" apply --reverse --check "$patch_file" >/dev/null 2>&1; then
    log "Patch $(basename "$patch_file") already applied"
    return
  fi

  printf 'Unable to apply patch cleanly: %s\n' "$patch_file" >&2
  exit 1
}

update_cache_versions() {
  python3 - "$ROOT_DIR" "$VERSION_TAG" <<'PY'
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
version = sys.argv[2]

files = {
    root / "web" / "wasm-worker.js": [
        (
            r'(\./vendor/micropython/micropython\.mjs\?v=)[^"]+',
            rf'\g<1>bridge-debug-{version}',
        ),
        (
            r'(const MICROPYTHON_WASM_VERSION = ")[^"]+(";\n)',
            rf'\g<1>bridge-debug-{version}\g<2>',
        ),
        (
            r'(const WORKER_BUILD_VERSION = ")[^"]+(";\n)',
            rf'\g<1>worker-debug-{version}\g<2>',
        ),
    ],
    root / "web" / "micropython-bridge.js": [
        (
            r'(const WORKER_SCRIPT_VERSION = ")[^"]+(";\n)',
            rf'\g<1>worker-debug-{version}\g<2>',
        ),
    ],
    root / "web" / "index.html": [
        (
            r'(\./micropython-bridge\.js\?v=)[^"]+',
            rf'\g<1>{version}',
        ),
    ],
}

for path, replacements in files.items():
    text = path.read_text(encoding="utf-8")
    original = text
    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text, count=1)
        if count != 1:
            raise SystemExit(f"Expected one replacement for {pattern!r} in {path}")
    if text != original:
        path.write_text(text, encoding="utf-8")
PY
}

require_cmd git
require_cmd python3
require_cmd make
require_cmd node
require_cmd cp

mkdir -p "$BUILD_ROOT"
mkdir -p "$OUTPUT_DIR"

ensure_checkout "$MICROPYTHON_REPO" "$MICROPYTHON_DIR" "$MICROPYTHON_REF"
ensure_checkout "$EMSDK_REPO" "$EMSDK_DIR" "$EMSDK_REF"

log "Installing and activating emsdk $EMSDK_VERSION"
"$EMSDK_DIR/emsdk" install "$EMSDK_VERSION"
"$EMSDK_DIR/emsdk" activate "$EMSDK_VERSION"

log "Updating required MicroPython submodule"
git -C "$MICROPYTHON_DIR" submodule update --init lib/micropython-lib

log "Installing trace build variant"
mkdir -p "$MICROPYTHON_DIR/ports/webassembly/variants/trace"
cp "$TRACE_VARIANT_DIR/mpconfigvariant.mk" "$MICROPYTHON_DIR/ports/webassembly/variants/trace/mpconfigvariant.mk"
cp "$TRACE_VARIANT_DIR/mpconfigvariant.h" "$MICROPYTHON_DIR/ports/webassembly/variants/trace/mpconfigvariant.h"

apply_patch_once "$MICROPYTHON_DIR" "$PATCH_FILE"

log "Building mpy-cross"
bash -lc "source \"$EMSDK_DIR/emsdk_env.sh\" >/dev/null && make -C \"$MICROPYTHON_DIR/mpy-cross\" -j$BUILD_JOBS"

log "Building webassembly trace variant"
bash -lc "source \"$EMSDK_DIR/emsdk_env.sh\" >/dev/null && make -C \"$MICROPYTHON_DIR/ports/webassembly\" VARIANT=trace -j$BUILD_JOBS"

log "Copying built artifacts into $OUTPUT_DIR"
cp "$MICROPYTHON_DIR/ports/webassembly/build-trace/micropython.mjs" "$OUTPUT_DIR/micropython.mjs"
cp "$MICROPYTHON_DIR/ports/webassembly/build-trace/micropython.wasm" "$OUTPUT_DIR/micropython.wasm"

log "Updating cache-busting version strings to $VERSION_TAG"
update_cache_versions

log "Verifying sys.settrace availability in vendored runtime"
node -e "import('file://$OUTPUT_DIR/micropython.mjs').then(async (mp_mjs) => { const mp = await mp_mjs.loadMicroPython({ url: 'file://$OUTPUT_DIR/micropython.wasm', stdout: console.log, stderr: console.error }); await mp.runPythonAsync('import sys\nprint(hasattr(sys, \"settrace\"))\n'); process.exit(0); }).catch((error) => { console.error(error); process.exit(1); });"

log "Done"
