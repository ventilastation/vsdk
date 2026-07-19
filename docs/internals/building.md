# Building Ventilastation firmware

This covers building and flashing the ESP32-S3 firmware images. For the
desktop/web emulators (no hardware needed) see the setup guides in
[docs/](docs/) instead.

## Prerequisites

The rotor firmware is made of two builds -- MicroPython
(`hardware/rotor/micropython` + `hardware/rotor/modules`) and the Retro-Go
apps (`apps/retro-go` submodule, `voom`/prboom-go, launcher, retro-core,
fmsx) -- and, since both now target the same ESP-IDF release (5.5.x), so
does the workbench. One checkout covers everything.

1. Install ESP-IDF 5.5.x (`install.sh`, so `export.sh` works).
2. Clone MicroPython where the build expects it (the path is gitignored):

   ```sh
   git clone https://github.com/micropython/micropython hardware/rotor/micropython
   ```

3. Initialize the Retro-Go submodule: `git submodule update --init apps/retro-go`

**Source the environment once per shell session, before running `make`:**

```sh
source ../../esp-idf/esp-5.5.2/export.sh   # or wherever your checkout lives
```

The Makefile deliberately does *not* do this for you per target -- that used
to happen on every single step (build, flash, provision, ...) via a wrapping
login shell, and re-running `export.sh` that often adds real seconds to each
one. Instead it just checks that `$IDF_PATH` is already set (which
`export.sh` does) and fails fast with a reminder if you forgot:

```
$ make voom
Makefile:92: *** ESP-IDF environment not active in this shell. Run 'source ../../esp-idf/esp-5.5.2/export.sh' once per session ... Stop.
```

The environment stays active for the rest of the shell session -- source it
once, then run as many `make` targets as you like.

## Selecting a board

The two boards use the same ESP32-S3 USB descriptor, so telling them apart
by port name alone doesn't work. `tools/find_board.py` instead keeps a small
local registry mapping each board's USB serial number (its factory MAC, so
it's stable across reflashes) to a kind, at a per-OS path (`~/Library/Application
Support/vsdk/boards.json` on macOS, `$XDG_CONFIG_HOME/vsdk/boards.json` —
usually `~/.config/vsdk/boards.json` — on Linux). Register each board once:

```sh
make register-rotor       # only one board attached: no PORT needed
make register-workbench   # several attached: pass PORT=... to say which one
make register-base
```

After that, `make initial-flash`, `make workbench-flash`, and friends select
their board with a plain USB-descriptor lookup — no serial I/O, no
multi-second wait. If the requested kind isn't registered, the target fails
fast and tells you to register it (or pass `PORT=...` to bypass selection
entirely). `make list-boards` shows every candidate port; for anything not
in the registry it falls back to a RESYNC probe (see
[input-protocol-v2.md](input-protocol-v2.md#resync--device-identification))
to identify what's plugged in, which is where the multi-second cost still
lives — worth it there since it's a one-off diagnostic, not a hot path.

An explicit `PORT` always overrides selection (registered or not). `MAC=...`
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
emulator's Ctrl-U/Command-U shortcut) and the workbench board (`workbench-*` targets), see the
comments in the [Makefile](../../Makefile), [ota.md](ota.md) and
[workbench.md](workbench.md).

## Web emulator runtime

```sh
make web-runtime-bundle       # refresh web/runtime-bundle.json after Python changes
make micropython-webassembly  # rebuild the pinned MicroPython WASM runtime
```
