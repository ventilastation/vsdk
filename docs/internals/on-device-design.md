# Ventilastation on-device design

How the spinning ESP32-S3 board is partitioned, how MicroPython and the native
retro-go apps share configuration, and how each is launched. Companion to
`emulator-audio.md` (emulator audio bridge).

## 1. Flash layout (16 MB)

The board runs **two firmwares**: MicroPython (the Ventilastation menu + Python
games), normally running from the `micropython` partition, and several
**native retro-go apps**, each in its own OTA app partition. They share one
LittleFS data partition (`vfs`). `factory` holds the same MicroPython image
but serves as the board's permanent recovery environment (see
`docs/internals/ota.md`), not a normal boot target — it's reached on a fresh
board, after a bad OTA update fails to confirm itself, or during a
firmware-update hand-off.

Defined in `hardware/rotor/partitions-ventilastation.csv`:

| Partition  | Type        | Offset    | Size      | Holds |
|------------|-------------|-----------|-----------|-------|
| nvs        | data/nvs    | 0x9000    | 0x4000    | shared config (see §2) |
| otadata    | data/ota    | 0xd000    | 0x2000    | which OTA app boots |
| phy_init   | data/phy    | 0xf000    | 0x1000    | RF cal |
| factory    | app/factory | 0x10000   | 0x200000  | **MicroPython** (permanent recovery environment) |
| prboom-go  | app/ota_0   | 0x210000  | 0x180000  | Voom (Doom) |
| retro-core | app/ota_1   | 0x390000  | 0x100000  | **NES, Master System, Game Gear, …** |
| micropython| app/ota_2   | 0x490000  | 0x200000  | **MicroPython** (normal boot target, OTA-updatable) |
| vfs        | data/fat\*  | 0x690000  | 0x970000  | LittleFS: code, sprite ROMs, game ROMs |

\* labelled `fat` historically; the content is LittleFS, mounted at `/` by
MicroPython and at `/vfs` by retro-go (`RG_STORAGE_ROOT`).

The `retro-core` slot originally held the standalone retro-go launcher, which is
disabled (its text is unreadable at the POV display's resolution); the partition
was repurposed for the multi-emulator `retro-core` app (0.92 MB, fits).

Booting another app = `esp_ota_set_boot_partition(target)` + reboot. On exit the
native apps set the boot partition back to `factory`, returning to the
MicroPython menu.

## 2. Shared configuration in NVS (single source of truth)

Config that must outlive firmware/filesystem reflashes and be read by **both**
firmwares lives in **NVS** (its own flash partition, never erased by app or vfs
flashing). There are no more `wifi_config.json` / `settings.json` files.

| Namespace  | Key          | Type | Written by | Read by |
|------------|--------------|------|------------|---------|
| `devel_wifi`| `ssid`      | blob | `tools/provision_wifi.py` (`mpremote run`) | MicroPython `updater.py` (OTA only) |
| `devel_wifi`| `password`  | blob | `tools/provision_wifi.py` | same |
| `vs_board` | `hall_gpio`, `irdiode_gpio` | i32 | `tools/provision_board.py` / `make configure-board*` | MicroPython POV display; native POV display |
| `vs_board` | `led_spi_host`, `led_clk`, `led_mosi`, `led_cs`, `led_freq` | i32 | same | MicroPython LED SPI; native POV display |
| `vs_board` | `serial_uart`, `serial_tx`, `serial_rx`, `serial_baud` | i32 | same | MicroPython comms; native host/audio bridge |
| `voom_pov` | `col_offset` | i32  | MicroPython `settings.py` (POV calibration) | POV driver `ventilastation_pov.c` (all native apps) |
| `voom_pov` | `color_v1` | versioned blob | MicroPython `color_calibration.py` / `povcal commit` | MicroPython and native POV colour pipelines |
| `voom_md`  | `rom`        | blob | MicroPython `native_apps.py` (before launch) | gwenesis `main.c` |
| `voom_emu` | `system`     | blob | MicroPython `native_apps.py` (before launch) | retro-core `main.c` (selects the emulator) |
| `voom_emu` | `rom`        | blob | MicroPython `native_apps.py` (before launch) | retro-core `main.c` |

Notes:
- **WiFi**: set once with `make wifi-provision WIFI_SSID=... WIFI_PASS=...`,
  which runs a tiny script on the board writing `devel_wifi`. The board never
  joins WiFi at boot — only `updater.py` reads the credentials, when an OTA
  upgrade is requested over the serial host link (see ota.md). Survives every
  reflash.
- **POV calibration** (`pov_column_offset`): `settings.py` reads/writes
  `voom_pov`/`col_offset` directly, the exact key the native POV driver reads —
  no copy step. On desktop (no `esp32` module) settings fall back to in-memory
  defaults.
- **Main-board wiring**: set after the first flash with `make configure-board`
  (Ventilastation III), `make configure-board-v2`, or
  `make configure-board-eu`. `vs_board` is the single source of truth for the
  Hall sensor, LED SPI and base-station UART, so changing a board revision no
  longer requires rebuilding MicroPython, prboom-go or retro-core. Override
  individual Make variables for a custom revision; see [building.md](building.md).
- **Mega Drive ROM path**: see §3.

## 3. Launching native apps from MicroPython

The MicroPython menu (`system/launcher`) lists native apps by slug. Selecting one
runs `native_apps.py` → `vshw_native_apps.launch(<name>)`
(`hardware/rotor/modules/native_apps/native_apps.c`), which maps the name to a
partition, sets it as the OTA boot partition, and reboots.

Registry (`native_apps.c`): `voom`→prboom-go, `gwenesis`→gwenesis,
`retro-core`→retro-core.

Menu slugs (`native_apps.py` `APP_REGISTRY`):
- `native.voom` → Voom (fixed WAD, no ROM arg)
- `native.nes` → "Super Mario Bros" — `retro-core`, `system=nes`
- `native.sms` → "Out Run" — `retro-core`, `system=sms`
- `native.genesis` → Mega Drive — `gwenesis` (registry only, off the menu)

**Handing an emulator its ROM.** The retro-go launcher normally passes the ROM
path (and the system) via its `bootArgs`/settings, but that uses a
sentinel-namespaced config file awkward to write from MicroPython. Since the
launcher is disabled, MicroPython writes the values to NVS just before launching:

- **gwenesis** (single system): ROM path → `voom_md`/`rom`; read in `main.c` when
  `bootArgs` is empty.
- **retro-core** (many systems): `system` + `rom` → `voom_emu`; `main.c` reads
  them, sets `app->configNs` (which the dispatch strcmp's — nes/sms/gg/…) and
  `app->romPath`.

```
main menu "Super Mario Bros"
  → native_apps.py writes voom_emu/system="nes", voom_emu/rom="/vfs/roms/nes/…"
  → vshw_native_apps.launch("retro-core")   (OTA → retro-core, reboot)
  → retro-core main.c: read voom_emu → configNs="nes", romPath=… → nes_main()
```

Console ROMs live in `apps/retro-go/roms/<system>/` (`md`, `nes`, `sms` —
gitignored) and are copied into the vfs image at `/roms/<system>/` by
`build_micropython_fs.py` (ROM extensions scoped to those folders). The
emulators load `.zip` directly.

## 3a. Running a retro-go emulator on the POV board

Every native retro-go emulator (gwenesis, retro-core, …) needs the same three
adaptations to run headless on the spinning board, because the stock code
assumes an LCD + SD card + the retro-go launcher. Do these in the app's
`app_main`, right after `rg_system_init` (see `gwenesis/main/main.c` and
`retro-core/main/main.c`):

1. **Mount `/vfs`** — `esp_vfs_littlefs_register({base_path "/vfs",
   partition_label "vfs"})`. The default `rg_storage` init mounts FAT (or an SD
   card), but the data partition is LittleFS; without this, `fopen("/vfs/…")`
   returns ENOENT and ROM loading fails. Needs the `joltwallet/littlefs`
   dependency in the app's `idf_component.yml`.
2. **POV display** — starts on its own: the driver's display task brings up
   the LED SPI bus as soon as `rg_vs_pov_init()` runs (no per-app call needed).
3. **Read the ROM (and system) from NVS** — see §3, since there are no bootArgs.

Config that the POV driver / audio bridge read from NVS (the `vs_board` wiring,
WiFi and `col_offset`) needs no per-app work — it is already in NVS (§2).

**Performance (why NES/SMS, not Genesis).** The Genesis is a dual-CPU
(68000 + Z80) machine and gwenesis runs at ~9 fps / 100 % CPU on the S3. The NES
(nofrendo) and Master System (smsplus) are single-CPU and run at a locked 60 fps
using ~50–60 % CPU. `retro-core` gets NES, Master System, Game Gear (and Game
Boy, PC Engine, … later) from one 0.92 MB app. NES sets `app->frameskip = 0`
(like SMS) so it renders every frame that fits the 16.6 ms budget to the POV.

## 4. Compressed sprite ROMs

MicroPython sprite ROMs (`apps/micropython/roms/*.rom`, generated from PNGs by
`tools/generate_roms.py`) are palette-indexed image data and compress ~85% with
deflate. `build_micropython_fs.py` stores each as **`<name>.rom.gz`** (gzip) in
the vfs image; `director.py` finds the `.gz` file and inflates it with the
board's `deflate` module, parsing it in RAM. Repo `.rom` files stay
uncompressed, so the desktop/web emulators are unaffected. This freed ~2.4 MB of
the vfs partition — enough to add the gwenesis app partition and Genesis ROMs.

## 5. Emulator audio bridge

The native emulators have no DAC on the spinning board, and 115200 baud is far
too slow for PCM. Instead the board streams the **sound-chip register writes**
(a VGM-style score) over the UART; the base-station host re-runs the *same* chip
cores to regenerate the audio. Full design in `emulator-audio.md`.

**Done — Genesis (gwenesis).**
- Device: `emu_audio_bridge.{c,h}` (shared, in `components/retro-go`) encodes a
  per-frame varint log of register writes and ships it as `achip` / `aframe` /
  `astop` lines. Taps in `ym2612.c` (`YM2612Write`) and `gwenesis_sn76489.c`
  (`gwenesis_SN76489_Write`), timestamped with each chip's in-frame sample index.
- Device also **skips the on-device PCM synthesis** (`ym2612_skip_synthesis` /
  `sn76489_skip_synthesis`): the host regenerates it, so the samples would only
  be discarded by the dummy sink. YM2612 keeps its timers running (the sound
  driver polls them); SN76489 is skipped outright.
- Host: `emulator/chipsynth/` compiles the unmodified gwenesis YM2612 + SN76489
  cores into `libgenesissynth`; `emulator/emu_audio.py` replays each `aframe`
  through it and plays the PCM via a pyglet streaming source. Runs ~11.5 KB/s,
  within the link budget.

### Next steps — NES + Master System audio (Phase 2)

Same pattern, per chip. The wire protocol, host player, and the `EMU_OP_*` op
encoding in `emu_audio_bridge.h` already leave room for these.

1. **Device taps.**
   - NES (nofrendo): tap `apu_write(addr, value)` in `nes/apu.c` (single handler
     for `0x4000–0x4017`). Encode with `EMU_OP_NES_BASE | (addr & 0x1f)`.
   - SMS (smsplus): tap the SN76489 PSG write. (A few games also drive the YM2413
     FM chip — optional, add a second op range if wanted.)
   - Call `emu_audio_begin("nes"|"sms")` / per-frame `emu_audio_frame_begin/end`
     from `retro-core/main/main_nes.c` / `main_sms.c`, like gwenesis does. Add the
     same `*_skip_synthesis` flags so the device doesn't waste CPU synthesizing
     audio it discards (NES/SMS have CPU headroom, so this is optional but tidy).
2. **Host synths.** Add `libnessynth` / `libsmssynth` under `emulator/chipsynth/`
   compiling nofrendo's APU / smsplus's SN76489 (mirror `host_chip.c` +
   `Makefile`). Register them in `emu_audio.py`'s `_SYNTH_FACTORIES` keyed by the
   `achip` system name. **Gotcha (learned on Genesis):** `host_chip.c` must
   *define* every `extern` global the chip sources reference (buffers, indices,
   and any `*_skip_synthesis` flags, set to 0) or the shared lib links with an
   undefined symbol and segfaults at first render.
3. **Timing.** NES APU and SMS PSG have far lower register-write rates than the
   YM2612, so bandwidth is a non-issue. Reuse the per-frame sample-index
   timestamping already in `emu_audio_bridge.c`.

## 6. Build & flash

Rebuild after changes:
- MicroPython (`factory`): `make vsdk` — needed for `native_apps.c` / C modules.
- A native app: `cd apps/retro-go && rg_tool.py build <app> --target=ventilastation`
  (`<app>` = `prboom-go`, `retro-core`, `gwenesis`).
- vfs image: `python hardware/rotor/build_micropython_fs.py` — needed for any
  Python, sprite ROM, or game ROM change (including new console ROMs dropped into
  `apps/retro-go/roms/<system>/`).

Flash (board on `PORT`):
1. `make flash-vsdk PORT=<p>` — bootloader + partition table + MicroPython. Only
   needed when the partition table or a C module (`native_apps.c`) changed.
2. On a newly flashed board, `make configure-board PORT=<p>` — seed the shared
   `vs_board` NVS wiring before MicroPython or a native app uses the display or
   base-station UART. This survives later reflashes.
3. `esptool --port <p> erase_region 0xd000 0x2000` — reset OTA selection (keeps
   NVS) so it boots cleanly to MicroPython. Do after a partition-table change.
4. `rm -f apps/retro-go/partitions.bin` then
   `rg_tool.py --target=ventilastation --port=<p> flash prboom-go retro-core gwenesis`
   — flash only the apps that changed.
5. `make deploy-fs PORT=<p>` — vfs image at 0x5F0000 (or
   `deploy_micropython_fs.py --skip-build` to flash an already-built image).

Note: the board's native USB-CDC re-enumerates on every reset, so a serial
handle goes stale after a flash; if a flash reports "port busy / doesn't exist",
kill stale holders (`lsof -t /dev/cu.usbmodem*`) and/or power-cycle the board.
The `vsdk/Makefile` flash targets use a host-side `lockf` guard so concurrent
`make -j` app builds can still overlap, but only one serial flash step runs at a
time.
