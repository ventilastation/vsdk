# Ventilastation Development Kit

Ventilastation is an open source electromechanical console for circular games, built with a large fan, a bar of LEDs and MicroPython.

<img width="40%" alt="image" src="https://github.com/user-attachments/assets/25be08fe-a0b5-4171-874c-5623d56633fa" />
<img width="40%" alt="image" src="https://github.com/user-attachments/assets/4e18ef31-3a48-4196-8ebd-66cba60be72e" />

## Documentation: pick your path

**🎮 I want to make a game** → start at **[docs/](docs/README.md)**.
Install the emulator, clone the smallest game, learn Scenes/Sprites/the
polar display, add graphics and sounds, and get on the menu — everything a
game developer needs, no hardware required.

**🔧 I want to work on vsdk itself** (runtime, emulators, editors, native
apps, hardware) → start at **[docs/internals/](docs/internals/README.md)**,
and read [AGENTS.md](AGENTS.md) for the repo shape and working rules. ROM
and wire-protocol specs, firmware building, the web emulator architecture
and the hardware workbench all live there.

## Ventilastation Emulator

Using the code in this repo you can develop games and apps for Ventilastation, and try them in the included emulator.

<img width="40%" alt="image" src="https://github.com/user-attachments/assets/18183e03-9fad-48d9-88ea-10ac6141eb14" />

The emulator has been tested on modern Linux, macOS and Windows — setup
guides are in [docs/](docs/README.md). There is also a browser-based
emulator with a built-in code editor and sprite editor, served from
`web/` (see [docs/internals/deploying-web-emulator.md](docs/internals/deploying-web-emulator.md)).

### Desktop scene-renderer comparison

The Pyglet 2 desktop emulator can compose raw `sprites` or `VS2` scene bytes
in a single OpenGL 3.3 pass instead of the usual CPU/native full-frame path.
Start directly in that mode with `./vs-emu.sh --scene-renderer shader`, or
press **F2** in the emulator to switch between **CPU** and **GPU shader**.
Press **F3** with a game/menu scene visible to measure both complete paths
(including their texture uploads) and check their rendered RGBA pixels match.
The result stays in the upper-left status line, making it easy to record the
same comparison on different machines. Captured `frame_rgb`/`frame_apa102`
frames remain on the established CPU upload path because they are already
final LED pixels.

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

<img width="40%" alt="image" src="https://github.com/user-attachments/assets/b6c1ed0a-6657-4d1e-be63-2cbb74b9bcad" />
<img width="40%" alt="image" src="https://github.com/user-attachments/assets/0130f902-f64b-4f7b-8971-a659ffe97859" />
