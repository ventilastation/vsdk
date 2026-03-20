#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-"$ROOT_DIR/dist/emulator"}"

python3 "$ROOT_DIR/tools/generate_web_runtime_bundle.py"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

cp -R "$ROOT_DIR/web/." "$OUT_DIR/"
rm -f "$OUT_DIR/apps"
cp -R "$ROOT_DIR/apps" "$OUT_DIR/apps"

printf 'Built web emulator bundle at %s\n' "$OUT_DIR"
