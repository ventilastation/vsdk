# vsdk internals

Documentation for people (and agents) working on vsdk itself: the runtime,
the emulators, the editors, the native apps and the hardware. If you just
want to **make a game**, you're in the wrong folder — start at
[../README.md](../README.md) instead.

Also read [../../AGENTS.md](../../AGENTS.md) first: it lists the repo
shape and the rules that keep biting.

## Choose your task

- **Make a game:** [first VS2 game](../vs2/tutorial/first-game.md).
- **Profile the desktop emulator:** [CPU/GPU scene comparison](emulator-performance.md#desktop-scene-renderer-comparison).
- **Change the browser/IDE:** [web architecture](web-emulator-architecture.md),
  [workspace contract](web-ide-integration.md), [publishing](deploying-web-emulator.md).
- **Build or operate hardware:** [on-device architecture](on-device-design.md),
  [building/flashing](building.md), [workbench](workbench.md), [OTA](ota.md).
- **Change the runtime:** [current VS2 decisions](vs2-decisions.md),
  [host protocol](host-protocol.md), [hardware acceptance](vs2-hardware-acceptance.md).

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

- **[vs2-decisions.md](vs2-decisions.md)** — accepted current API decisions.
- **[emulator-performance.md](emulator-performance.md)** — desktop CPU/GPU comparison and earlier profiling results.
- **[workbench.md](workbench.md)** — the second ESP32-S3 that exercises a
  real board: LED-bus capture, hall simulation, UART bridge, telemetry.
- **[vs2-hardware-acceptance.md](vs2-hardware-acceptance.md)** — repeatable
  USB-only API v2 timing, heap-stability, and physical-render parity gates.
- **[remote-workbench-access.md](remote-workbench-access.md)** — authenticated
  remote mobile access to a physical workbench: tunnel, Google login, ACL,
  controller lease, frames, audio, input, deployment, and verification.
- **[pov-color-pipeline.md](pov-color-pipeline.md)** — calibrated game-RGB
  conversion, shared APA102 encoder, NVS profile format, and calibration
  protocol for MicroPython, Retro-Go, the workbench, and the desktop preview.
- **[emulator-audio.md](emulator-audio.md)** — streaming console
  sound-chip register writes to the host synth (`emulator/chipsynth`).
- **[serial-stress-test.md](serial-stress-test.md)** — measuring the
  base↔rotor serial link: the Serial Stress app, `tools/serial_stress.py`,
  loopback tests, and how to tell wire errors from software overruns.
- **[ota.md](ota.md)** — the three-tier OTA update system.
- **[game-packages.md](game-packages.md)** — .vs2 game packages: editor/CLI
  build, push to the base, single-file board install, menu rom merging.
- **[native-app-handoff.md](native-app-handoff.md)** — launching retro-go
  apps (Voom, NES, SMS) from the MicroPython launcher via partition
  switching.
- **[web-ide-integration.md](web-ide-integration.md)** — the browser IDE's
  workspace API hooks.

## Compatibility and hardware validation

- [ROM width/frame encoding](rom-width-sentinel.md) records the bias-by-one
  migration now implemented in `main`; its remaining hardware checks retain
  their stated status.
- Resolved menu/OTA display investigations are in [history](history/README.md),
  separate from current instructions.

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

```{toctree}
:hidden:
:maxdepth: 1

base-control-api
building
deploying-web-emulator
emulator-audio
emulator-performance
game-packages
host-protocol
input-protocol-v2
native-app-handoff
on-device-design
ota
pov-color-pipeline
remote-workbench-access
rom-format
rom-width-sentinel
vs2-decisions
vs2-hardware-acceptance
web-emulator-architecture
web-ide-integration
workbench
history/README
```
