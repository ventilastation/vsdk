# Deploying the web emulator

The editable source lives in `vsdk/web/`. The public site serves a
published copy from the website repo's `emulator/` directory (this repo is
its `vsdk/` submodule). Treat that copy as build output — never edit it
directly (see ARCHITECTURE.md, "Source Tree").

## Refresh steps

1. **Regenerate ROMs** if game/system images changed:

   ```sh
   make generate-roms
   ```

2. **Refresh the runtime bundle** if any Python under `apps/micropython`,
   `games/` or `system/` changed (the worker mounts its filesystem from
   `web/runtime-bundle.json`; the file list in `runtime-manifest.json` is
   auto-discovered):

   ```sh
   make web-runtime-bundle
   ```

3. **Bump cache-busting versions** if worker or module JS changed: the
   `?v=` strings in `web/index.html` script tags and in module import
   specifiers. Stale workers are the usual cause of "my change does
   nothing".

4. **Publish** the tree into the website repo:

   ```sh
   ./tools/build-web-emulator-bundle.sh ../emulator
   ```

   (Without an argument it builds to `dist/emulator` for inspection.)

5. Commit both repos: the `vsdk` submodule bump and the regenerated
   `emulator/` copy in the website repo.

## Rebuilding the MicroPython WASM runtime

Only needed when upgrading MicroPython itself or its build patches:

```sh
make micropython-webassembly
```

This clones pinned checkouts, applies the repo's patches, builds
`micropython.mjs`/`micropython.wasm` into `web/vendor/micropython/`, and
bumps the worker cache-busting version.

That target clones pinned `micropython` and `emsdk` checkouts into
`/tmp/vsdk-micropython-webassembly` by default and applies the repo's
trace-enabled WebAssembly variant and compatibility patch. Useful
overrides:

```sh
BUILD_ROOT=/tmp/custom-vsdk-build make micropython-webassembly
VERSION_TAG=20260618T160000Z make micropython-webassembly
BUILD_JOBS=8 make micropython-webassembly
```

## Post-deploy check

Load the published emulator, let the menu idle 30–60 s, and confirm
`Heap Used` stays steady (ARCHITECTURE.md, "Manual Regression Check").
