# Ventilastation Development Kit

Ventilastation is an open source electromechanical console for circular games, built with a large fan, a bar of LEDs and MicroPython.

<img width="40%" alt="Ventilastation console and emulator" src="https://github.com/user-attachments/assets/25be08fe-a0b5-4171-874c-5623d56633fa" />
<img width="40%" alt="Ventilastation console and emulator" src="https://github.com/user-attachments/assets/4e18ef31-3a48-4196-8ebd-66cba60be72e" />

## Start here

- **[Set up the desktop emulator](docs/guides/desktop.md)** — develop and test games on your computer.
- **[Make your first VS2 game](https://ventilastation.protocultura.net/docs/vs2/tutorial/first-game.html)** — start with [desktop setup](docs/guides/desktop.md), then build a game through seven chapters.
- **[API reference](https://ventilastation.protocultura.net/docs/vs2/reference/index.html)** — current VS2, generated from code.
- **[SDK and hardware internals](docs/internals/README.md)** — runtime, emulators, firmware and protocols; see [AGENTS.md](AGENTS.md) for working rules.

[Documentation sources and maintenance](docs/README.md) live in this repository.
The original `ventilastation.sprites` API is **obsolete for new development**;
its [maintenance guide](docs/legacy/sprites-api.md) is separate from the VS2 path.
Existing V1 games continue to run.

## Repo layout

- `games/<group>/<name>/` — one folder per game: `code`, `images`,
  `sounds`, `menu.png`, `meta.json`
- `system/` — the launcher and other built-in apps, shared UI assets
- `apps/micropython/ventilastation/` — the SDK runtime
- `apps/retro-go` — submodule: native apps (Voom/Doom, console emulators)
- `emulator/` — the desktop emulator host; `web/` — the browser emulator + IDE
- `hardware/` — rotor firmware modules, schematics, the test workbench
- `tools/`, `tests/` — generators and the test suite (`python3 tests/run_tests.py`)

## Build your own Ventilastation

If you have some maker experience, there are also schematics and blueprints so you can build your own Ventilastation console — see `hardware/` and [docs/internals/building.md](docs/internals/building.md) for flashing firmware.

<img width="40%" alt="Ventilastation console and emulator" src="https://github.com/user-attachments/assets/b6c1ed0a-6657-4d1e-be63-2cbb74b9bcad" />
<img width="40%" alt="Ventilastation console and emulator" src="https://github.com/user-attachments/assets/0130f902-f64b-4f7b-8971-a659ffe97859" />
