#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-"$ROOT_DIR/dist/emulator"}"

python3 "$ROOT_DIR/tools/generate_web_runtime_bundle.py"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

# web/ holds symlinks (apps, games, system) so the dev server can reach the
# asset trees; replace them with real copies so the published output is
# self-contained.
cp -R "$ROOT_DIR/web/." "$OUT_DIR/"
for tree in apps games system; do
    rm -f "$OUT_DIR/$tree"
    cp -R "$ROOT_DIR/$tree" "$OUT_DIR/$tree"
done

printf 'Built web emulator bundle at %s\n' "$OUT_DIR"
