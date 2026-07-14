# Architecture Notes

This document captures the parts of the web emulator architecture that matter when debugging rendering, bridge behavior, and MicroPython memory usage.

## Source Tree

The editable web emulator source of truth lives in:

- `vsdk/web`

Within that tree, `vsdk/web/apps` is a symlink to:

- `vsdk/apps`

The worker-hosted runtime bundle also includes Python files from:

- `vsdk/games`
- `vsdk/system`

The top-level `emulator/` directory is only the published copy used by the Jekyll site.

When reading the rest of this document, prefer the matching path under `vsdk/web/...`; the `emulator/...` copy should be treated as deployment output.

## Native App Handoff

The current runtime is MicroPython-first:

1. MicroPython boots from `apps/micropython/main.py`
2. the launcher loads app slugs through `ventilastation.app_loader`
3. Python apps return `Scene` objects that run inside the `director`

To support heavyweight native apps such as `voom`, the launcher now also has a native-app registry in
`apps/micropython/ventilastation/native_apps.py`.

On hardware, the preferred launch path is a direct native launcher hook exposed by the
MicroPython firmware itself. This matches the current rotor build, which is a single
MicroPython firmware image with linked user C modules under `hardware/rotor/modules/...`.

At the moment, that native hook is implemented as a practical bridge to the existing Voom
firmware fork, which builds Doom as the `prboom-go` app partition in a Retro-Go image.

That means the current hardware flow for `voom` is:

- MicroPython launcher selects `native.voom`
- Python asks the hardware platform to launch a native app hook
- the hook switches boot partition to `prboom-go`
- the ESP32 restarts into the flashed Voom firmware

The current combined-image layout for this handoff is defined in:

- `hardware/rotor/partitions-ventilastation.csv`

and built by:

- `hardware/rotor/build_voom_image.py`

That image keeps:

- MicroPython in the `factory` app partition
- Voom in the `prboom-go` app partition
- `otadata` present so `esp_ota_set_boot_partition()` can switch between them

The combined builder intentionally supports different ESP-IDF trees for each side:

- `vsdk` / MicroPython can stay on `esp-idf-5.4`
- `voom` / Retro-Go can be built with another installed SDK such as `esp-idf` (`v5.0.4`)

The intended longer-term steady-state flow is still possible:

- the native runtime takes over display/input/audio timing directly without rebooting
- on exit, native code returns to the launcher or resets back into MicroPython

The registry also defines a boot-intent fallback:

- the launcher persists intent in `ventilastation/boot.json`
- a future native boot shim can read that intent before entering MicroPython
- native apps are expected to clear or replace that intent before returning to the launcher

At the moment the Python-side registry, intent persistence, and a hardware native launcher hook
exist. Platforms without that hook still save boot intent and then fail loudly because they cannot
honor it.

## Web Emulator Overview

The browser-based emulator is split into four main layers:

1. `vsdk/web/app.js`
   - Main browser UI and renderer host.
   - Receives streamed frame updates from the worker.
   - Shows diagnostics, heap information, and debug controls.

2. `vsdk/web/micropython-bridge.js`
   - Thin browser-to-worker RPC bridge.
   - Creates the module worker and forwards commands.

3. `vsdk/web/wasm-worker.js`
   - Runs the MicroPython WASM runtime in a worker.
   - Mounts the runtime filesystem from `runtime-bundle.json`.
   - Registers the `__vs_host` JS module that MicroPython calls into.
   - Streams frame events back to the browser thread.

4. `vsdk/web/apps/micropython/ventilastation/...`
   - MicroPython-side emulator code.
   - `platforms/__init__.py` contains the browser display/comms implementation used by the WASM runtime.
   - app boot and scene loading then continue into `games/...` and `system/...` as needed.

## Browser Input Flow

`app.js` uses the standard browser Gamepad API (`navigator.getGamepads()`) and
sends the same three v2 fields used by the desktop emulator: `joy1`, `joy2`,
and `extra`. The WASM worker stores those fields as primitive values exposed
through `__vs_host`; `BrowserComms` reads them without allocating per-frame
input objects.

- One controller: left stick/D-pad is Joy1; right stick is Joy2; its shoulder
  and trigger controls are Joy2 A/B/X/Y.
- Two controllers: controller 2's left stick/D-pad plus face, Start, and Back
  controls are Joy2; controller 1's right stick is ignored.
- Guide/Home (or Escape) is latched as one `exit` command, which the Director
  handles by returning to the MicroPython launcher scene.

## Frame Flow

Normal rendering now works like this:

1. MicroPython scene code updates sprite state and display state.
2. `BrowserDisplay.update()` in `vsdk/web/apps/micropython/ventilastation/platforms/__init__.py` prepares:
   - sprite bytes from `self.sprite_data`
   - frame metadata from `self._frame_meta`
3. If available, MicroPython posts both through the worker host using pointer-based calls:
   - `post_present_ptr(sprite_ptr, sprite_len, frame_ptr, frame_len)`
4. `vsdk/web/wasm-worker.js` reads the pointed-to bytes from WASM memory and converts them into browser `Uint8Array` payloads.
5. The worker reconstructs the streamed frame and emits it to `app.js`.
6. `app.js` renders the frame with WebGL or the 2D fallback renderer.

Palette and imagestrip data still travel as explicit commands when needed, but sprite/frame transport now prefers the pointer-based route.

## Command Flow

Generic emulator commands also cross the bridge.

Examples include:

- `sound ...`
- `music ...`
- `notes ...`
- `palette ...`
- `imagestrip ...`
- `traceback ...`

Those commands are emitted from MicroPython through `BrowserComms.send()` in
`vsdk/web/apps/micropython/ventilastation/platforms/__init__.py`.

The important change is that `post_command(...)` is now also pointer-first:

1. MicroPython keeps the command line and payload in MicroPython-managed memory
2. it calls `post_command_ptr(line_ptr, line_len, data_ptr, data_len)` when available
3. `vsdk/web/wasm-worker.js` reads both buffers directly from WASM memory
4. the worker reconstructs the command on the JS side

This matters because command traffic turned out to be another leak surface, especially for frequently repeated commands such as menu navigation sounds.

## Why Pointer Posting Matters

The original bridge path passed Python-owned byte payloads directly from MicroPython to JS on every frame.

That included:

- sprite payloads
- frame metadata payloads
- generic command payloads

In practice, that path caused steady growth in the MicroPython heap in the WASM build, even while idling on the menu. The leak did not reproduce the same way on ESP32 hardware, which pointed to the browser bridge rather than game logic.

The working fix was to stop using Python byte objects as the primary bridge payload and instead:

1. keep command/frame data in MicroPython-managed buffers
2. pass only pointer + length to the worker host
3. let the worker read the bytes directly from WASM memory

This made the MicroPython heap remain steady during idle rendering and removed a larger leak that showed up while exiting games.

## Current Memory Rule

For high-frequency frame transport between MicroPython and JS:

- prefer pointer + length
- avoid creating fresh Python `bytes` or `bytearray` payloads just to cross the bridge

The same rule applies to generic commands:

- prefer pointer-based transport whenever command payloads cross from MicroPython into JS
- treat direct object bridging as fallback compatibility only, not the normal path

## Useful Files

- `vsdk/web/apps/micropython/ventilastation/platforms/__init__.py`
  - browser display/comms implementation
  - pointer-based present/frame posting
  - pointer-based generic command posting
- `vsdk/web/wasm-worker.js`
  - worker host methods
  - pointer reads from WASM memory
- `vsdk/web/vendor/micropython/micropython.mjs`
  - MicroPython JS runtime wrapper
  - helper used by worker to read memory bytes
- `vsdk/web/app.js`
  - heap diagnostics UI
  - streamed frame consumer
- `DEPLOY.md`
  - bundle refresh and cache-busting workflow

## Manual Regression Check

When changing the bridge or display update code:

1. run the emulator
2. leave it idling on the menu for 30-60 seconds
3. click `Collect heap`
4. wait again and click `Collect heap` again
5. verify `Heap Used` stays roughly steady

If heap growth returns while the menu is idle, suspect the MicroPython-to-JS bridge before suspecting game logic.

A useful follow-up check is:

1. enable `Collect after every frame`
2. press menu `UP`/`DOWN` repeatedly
3. verify the post-collect heap no longer ratchets upward due to sound/command traffic

## Refresh Caveat

Python-side emulator changes do not take effect in the browser until `vsdk/web/runtime-bundle.json` is refreshed and `vsdk/web` is published into `emulator/`.

Worker-side JS changes may also appear stale unless the worker cache-busting version is bumped.

See `DEPLOY.md` for the exact refresh steps.
