# Super Ventilagon emulator assessment

Investigation: 2026-10-13, checkout `3b9f865`. The assessment below records
the original failures and measurements. The shared C replacement has since
been implemented; see [the adapter documentation](../../emulator/ventilagon/README.md).

## Recommendation

Reuse the original C as a shared game core for the rotor, desktop and web.
Keep the MicroPython scene wrapper, idle screens, launcher integration and
audio/control routing. Retire `ventilagon_emu.py` and its generated Python
data tables after the C adapters pass behavioral and rendering comparisons.

Repairing the Python port is possible, especially on desktop, but requires
more than matching individual C statements. The port loses the original
execution cadence, duplicates gameplay logic, and independently reconstructs
the display. On the shipped web interpreter, rendering alone exceeds the
current scene-frame budget. A shared C core addresses both execution cost and
the continuing maintenance of two implementations.

Merely compiling C and calling its loop once per scene frame would preserve
the slow controls. The simulation clock and display ownership need explicit
fixes whichever language is used.

## Confirmed causes

### Desktop: the normal display update clears the game frame

The sequence is:

1. `VentilagonGame.step()` calls the port's `tick()`, which sends `frame_rgb`.
2. `Director.step_once()` then calls the normal display `update()`.
3. `remotepov.update()` sends the legacy `sprites` table.
4. The desktop host's `dispatch_command()` handles `sprites` by calling
   `clear_voom_frame()`, immediately discarding the RGB framebuffer.

The gameplay scene has no enabled game sprites to replace that image. This
explains the blank gameplay display, or a fleeting frame depending on when
the rendering thread samples it. An isolated probe executed the actual
`remotepov.update()` and host dispatch function and reproduced both the
command ordering and the framebuffer being cleared.

The fix belongs in display infrastructure: give a scene an explicit raw-frame
presentation mode, send one authoritative presentation per update, and switch
back to sprites on exit. Removing `clear_voom_frame()` indiscriminately would
leave stale game frames over the launcher.

Relevant code: [scene wrapper](../../games/alecu/ventilagon_game/code/ventilagon_game.py),
[director](../../apps/micropython/ventilastation/director.py),
[desktop display](../../apps/micropython/ventilastation/remotepov.py),
[host dispatch](../../emulator/comms.py).

### Both emulators: simulation timing was translated incorrectly

Both the director and web worker normally advance scenes every 30 ms.
The rotor invokes `ventilagon_loop()` continuously on its display task.
Level 1 permits ship movement every `37500 / 32 = 1171` microseconds, but
the Python port performs at most one move per `tick()` and resets the move
timer to the current time. It discards the intervening movement opportunities.

On an empty, paused board, holding right for 0.99 simulated seconds produced:

| Update cadence | Python port | Original C with host shims |
| --- | ---: | ---: |
| 30 ms, the normal scene cadence | 165 subdegrees / 7.25° | Same cadence limitation would apply |
| 100 µs, controlled timing probe | 4125 subdegrees / 181.27° | 4125 subdegrees / 181.27° |
| 1 ms | 2475 subdegrees / 108.76° | Not used as the reference |

The normal-cadence port is **25 times slower** in this probe. The 1 ms result
also shows that simply picking a nominal 1 kHz loop does not reproduce the
original threshold behavior: its strict comparison quantizes movement into
2 ms intervals.

Other timers have the same one-event-per-call behavior: board scrolling,
drift, resetting and credits. Section duration still uses elapsed wall time,
so level changes and music can progress while movement/scrolling lag behind.
Drift selection is particularly problematic: `display_adjust_drift()` chooses
again every 1024 loop calls, which becomes about 30.72 seconds at 33⅓ Hz.
Its hardware cadence depends on actual display-task throughput.

A replacement must separate simulation from presentation, preserve collision
checks between movement/board events, and specify elapsed-time behavior.
Hardware drift cadence should be measured before changing it. The 100 µs
probe is a controlled comparison, not a measurement of the physical rotor's
loop frequency.

Relevant code: the former `ventilagon_emu.py` Python port,
[C play loop](../../hardware/rotor/modules/povdisplay/ventilagon/state_play.c),
[C display](../../hardware/rotor/modules/povdisplay/ventilagon/display.c),
[rotor task](../../hardware/rotor/modules/povdisplay/povdisplay.c),
[web worker](../../web/wasm-worker.js).

### Web: full-frame Python rendering exceeds the frame budget

Measured locally on macOS x86_64 with Node v25.6.1 and the **shipped**
MicroPython/WASM interpreter and actual worker. The worker loaded the runtime
bundle, entered `VentilagonGame` through its idle scene, and emitted a valid
41,472-byte RGB frame. The native probe used `clang -O2`; the C/WASM probe
used Emscripten 5.0.1 `-O2`.

| Work measured | Desktop MicroPython | Shipped MicroPython/WASM | C desktop | C/WASM |
| --- | ---: | ---: | ---: | ---: |
| Full gameplay RGB frame | 0.50 ms | 76.3 ms | 0.012 ms | 0.034 ms |
| Simulation plus one frame | 0.57 ms at 1 kHz | 184.8 ms at 1 kHz | 0.041 ms at 10 kHz | 0.053 ms at 10 kHz |

The simulation rows deliberately use different cadences and are not a
matched-work speedup claim. They demonstrate the available C headroom.
The full-frame C helper reuses `board_draw_column()` and `display_ship_rows()`
but simplifies physical coordinates; it is a throughput probe, not a finished
hardware-faithful renderer.

Actual worker/director steps, including scene work and pointer-based frame
posting, averaged **99.9 ms and 120.6 ms** over two batches of 20 frames.
Post-GC heap usage was unchanged at **1,867,680 bytes** after those batches.
There is no evidence of a growing heap in this short run. The current bridge
already sends this payload as pointer + length.

These are local Node measurements, not a browser/GPU benchmark. Python frame
benchmarks used 10 frames; desktop used 1000 and C rendering used 10,000.
Browser drawing, real audio and device performance remain unmeasured. Even
with those limits, 76.3 ms for Python rendering alone cannot meet the current
30 ms scene budget on the tested machine.

## Additional parity gaps

- In calibration/game-over mode, C returns a boolean from
  `display_ship_rows()` and paints one red row. Python returns two rows.
  A fixed-board comparison found 86 differing RGB bytes from this alone.
- C's DMA layout places the 48 board rows at a six-LED offset within the
  54-LED arm and handles opposed arms. Python puts rows at LEDs 0–47 and
  leaves the outer six black. Physical radial/angular mapping needs validation
  against a workbench capture.
- C credits use the upper-half/two-arm mapping in `text_loop2()`. Python
  paints text across all 256 angles. Text wrapping and string-length treatment
  also differ.
- Python creates a fresh `Game` on entry; C retains several globals and static
  counters. Re-entry semantics need an explicit test.
- A shared C implementation does not automatically produce identical random
  sequences across ESP32, desktop libc and WASM libc. Use a specified shared
  PRNG or injected random values if deterministic cross-platform replay is
  required.

The five existing `test_ventilagon_parity.py` checks all pass. They validate
table structure, transformations, one collision example and a gameplay smoke
run. They do not compare against a running C reference, assert movement speed,
test presentation ownership, or compare complete rendered frames.

## Implementation choice

| Approach | Benefit | Cost and limitation |
| --- | --- | --- |
| Repair the Python port | Smallest initial desktop fix; editable gameplay in the web IDE | Must repair timers, optimize/cache rendering, reproduce physical output, and maintain duplicate logic |
| Shared C core with host adapters | One gameplay implementation; large measured performance margin; original tables and helpers reused | Requires portable clock/input/output interfaces, builds and packaging, plus real parity tests |

The feasibility probe compiled **all 16 C files listed in the firmware's
`micropython.cmake`, unchanged**, into both a desktop shared library and a
standalone WASM module. Small shims supplied the ESP timer, FreeRTOS queues,
critical sections and SPI functions. The WASM binary was 10,916 bytes in this
probe. Desktop MicroPython v1.25.0 successfully called the library via `ffi`.

For production, replace the test shims with narrow platform interfaces and
share the actual core sources rather than copying them into emulator folders.
Keep hardware's native `ventilagon` API. Desktop can expose the same API through
a user C module, or a shared-library wrapper. The `ffi` experiment proves the
local Unix route; Linux and the bundled Windows interpreter were not tested.
A CPython-host `ctypes` adapter is another packaging route if retaining stock
desktop MicroPython is a priority.

On web, a separate WASM module inside the existing worker avoids having to
rebuild the MicroPython interpreter for each game-core change. Thin scene/host
calls can preserve `enter`, `exit`, `received`, `sending`, `is_idle` and `tick`.
Frame bytes should come directly from C/WASM memory to the existing RGB
renderer, with explicit buffer ownership across worker transfers. Audio stays
as commands consumed by the emulator/base; it does not move onto the rotor.

This should remain a normal launcher scene. Ventilagon already runs as linked
C on the rotor; it does not need a Retro-Go partition handoff.

## Migration and acceptance

1. Fix explicit raw-frame presentation ownership and test exit back to the
   launcher on both hosts.
2. Establish hardware timing and frame captures as the reference, including
   ship speed, scrolling, drift and credits.
3. Extract the shared C/platform boundary and add an elapsed-time simulation
   interface. Rendering cadence must not determine gameplay speed.
4. Add desktop and worker adapters and package reproducible native/WASM builds.
5. Compare seeded/injected-input traces at multiple presentation rates,
   including slow frames, collisions, restart, all sections, credits, win and
   audio/control commands. Check physical mapping against captured frames.
6. Verify browser frame time and post-GC heap stability over sustained play
   and repeated scene entry/exit. Only then remove the Python simulation and
   generated Python tables; retain the scene wrapper and shared assets.

Validation performed for this assessment: existing Ventilagon tests (5),
browser input tests (2), host protocol tests (4), web renderer parity tests,
native and WASM compilation, desktop FFI loading, worker startup/presentation,
timing probes, and the short heap check above. Firmware and physical hardware
were not exercised during the initial investigation. The subsequent implementation
removes the Python simulation and tests frames against the original C SPI output.
