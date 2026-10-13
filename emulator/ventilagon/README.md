# Native Super Ventilagon emulator

Desktop and browser emulators compile the **original rotor C sources** listed
in `hardware/rotor/modules/povdisplay/micropython.cmake`. `host.c` supplies a
virtual timer, synchronous queues, SPI stubs and a full RGB frame adapter. It
reuses the original board, ship, font, state, level and pattern functions.
There is no separate Python simulation or extracted copy of the data tables.

The MicroPython game scene and idle screens stay in
`games/alecu/ventilagon_game/code/ventilagon_game.py`. Hardware continues using
its built-in `ventilagon` module and continuous display task. In emulators,
`ventilastation.ventilagon_host` is a small scene-to-host adapter.

## Desktop

The CPython emulator loads a shared library through `ctypes`. This works with
the stock MicroPython interpreter; no custom interpreter or MicroPython FFI
support is required. The library is built on first native launch when missing
or older than its sources. To build it ahead of time:

```sh
make ventilagon-native
# or: python3 tools/build_ventilagon.py
```

A C compiler (`cc`/`clang`, or `CC` specifying a compiler command) must be
available, or the platform library must be supplied in this directory:
`libventilagon.dylib` on macOS, `libventilagon.so` on Linux, `ventilagon.dll`
on Windows. These platform binaries are ignored build output. Windows
packaging can include the DLL beside the emulator, just as it includes the
MicroPython executable. The named-pipe transport now uses the same v2 input
and status parser as the TCP transport.

MicroPython sends small `ventilagon enter <seed>`, `ventilagon tick <us>
<buttons>` and `ventilagon exit` commands. The receive thread runs C, publishes
an immutable RGB frame to the renderer, and routes C's audio/base commands
through the normal dispatcher. `ventilagon_idle 0|1` returns over the input
link; the parser handles it without putting it in the control-command queue.
Pixels never cross the desktop MicroPython connection.
Idle status is repeated on presentation so reconnecting the input link does
not lose the game's current idle state.
Native failures return `ventilagon_error` and become regular scene exceptions;
the host also preserves the full native-loading/execution traceback.

## Browser

The worker loads `web/vendor/ventilagon/ventilagon.mjs` and its sibling WASM
binary through `web/ventilagon-native.js`. Build them with Emscripten on PATH:

```sh
make ventilagon-wasm
# or: python3 tools/build_ventilagon.py --wasm
```

`EMCC` can specify the compiler command. The web vendor pair is shipped in
Git so running the web emulator does not require a compiler. Publishing checks
and rebuilds it when the C sources change. After editing the core during local
web development, run the build target before reloading. Sprite ROMs and the
runtime JSON bundle keep their usual generated-output lifecycle.

MicroPython calls worker functions with primitive time/input values. The
worker copies RGB bytes directly from **native WASM memory**, drains audio/base
commands, and queues one frame event. No Python bytes object carries pixels
across the MicroPython/JS bridge.

## Timing, frame ownership and parity

Both emulator hosts run a fixed **100 µs** simulation step and accumulate the
fractional remainder across presentations. Movement, collisions, scrolling,
sections and credits use the original C loops on that clock, independent of
whether the UI presents at 10, 33, 60 or 144 Hz. Catch-up is capped at 250 ms per
presentation so resuming a suspended tab pauses rather than replaying minutes
of stale input.

The virtual rotor runs at 600 RPM. The full-frame adapter preserves the
original integer phase/drift conversion, opposed-arm orientation, six-LED hub
gap, game-over marker and upper-half/outer-ring credits layout. Frozen frames
are compared byte-for-byte against SPI output from the original C display
functions, including several nonzero drift positions and all five states.
The emulator does not send synthetic SPI output to hardware.

The original firmware chooses drift every 1024 busy-loop calls; that physical
cadence has not been measured here. Emulator drift therefore uses the explicit
100 µs virtual-loop cadence. Dynamic parity with a physical rotor still needs
a workbench timing check. Do not change hardware cadence to match this adapter
without measuring it.

Host builds replace libc `rand()` with one specified 32-bit LCG, seeded on
entry, so desktop and WASM replays match. Rotor RNG behavior stays unchanged;
the random choices use the same original pools and transforms, but a host seed
does not promise the identical random sequence on firmware.

A gameplay scene declares `raw_frame = True`. Desktop display updates suppress
legacy sprite packets while that scene owns presentation; browser updates post
frame metadata without a sprite table. On exit, the next normal scene resumes
sprite presentation and clears the native frame. Audio remains on the base or
emulator host, as on hardware.

## Validation

```sh
python3 tests/test_ventilagon_parity.py
python3 tests/test_ventilagon_host.py
python3 tools/generate_web_runtime_bundle.py
node tests/test_ventilagon_wasm.mjs
node tests/test_ventilagon_wasm.mjs --soak
```

The native tests cover input speed across frame rates, collisions within slow
frames, reset/restart/exit, seeded re-entry, section/credits/win durations and
original SPI frame mapping. The production WASM replay must match native
frame hashes and audio/control events. The real worker test exercises the
actual MicroPython scene, 2,000 frames, repeated entry/exit and post-GC heap
stability. `--soak` adds two 30-second idle windows with heap collections.

On the implementation machine, the full worker path measured **0.5–0.9 ms
per step**, compared with 100–120 ms for the removed Python simulation. These
are local Node/worker measurements, excluding browser/GPU drawing. The
existing render-parity suite still checks the shared RGB display path.
