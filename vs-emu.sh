#!/bin/sh
# Regenerate ROM assets and run the desktop emulator.
set -e
cd "$(dirname "$0")"
[ -f .venv/bin/activate ] && . .venv/bin/activate
(cd tools && python generate_roms.py)
(cd emulator/native && ./build.sh)
cd emulator
exec python emu.py "$@"
