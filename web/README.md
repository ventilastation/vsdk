# Browser Host Scaffold

This directory is a minimal static shell for the future WASM runtime.

It currently provides:

- event-driven keyboard input mapped to the Ventilastation button bitmask
- Gamepad API input mapped to the same button bitmask, using the first connected controller
- a pull-based frame polling loop
- a debug canvas that renders exported sprite state
- inspector panels for runtime events, sprites, and assets
- a WASM adapter layer that auto-activates if a low-level bridge is provided
- a worker-bridge scaffold for integrating the official MicroPython `webassembly` port
- a browser-usable ROM builder for `stripedefs.yaml` asset folders
- a runtime workspace API for browser IDE integration

## Browser Workspace API

The emulator now exposes `window.VentilastationWebEmulator` for browser-side IDEs and parent shells.

That API provides:

- `listProjectFiles(path = ".")`
- `readProjectFile(path, encoding = "utf8")`
- `writeProjectFile(path, content, encoding = "utf8")`
- `deleteProjectFile(path)`
- `applyProjectSnapshot(files)`
- `restartRuntime({ full = true })`

This lets an embedded editor write files directly into the worker-hosted MicroPython filesystem and restart the runtime without rebuilding `runtime-bundle.json` on every save.

The first built-in IDE panel uses Monaco and lazy-loads it from jsDelivr at runtime, so that editor surface currently depends on normal browser network access.

For the intended GitHub and web-IDE flow, see:

- `vsdk/docs/web-ide-integration.md`

## Run

Serve the repository root or the `web/` directory with any static HTTP server.

Example:

```bash
cd /Users/alecu/ventilastation/vsdk
python3 -m http.server 8000
```

Then open `http://localhost:8000/web/`.

For a direct worker/bootstrap check, open:

`http://localhost:8000/web/smoke-test.html`

## ROM Builder

Two browser-friendly scripts are now available:

- `web/rom-builder-core.js`
- `web/rom-builder-browser.js`

Load them in that order, then generate a ROM from an asset folder:

```html
<script src="/web/rom-builder-core.js"></script>
<script src="/web/rom-builder-browser.js"></script>
<script>
  const rom = await window.VentilastationBrowserRomBuilder.buildRomFromFolder(
    "/apps/images/ventap/"
  );
  console.log("ROM bytes", rom.length);
</script>
```

The same shared core is also used by a tiny Node CLI:

```bash
cd vsdk
npm install
node tools/generate_roms_js.cjs
```

Or generate a single folder:

```bash
node tools/generate_roms_js.cjs apps/images/ventap
```

## Expected Runtime Adapter

The page looks for `window.VentilastationRuntimeAdapter`.

If that is not present, it tries to create one through `window.createVentilastationWasmAdapter()`.

That adapter should expose:

```js
{
  name: "MicroPython WASM",
  setButtons(bitmask) {},
  exportFrame({ full }) {
    return {
      frame: 1,
      buttons: 0,
      column_offset: 0,
      gamma_mode: 1,
      palette: Uint8Array | undefined,
      assets: [
        {
          slot: 3,
          width: 4,
          height: 6,
          frames: 1,
          palette: 0,
          data: Uint8Array
        }
      ],
      events: [
        {
          command: "sound",
          args: ["demo/sfx"]
        }
      ],
      sprites: [
        {
          slot: 1,
          image_strip: 3,
          x: 12,
          y: 34,
          frame: 0,
          perspective: 2
        }
      ]
    };
  }
}
```

The adapter scaffold in `web/wasm-adapter.js` expects one of:

- `window.VentilastationWasmBridge`
- `window.createVentilastationWasmBridge()`

That bridge must expose:

```js
{
  async initialize() {},
  async exec(code) {},
  call(moduleName, functionName, ...args) {}
}
```

This repository now also includes a default scaffold implementation:

- [web/micropython-bridge.js](/Users/alecu/ventilastation/vsdk/web/micropython-bridge.js)
- [web/wasm-worker.js](/Users/alecu/ventilastation/vsdk/web/wasm-worker.js)

Today those files provide the transport layer. They do not include the actual MicroPython artifacts yet.

The high-level adapter already translates that into:

- `ventilastation.browser.set_buttons(...)`
- `ventilastation.browser.export_frame(...)`
- optionally `ventilastation.browser.export_storage(...)`

## Smoke Test

The smoke test page:

- creates the worker bridge
- initializes the MicroPython webassembly runtime
- runs `configure_runtime("browser")`
- imports `main`
- calls `ventilastation.browser.export_frame(True)`

Files:

- [web/smoke-test.html](/Users/alecu/ventilastation/vsdk/web/smoke-test.html)
- [web/smoke-test.js](/Users/alecu/ventilastation/vsdk/web/smoke-test.js)

## Boot Sequence Used By The Adapter

The adapter initializes the Python runtime with:

```python
import sys
if "." not in sys.path:
    sys.path.insert(0, ".")
from ventilastation.director import configure_runtime
configure_runtime("browser")
import main
```

So the only missing piece now is a real MicroPython-in-WASM bridge that can:

- evaluate Python code
- call Python functions and return JS-usable values

## Proposed Artifact Layout

Place the official MicroPython webassembly build output under:

```text
web/vendor/micropython/
  micropython.mjs
  micropython.wasm
```

Then replace the placeholder logic in [web/wasm-worker.js](/Users/alecu/ventilastation/vsdk/web/wasm-worker.js) with:

1. loading `micropython.mjs`
2. instantiating `micropython.wasm`
3. exposing `exec(code)` and `call(module, fn, args)`
4. making the `apps/micropython` tree available to the runtime

## Worker Protocol

The main thread sends:

- `initialize`
- `exec`
- `call`

The worker replies with:

- `{ id, ok: true, result }`
- `{ id, ok: false, error }`

That protocol is implemented in:

- [web/micropython-bridge.js](/Users/alecu/ventilastation/vsdk/web/micropython-bridge.js)
- [web/wasm-worker.js](/Users/alecu/ventilastation/vsdk/web/wasm-worker.js)
