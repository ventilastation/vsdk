#!/bin/sh
# Run the desktop emulator (it brings the sprite ROMs up to date itself).
set -e
cd "$(dirname "$0")"
[ -f .venv/bin/activate ] && . .venv/bin/activate
(cd emulator/native && ./build.sh)
cd emulator
exec python emu.py "$@"
