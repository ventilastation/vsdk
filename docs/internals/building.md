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

The two boards use the same ESP32-S3 USB descriptor, so
`tools/find_board.py` asks each firmware which kind of board it is. Targets
select the board type they need automatically:

```sh
make flash-vsdk       # selects the unique Ventilastation rotor board
make workbench-flash  # selects the unique workbench board
make list-boards      # show ports, board types and USB-JTAG serials
```

If more than one board of the requested type is connected, pass `PORT=...` to
choose one. An explicit `PORT` always overrides automatic selection. `MAC=...`
can also select a USB-JTAG serial where the host exposes it (including Linux
`/dev/serial/by-id` names). Flash commands are serialized through a host-side
lock so parallel invocations cannot corrupt a transfer.

## Common targets

```sh
make vsdk                     # build MicroPython firmware (POV modules + frozen manifest)
make flash-vsdk               # build + flash it (factory and ota_2 slots)
make voom                     # build the Doom (prboom-go) Retro-Go app
make flash-voom               # build + flash it
make flash-retro-core         # the multi-console emulator core
make build-fs                 # pack games/system Python + ROMs into a LittleFS image
make deploy-fs                # flash that filesystem image
make flash-all                # everything a fresh board needs
```

For the desktop-emulator development loop against real hardware
(`run-emulator` via the workbench, OTA sync via `wifi-provision` + the
emulator's U key) and the workbench board (`workbench-*` targets), see the
comments in the [Makefile](../../Makefile), [ota.md](ota.md) and
[workbench.md](workbench.md).

## Web emulator runtime

```sh
make web-runtime-bundle       # refresh web/runtime-bundle.json after Python changes
make micropython-webassembly  # rebuild the pinned MicroPython WASM runtime
```
