# Working on vsdk

Standing guidance for agents and new contributors. Directory-specific
detail lives in each area's README; docs/README.md is the documentation
index.

## Repo shape

- `apps/micropython/ventilastation/` — the SDK runtime (director, scenes,
  platform selection: desktop / hardware / browser / headless).
- `games/<group>/<name>/` — one folder per game: `code/`, `images/`,
  `sounds/`, `menu.png`, `meta.json` (menu order/visibility; discovered by
  `ventilastation/catalog.py`, no launcher edit needed).
- `system/` — launcher and system scenes, shared UI assets.
- `emulator/` — the desktop (pyglet) emulator host. Entry point `emu.py`.
- `web/` — the browser emulator + IDE. **Source of truth**; the website
  repo's `emulator/` directory is published output — never edit that copy
  (see docs/internals/deploying-web-emulator.md).
- `hardware/` — rotor board (MicroPython user C modules), workbench, base.
- `apps/retro-go` — submodule. Ventilastation-specific code stays under
  `components/retro-go/` (targets/ventilastation, vs_host_bridge,
  ventilastation_pov) with minimal diffs elsewhere.
- `tools/`, `tests/` — host-side generators and the test suite.

## Rules that keep biting

- Prefer infrastructure fixes in `ventilastation/` over app-specific
  workarounds in a game.
- Jam game code is historical — don't restyle it. Spanish is fine inside
  games; everything else (core, system, emulators, docs) is English.
- High-frequency MicroPython→JS payloads must cross the WASM bridge as
  pointer + length, never as fresh bytes objects (docs/internals/web-emulator-architecture.md explains
  the heap leak this avoids). Re-run the heap regression check after
  touching the bridge.
- Browser changes need `make web-runtime-bundle` (Python/ROM/meta changes)
  and a `?v=` cache-bust (JS changes) before they show up; see docs/internals/deploying-web-emulator.md.
- MicroPython quirks: no bytearray slice deletion; module `__getattr__`
  works; code under `apps/micropython`, `system/`, `games/` must compile
  with mpy-cross (CI checks this).
- Flash only through the Makefile targets — they serialize the serial port
  so concurrent flashes can't corrupt each other. Board-specific targets
  auto-select the unique matching board; use `make list-boards` to inspect
  the USB mapping and `PORT=...` when several are attached or a specific board
  must be forced. Source ESP-IDF's `export.sh` once per shell session before
  running make — it does not do this per target (docs/internals/building.md).
- Scene lifecycle errors must surface: the director reports tracebacks
  over comms; don't swallow exceptions when changing scene handling.

## Workflow

- Commit per concern with messages that explain why, not just what.
- Before committing runtime changes: run the tests in `tests/` (they run
  under both python3 and micropython where applicable).
- Before pushing firmware changes: build the touched image (`make vsdk`,
  `make voom`, `make workbench-build`).
