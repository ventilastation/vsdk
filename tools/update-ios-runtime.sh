#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VSDK_DIR="${1:-"$ROOT_DIR"}"
OUT_DIR="${2:-"$ROOT_DIR/dist/emulator"}"

if [[ ! -d "$VSDK_DIR/web" || ! -d "$VSDK_DIR/apps" ]]; then
  echo "Expected a vsdk checkout at $VSDK_DIR" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
# web/apps, web/games and web/system are dev-serving symlinks into the vsdk
# checkout; skip them here, the rsyncs below publish the real trees instead
rsync -a --delete --exclude 'apps' --exclude 'games' --exclude 'system' --exclude '__pycache__/' "$VSDK_DIR/web"/ "$OUT_DIR"/
rsync -a --delete --exclude '__pycache__/' "$VSDK_DIR/apps"/ "$OUT_DIR/apps"/
rsync -a --delete --prune-empty-dirs \
  --include '*/' \
  --include 'code/***' \
  --include 'images/***' \
  --include 'sounds/***' \
  --include 'meta.json' \
  --include 'menu.png' \
  --exclude '*' \
  "$VSDK_DIR/games"/ "$OUT_DIR/games"/
rsync -a --delete --prune-empty-dirs \
  --delete-excluded \
  --exclude 'voom/' \
  --include '*/' \
  --include 'code/***' \
  --include 'images/***' \
  --include 'sounds/***' \
  --include 'meta.json' \
  --exclude '*' \
  "$VSDK_DIR/system"/ "$OUT_DIR/system"/

find "$OUT_DIR/games" "$OUT_DIR/system" -type f \( -name '__images__.yaml.txt' -o -name '__images__.yml.txt' -o -name 'images-manifest.yaml.txt' -o -name 'images-manifest.yml.txt' \) -delete 2>/dev/null || true
while IFS= read -r -d '' manifest; do
  manifest_dir="$(dirname "$manifest")"
  manifest_name="$(basename "$manifest")"
  case "$manifest_name" in
    __images__.yaml)
      cp "$manifest" "$manifest_dir/images-manifest.yaml.txt"
      ;;
    __images__.yml)
      cp "$manifest" "$manifest_dir/images-manifest.yml.txt"
      ;;
  esac
done < <(find "$OUT_DIR/games" "$OUT_DIR/system" -type f \( -name '__images__.yaml' -o -name '__images__.yml' \) -print0 2>/dev/null)

# Keep the hardware acceptance app available only in the launcher's hidden
# system menu. The launcher source is generated from the vsdk checkout, so
# apply this small native-emulator overlay after each publish refresh.
if [[ "$OUT_DIR" == "$ROOT_DIR/dist/emulator" ]] && [[ -f "$OUT_DIR/system/launcher/code/__init__.py" ]] &&
   ! grep -q '"vs2_hardware"' "$OUT_DIR/system/launcher/code/__init__.py"; then
  patch -p0 < "$ROOT_DIR/tools/ios-system-menu.patch" >/dev/null
fi

printf 'Updated emulator publish tree at %s from %s/web + %s/apps + source assets\n' "$OUT_DIR" "$VSDK_DIR" "$VSDK_DIR"
