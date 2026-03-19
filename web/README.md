# Browser Host Scaffold

This directory is a minimal static shell for the future WASM runtime.

It currently provides:

- event-driven keyboard input mapped to the Ventilastation button bitmask
- a pull-based frame polling loop
- a debug canvas that renders exported sprite state
- inspector panels for runtime events, sprites, and assets
- a mock runtime adapter so the shell works before MicroPython/WASM is wired in

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

Replace the mock adapter with a real WASM bridge that calls:

- `ventilastation.browser.set_buttons(...)`
- `ventilastation.browser.export_frame(...)`
- optionally `ventilastation.browser.export_storage(...)`
