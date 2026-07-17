# Web Emulator

The browser-based Ventilastation emulator: the MicroPython runtime compiled
to WebAssembly runs the real launcher, system apps and games in a module
worker, and this directory hosts the UI around it — WebGL/canvas POV
renderers, keyboard/gamepad/touch input, audio playback, a Monaco-based
code editor with live reload, a Piskel pixel-art editor, an in-browser ROM
builder, and debug/heap inspectors.

This directory is the **source of truth**; the Jekyll site publishes a copy
of it (see [DEPLOY.md](../docs/internals/deploying-web-emulator.md)). `apps`, `games` and `system` are
symlinks to the repo trees so this directory can be served directly as the
docroot (e.g. `python3 -m http.server` from here): the worker fetches
non-bundled assets — PNGs, sounds — over HTTP relative to the page. The
publish script replaces the symlinks with real copies.

## Layout

| File | Role |
|---|---|
| `index.html`, `styles.css` | page shell, cache-busted script tags |
| `app.js` | `BrowserHostApp`: UI, input, frame loop, inspectors |
| `app-support.js` | shared constants + small helpers |
| `led-ring-renderers.js` | WebGL renderer and 2D-canvas fallback |
| `scene-webgl-compositor.js`, `scene-shader-core.js` | WebGL2 whole-frame compositor and its shared raw-scene/GLSL definition |
| `audio-host.js` | plays the `sound`/`music`/`notes` commands |
| `led-render-core.js` | polar frame math shared with the render parity test |
| `micropython-bridge.js`, `wasm-worker.js`, `wasm-adapter.js` | browser⇄worker⇄WASM bridge (pointer-based frame transport; see ../docs/internals/web-emulator-architecture.md) |
| `monaco-ide.js`, `piskel-embed.js` | embedded code/sprite editors |
| `rom-builder-core.js`, `rom-builder-browser.js`, `workspace-rom-builder.js` | in-browser `.rom` building from `__images__.yaml` |
| `runtime-manifest.json`, `runtime-bundle.json` | generated file list + bundle the worker mounts (`make web-runtime-bundle`) |
| `vendor/` | pinned MicroPython WASM build, Monaco, Piskel |
| `smoke-test.html`, `render-parity-test.js` | manual regression checks |

## Browser Workspace API

The emulator exposes `window.VentilastationWebEmulator` for browser-side
IDEs and parent shells:

- `listProjectFiles(path = ".")`
- `readProjectFile(path, encoding = "utf8")`
- `writeProjectFile(path, content, encoding = "utf8")`
- `deleteProjectFile(path)`
- `applyProjectSnapshot(files)`
- `restartRuntime({ full = true })`

This lets an embedded editor write files directly into the worker-hosted
MicroPython filesystem and restart the runtime without rebuilding
`runtime-bundle.json` on every save.

## Comparing the CPU and shader compositors

Open **Options → Renderer** in the emulator and select either **CPU
(existing)** or **GPU shader (WebGL2)**. The shader path consumes the raw
`sprites` or `vs2_scene` frame payload, maps strip and palette data through
GPU textures, and renders the complete 256×54 LED frame before the radial
preview pass; it never calls the JavaScript per-column compositor.

**Compare CPU / shader** warms both full paths and then times 24 synchronized
frames with `gl.finish()` so the result includes GPU work rather than only
command submission. It also reads back the shader LED texture once and reports
pixel parity against the CPU compositor. This makes the same control useful for
collecting comparable results on desktop and mobile browsers. The GPU option
falls back to the CPU path on WebGL1-only devices, while strips are still
loading, and for raw RGB-frame games.

The core packer/software-parity checks run without a browser:

```sh
node tests/test_scene_shader_core.mjs
```

## Development notes

- Python-side changes only reach the browser after `make web-runtime-bundle`
  regenerates `runtime-bundle.json`.
- When changing worker or module JS, bump the `?v=` cache-busting version in
  `index.html` (and in module import specifiers) or browsers will keep the
  old file.
- After bridge/display changes, run the heap regression check described in
  ../docs/internals/web-emulator-architecture.md ("Manual Regression Check").
