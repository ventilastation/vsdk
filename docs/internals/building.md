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
make initial-flash    # selects the unique Ventilastation rotor board
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
make initial-flash            # build + flash it (factory + ota_2 slots) and an empty vfs
make flash-recovery           # bring-up for a new board: factory + NVS only (see ota.md)
make configure-board          # store Ventilastation III wiring in the board's NVS
make configure-board-v2       # store the original Ventilastation 2 wiring
make configure-board-eu       # store the European Edition wiring
make voom                     # build the Doom (prboom-go) Retro-Go app
make flash-launcher           # build + flash the Retro-Go launcher (no OTA path yet)
make build-fs                 # pack games/system Python + ROMs into a LittleFS image
```

Native app partitions (`prboom-go`, `retro-core`) and the LittleFS content are
no longer flashed over USB day-to-day — they install over WiFi via the
three-tier OTA updater (see [ota.md](ota.md)).

## Configuring the main board

The GPIO and bus wiring is not compiled into either firmware. It lives in the
main board's NVS partition, so the same configuration is used by MicroPython,
Voom and retro-core and it survives firmware/filesystem reflashes. A freshly
flashed board must be configured before it can drive the display or talk to the
base station:

```sh
make configure-board           # Ventilastation III (the default)
make configure-board-v2        # original Ventilastation 2
make configure-board-eu        # Ventilastation European Edition
```

`initial-flash` and `flash-recovery` deliberately do not overwrite NVS, so
they preserve an existing board's wiring. On a new board, run
`make configure-board` after `initial-flash` (or `flash-recovery`) and before
using it.

The target uses the same automatic board selection and serial lock as flashing.
Pass `PORT=...` when needed. For a custom revision, override the individual
values, for example:

```sh
make configure-board PORT=/dev/cu.usbmodemXXXX HALL_GPIO=4 LED_CLK=15 LED_MOSI=16
```

The complete key list and the ownership of each value are in
[on-device-design.md](on-device-design.md#2-shared-configuration-in-nvs-single-source-of-truth).

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
