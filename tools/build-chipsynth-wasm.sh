#!/usr/bin/env bash
#
# Builds the browser-side chip-audio synthesizers used by
# web/chip-audio-host.js to regenerate NES/SMS/MSX sound-chip audio from the
# register writes the physical board streams over the remote-workbench link
# (see docs/internals/emulator-audio.md). Each output is a small standalone
# Emscripten module compiled from the *same* unmodified device/host chip
# sources as emulator/chipsynth (the desktop pyglet host's native build) --
# only the compiler and output format differ.
#
# Mirrors tools/build-micropython-webassembly.sh's emsdk bootstrap so both
# WASM builds share the same pattern (and can share an emsdk checkout by
# pointing EMSDK_DIR at the same directory).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_ROOT="${BUILD_ROOT:-/tmp/vsdk-chipsynth-wasm}"
EMSDK_DIR="${EMSDK_DIR:-$BUILD_ROOT/emsdk}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/web/vendor/chipsynth}"
EMSDK_REPO="${EMSDK_REPO:-https://github.com/emscripten-core/emsdk.git}"
# Same pin as tools/build-micropython-webassembly.sh, so a dev who already
# built the MicroPython WASM runtime can point EMSDK_DIR at that checkout
# and skip a second multi-hundred-MB toolchain download.
EMSDK_REF="${EMSDK_REF:-d223ae73c6998296e3ab27cf81dc2c2c9fd383de}"
EMSDK_VERSION="${EMSDK_VERSION:-6.0.0}"

CHIPSYNTH_DIR="$ROOT_DIR/emulator/chipsynth"
RETROGO="$ROOT_DIR/apps/retro-go"
RG_COMP="$RETROGO/components/retro-go"

log() {
  printf '[build-chipsynth-wasm] %s\n' "$*"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'Missing required command: %s\n' "$1" >&2
    exit 1
  }
}

require_cmd git
require_cmd python3

mkdir -p "$BUILD_ROOT"
mkdir -p "$OUTPUT_DIR"

if [[ ! -d "$EMSDK_DIR/.git" ]]; then
  log "Cloning emsdk into $EMSDK_DIR"
  git clone "$EMSDK_REPO" "$EMSDK_DIR"
fi
git -C "$EMSDK_DIR" fetch origin
git -C "$EMSDK_DIR" checkout "$EMSDK_REF"

log "Installing and activating emsdk $EMSDK_VERSION"
"$EMSDK_DIR/emsdk" install "$EMSDK_VERSION"
"$EMSDK_DIR/emsdk" activate "$EMSDK_VERSION"

log "Sourcing emsdk environment"
# shellcheck disable=SC1091
source "$EMSDK_DIR/emsdk_env.sh" >/dev/null
require_cmd emcc

# Common flags. -O2 keeps parity with the native build's optimization level.
# The vendored cores rely on the same char/pointer leniency the native
# Makefile already tolerates (see emulator/chipsynth/Makefile), so quiet the
# same warnings rather than patch shared vendored code.
COMMON_FLAGS=(
  -O2
  -Wno-incompatible-pointer-types
  -Wno-implicit-function-declaration
  -sMODULARIZE=1
  -sEXPORT_ES6=1
  -sALLOW_MEMORY_GROWTH=1
  -sENVIRONMENT=web
  # HEAP16 must be listed explicitly: since Emscripten ~3.1.44, MODULARIZE
  # builds no longer attach the heap typed-array views to the returned
  # Module object unless exported here (this bit us once already --
  # chip-audio-host.js's frame() reads Module.HEAP16 to pull rendered PCM
  # back out of WASM memory).
  "-sEXPORTED_RUNTIME_METHODS=['cwrap','HEAP16']"
)

# build_module <name> <export-name> <exported-functions-csv> <include-dir>... -- <source-file>...
build_module() {
  local name="$1" export_name="$2" exported_functions="$3"
  shift 3
  local includes=()
  while [[ "$1" != "--" ]]; do
    includes+=("$1")
    shift
  done
  shift # drop the "--" separator
  local sources=("$@")

  log "Building $name-synth.wasm"
  emcc "${COMMON_FLAGS[@]}" \
    -sEXPORT_NAME="$export_name" \
    -sEXPORTED_FUNCTIONS="$exported_functions" \
    "${includes[@]}" \
    -o "$OUTPUT_DIR/$name-synth.mjs" \
    "${sources[@]}"
}

# --- NES (nofrendo apu.c) ---
build_module nes createNesSynth \
  "['_nes_synth_reset_ntsc','_nes_synth_reset_pal','_nes_synth_render','_nes_synth_load_rom','_malloc','_free']" \
  -I"$CHIPSYNTH_DIR" \
  -I"$RETROGO/retro-core/components/nofrendo" \
  -I"$RETROGO/retro-core/components/nofrendo/nes" \
  -I"$RG_COMP" \
  -- \
  "$CHIPSYNTH_DIR/host_nes.c" \
  "$RETROGO/retro-core/components/nofrendo/nes/apu.c"

# --- SMS/Game Gear (smsplus sn76489.c) ---
build_module sms createSmsSynth \
  "['_sms_synth_reset_ntsc','_sms_synth_reset_pal','_sms_synth_render','_malloc','_free']" \
  -I"$CHIPSYNTH_DIR" \
  -I"$RETROGO/retro-core/components/smsplus" \
  -I"$RETROGO/retro-core/components/smsplus/cpu" \
  -I"$RETROGO/retro-core/components/smsplus/sound" \
  -I"$RG_COMP" \
  -- \
  "$CHIPSYNTH_DIR/host_sms.c" \
  "$RETROGO/retro-core/components/smsplus/sound/sn76489.c"

# --- MSX (fMSX AY8910.c + Sound.c) ---
build_module msx createMsxSynth \
  "['_msx_synth_reset','_msx_synth_render','_malloc','_free']" \
  -I"$CHIPSYNTH_DIR" \
  -I"$RETROGO/fmsx/components/fmsx/src/EMULib" \
  -I"$RG_COMP" \
  -- \
  "$CHIPSYNTH_DIR/host_msx.c" \
  "$RETROGO/fmsx/components/fmsx/src/EMULib/AY8910.c" \
  "$RETROGO/fmsx/components/fmsx/src/EMULib/Sound.c"

log "Done. Output in $OUTPUT_DIR"
