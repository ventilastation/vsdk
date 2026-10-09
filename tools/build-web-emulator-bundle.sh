#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-"$ROOT_DIR/dist/emulator"}"
PYTHON="${PYTHON:-$(if [ -x "$ROOT_DIR/.venv/bin/python" ]; then echo "$ROOT_DIR/.venv/bin/python"; else echo python3; fi)}"

# A publish rebuilds every sprite ROM from scratch rather than trusting the
# incremental check, then the runtime manifest and bundle that embed them.
rm -f "$ROOT_DIR"/apps/micropython/roms/*.rom
"$PYTHON" "$ROOT_DIR/tools/generate_web_runtime_bundle.py" --force

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

"$PYTHON" "$ROOT_DIR/tools/stamp_web_versions.py" "$OUT_DIR"

printf 'Built web emulator bundle at %s\n' "$OUT_DIR"
