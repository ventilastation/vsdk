# Ventilastation Development Kit

Ventilastation is a an open source electromechanical console for circular games, built with a large fan, a bar of LEDs and Micropython.

<img width="40%" alt="image" src="https://github.com/user-attachments/assets/25be08fe-a0b5-4171-874c-5623d56633fa" />
<img width="40%" alt="image" src="https://github.com/user-attachments/assets/4e18ef31-3a48-4196-8ebd-66cba60be72e" />


# Ventilastation Emulator
Using the code in this repo you can develop games and apps for Ventilastation, and try them in the included emulator.

<img width="40%" alt="image" src="https://github.com/user-attachments/assets/18183e03-9fad-48d9-88ea-10ac6141eb14" />

The emulator has been tested on modern Linux, macOS and Windows.

- [Linux setup](docs/emulator-setup.Linux.md)
- [macOS setup](docs/emulator-setup.macOS.md)
- [Windows setup](docs/emulator-setup.Windows.md)

## Current Repo Layout

Game code and assets now live together under `games/<slug>/`:

- `games/<slug>/code`
- `games/<slug>/images`
- `games/<slug>/sounds`

The default boot app is the launcher in `system/launcher/code`, and shared non-game assets live under `system/menu` and `system/shared`.

## Rebuilding The WebAssembly Runtime

The browser emulator uses vendored MicroPython WebAssembly artifacts under `web/vendor/micropython/`.

To rebuild those files with `sys.settrace` enabled:

```bash
cd vsdk
make micropython-webassembly
```

That target:

- clones pinned `micropython` and `emsdk` checkouts into `/tmp/vsdk-micropython-webassembly` by default
- applies the repo's trace-enabled WebAssembly variant and compatibility patch
- builds `micropython.mjs` and `micropython.wasm`
- copies them into `web/vendor/micropython/`
- bumps the browser cache-busting version strings used by the worker bridge

Useful overrides:

```bash
BUILD_ROOT=/tmp/custom-vsdk-build make micropython-webassembly
VERSION_TAG=20260618T160000Z make micropython-webassembly
BUILD_JOBS=8 make micropython-webassembly
```

# Build your own Ventilastation

If you have some maker experience, there are also schematics and blueprints so you can build your own Ventilastation console.

<img width="40%" alt="image" src="https://github.com/user-attachments/assets/b6c1ed0a-6657-4d1e-be63-2cbb74b9bcad" />
<img width="40%" alt="image" src="https://github.com/user-attachments/assets/0130f902-f64b-4f7b-8971-a659ffe97859" />
