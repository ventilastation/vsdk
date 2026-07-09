# Building Ventilastation firmware

This covers building and flashing the ESP32-S3 firmware images. For the
desktop/web emulators (no hardware needed) see the setup guides in
[docs/](docs/) instead.

## Prerequisites

The rotor firmware is made of **two builds that need two different ESP-IDF
versions**:

| What | Source | ESP-IDF | Makefile variable |
|---|---|---|---|
| MicroPython (menu + Python games + POV C modules) | `hardware/rotor/micropython` + `hardware/rotor/modules` | 5.5.x | `VSDK_IDF_PATH` |
| Retro-Go apps (`voom`/prboom-go, launcher, retro-core) | `apps/retro-go` submodule | 5.0.x | `RETRO_GO_IDF_PATH` |

1. Install both ESP-IDF versions (each in its own directory, with
   `install.sh` run so `export.sh` works).
2. Clone MicroPython where the build expects it (the path is gitignored):

   ```sh
   git clone https://github.com/micropython/micropython hardware/rotor/micropython
   ```

3. Initialize the Retro-Go submodule: `git submodule update --init apps/retro-go`

The Makefile defaults assume the IDF trees live at
`../../esp-idf/esp-5.5.2` and `../../esp-idf/esp-5.0.4` relative to this
repo. Override per invocation or in your environment when yours live
elsewhere:

```sh
make vsdk VSDK_IDF_PATH=~/esp/esp-idf-v5.5 RETRO_GO_IDF_PATH=~/esp/esp-idf-v5.0.4
```

## Selecting a board

Every target that touches a board needs `PORT=...`. On Linux, `/dev/ttyACM*`
numbers can swap between resets when two boards are attached; pass
`MAC=aa:bb:cc:dd:ee:ff` instead to select the board by its USB-JTAG serial.
`make list-boards` shows what is attached. Flash commands are serialized
through a host-side lock so parallel invocations cannot corrupt a transfer.

## Common targets

```sh
make vsdk                     # build MicroPython firmware (POV modules + frozen manifest)
make flash-vsdk PORT=...      # build + flash it (factory and ota_2 slots)
make voom                     # build the Doom (prboom-go) Retro-Go app
make flash-voom PORT=...      # build + flash it
make flash-retro-core PORT=...# the multi-console emulator core
make build-fs                 # pack games/system Python + ROMs into a LittleFS image
make deploy-fs PORT=...       # flash that filesystem image
make flash-all PORT=...       # everything a fresh board needs
```

For the desktop-emulator development loop against real hardware
(`flash-voom-emulator`, `dev-deploy`, `run-emulator`) and the workbench
board (`workbench-*` targets), see the comments in the [Makefile](Makefile)
and [WORKBENCH.md](WORKBENCH.md).

## Web emulator runtime

```sh
make web-runtime-bundle       # refresh web/runtime-bundle.json after Python changes
make micropython-webassembly  # rebuild the pinned MicroPython WASM runtime
```
