# Browser Host Scaffold

This directory is a minimal static shell for the future WASM runtime.

It currently provides:

- event-driven keyboard input mapped to the Ventilastation button bitmask
- a pull-based frame polling loop
- a debug canvas that renders exported sprite state
- inspector panels for runtime events, sprites, and assets
- a mock runtime adapter so the shell works before MicroPython/WASM is wired in
- a WASM adapter layer that auto-activates if a low-level bridge is provided
- a worker-bridge scaffold for integrating the official MicroPython `webassembly` port

## Run

Serve the repository root or the `web/` directory with any static HTTP server.

Example:

```bash
cd /Users/alecu/ventilastation/vsdk
python3 -m http.server 8000
```

Then open `http://localhost:8000/web/`.

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

## Next Step

Replace the mock adapter with a real low-level WASM bridge.

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

Today those files provide the transport and placeholder runtime. They do not include the actual MicroPython artifacts yet.

The high-level adapter already translates that into:

- `ventilastation.browser.set_buttons(...)`
- `ventilastation.browser.export_frame(...)`
- optionally `ventilastation.browser.export_storage(...)`

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
