#!/bin/sh
# Builds libvs2render.so: the real hardware VS2/sprite renderer (gpu.c,
# the same code tests/native/test_render_vs2.c exercises) wrapped for the
# desktop emulator via ctypes (see ../native_render.py). Skips quietly if no
# C compiler is on PATH -- native_render.py falls back to the pure-Python
# renderer in povrender.py when the library isn't present.
set -e
cd "$(dirname "$0")"

OUT=libvs2render.so
SOURCES="
../../hardware/rotor/modules/povdisplay/gpu.c
../../hardware/rotor/modules/povdisplay/color_pipeline.c
vs2_wire.c
emu_bridge.c
"

CC=$(command -v cc || command -v gcc || command -v clang || true)
if [ -z "$CC" ]; then
    echo "vs2render: no C compiler on PATH, skipping native renderer build (falling back to Python)"
    exit 0
fi

need_rebuild=0
if [ ! -f "$OUT" ]; then
    need_rebuild=1
else
    for src in $SOURCES vs2_wire.h ../../hardware/rotor/modules/povdisplay/gpu.h; do
        if [ "$src" -nt "$OUT" ]; then
            need_rebuild=1
        fi
    done
fi

if [ "$need_rebuild" = "0" ]; then
    exit 0
fi

"$CC" -std=c11 -Wall -fPIC -shared \
    -I ../../tests/native/stubs \
    -I ../../hardware/rotor/modules/povdisplay \
    -I . \
    -o "$OUT" \
    $SOURCES \
    -lm
echo "vs2render: built $OUT"
