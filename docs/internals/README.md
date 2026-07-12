# vsdk internals

Documentation for people (and agents) working on vsdk itself: the runtime,
the emulators, the editors, the native apps and the hardware. If you just
want to **make a game**, you're in the wrong folder — start at
[../README.md](../README.md) instead.

Also read [../../AGENTS.md](../../AGENTS.md) first: it lists the repo
shape and the rules that keep biting.

## Suggested reading order

1. **[on-device-design.md](on-device-design.md)** — how the spinning
   ESP32-S3 is partitioned: MicroPython + retro-go apps sharing one flash,
   how each is launched. The mental model everything else hangs off.
2. **[building.md](building.md)** — building and flashing firmware; the
   two-ESP-IDF setup, board selection, Makefile targets.
3. **[web-emulator-architecture.md](web-emulator-architecture.md)** — the
   browser emulator: worker/WASM layering, frame flow, and the
   pointer-posting memory rule you must not break.
4. **[deploying-web-emulator.md](deploying-web-emulator.md)** — bundle
   refresh, cache busting, publishing into the website repo.

## Wire formats and data (normative specs)

- **[rom-format.md](rom-format.md)** — the sprite ROM container. Three
  builders (Python, Node, browser) and every renderer consume it;
  `tests/test_rom_format.py` enforces it.
- **[input-protocol-v2.md](input-protocol-v2.md)** — the joystick/command
  byte stream. Implemented in `ventilastation/input_parser.py`, the
  retro-go `vs_host_bridge.c`, and the workbench; keep them in lockstep.
- **[host-protocol.md](host-protocol.md)** — the line-based command
  protocol the runtime sends to whichever host plays audio and (in
  emulation) draws frames.
- **[base-control-api.md](base-control-api.md)** — reusable base RGB, servo,
  and button-light control; includes the Voom feedback design and safe
  normalized-servo contract.

## Subsystems

- **[vs2-api-plan.md](vs2-api-plan.md)** — the API v2 rollout plan: new
  `vs2` game API, compatibility guard, v2 memory model, and renderer phases.
- **[workbench.md](workbench.md)** — the second ESP32-S3 that exercises a
  real board: LED-bus capture, hall simulation, UART bridge, telemetry.
- **[pov-color-pipeline.md](pov-color-pipeline.md)** — calibrated game-RGB
  conversion, shared APA102 encoder, NVS profile format, and calibration
  protocol for MicroPython, Retro-Go, the workbench, and the desktop preview.
- **[emulator-audio.md](emulator-audio.md)** — streaming console
  sound-chip register writes to the host synth (`emulator/chipsynth`).
- **[ota.md](ota.md)** — the three-tier OTA update system.
- **[native-app-handoff.md](native-app-handoff.md)** — launching retro-go
  apps (Voom, NES, SMS) from the MicroPython launcher via partition
  switching.
- **[web-ide-integration.md](web-ide-integration.md)** — the browser IDE's
  workspace API hooks.

## Where the code lives

| Area | Path |
|---|---|
| SDK runtime (director, scenes, platforms) | `apps/micropython/ventilastation/` |
| POV display C modules (MicroPython firmware) | `hardware/rotor/modules/povdisplay/` |
| retro-go fork (Voom + console emulators) | `apps/retro-go` (submodule; VS-specific code under `components/retro-go/`) |
| Desktop emulator host | `emulator/` |
| Web emulator + IDE | `web/` |
| Workbench firmware | `hardware/workbench/workbench_esp32s3/` |
| Generators and host tools | `tools/` |
| Test suite (`python3 tests/run_tests.py`) | `tests/` |

## Historical documents

[history/](history/) keeps plans that have since shipped or changed —
context only, don't code against them.
