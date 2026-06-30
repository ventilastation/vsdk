# Ventilastation on-device design

How the spinning ESP32-S3 board is partitioned, how MicroPython and the native
retro-go apps share configuration, and how each is launched. Companion to
`EMULATOR_AUDIO_PLAN.md` (emulator audio bridge).

## 1. Flash layout (16 MB)

The board runs **two firmwares**: MicroPython (the Ventilastation menu + Python
games) in the `factory` partition, and several **native retro-go apps**, each in
its own OTA app partition. They share one LittleFS data partition (`vfs`).

Defined in `hardware/rotor/partitions-voom.csv`:

| Partition | Type        | Offset    | Size      | Holds |
|-----------|-------------|-----------|-----------|-------|
| nvs       | data/nvs    | 0x9000    | 0x4000    | shared config (see §2) |
| otadata   | data/ota    | 0xd000    | 0x2000    | which OTA app boots |
| phy_init  | data/phy    | 0xf000    | 0x1000    | RF cal |
| factory   | app/factory | 0x10000   | 0x260000  | **MicroPython** |
| prboom-go | app/ota_0   | 0x270000  | 0x180000  | Voom (Doom) |
| launcher  | app/ota_1   | 0x3F0000  | 0x100000  | retro-go launcher |
| gwenesis  | app/ota_2   | 0x4F0000  | 0x100000  | **Mega Drive emulator** |
| vfs       | data/fat\*  | 0x5F0000  | 0xA10000  | LittleFS: code, sprite ROMs, game ROMs |

\* labelled `fat` historically; the content is LittleFS, mounted at `/` by
MicroPython and at `/vfs` by retro-go (`RG_STORAGE_ROOT`).

Booting another app = `esp_ota_set_boot_partition(target)` + reboot. On exit the
native apps set the boot partition back to `factory`, returning to the
MicroPython menu.

## 2. Shared configuration in NVS (single source of truth)

Config that must outlive firmware/filesystem reflashes and be read by **both**
firmwares lives in **NVS** (its own flash partition, never erased by app or vfs
flashing). There are no more `wifi_config.json` / `settings.json` files.

| Namespace  | Key          | Type | Written by | Read by |
|------------|--------------|------|------------|---------|
| `voom_wifi`| `ssid`       | blob | `tools/dev_deploy.py` (`mpremote run`) | MicroPython `comms.py`, prboom-go/gwenesis `wb_init` |
| `voom_wifi`| `password`   | blob | `tools/dev_deploy.py` | same |
| `voom_pov` | `col_offset` | i32  | MicroPython `settings.py` (POV calibration) | prboom-go / gwenesis `ventilastation_pov.c` |
| `voom_md`  | `rom`        | blob | MicroPython `native_apps.py` (before launch) | gwenesis `main.c` |

Notes:
- **WiFi**: set once with `make dev-deploy WIFI_SSID=... WIFI_PASS=...`, which
  runs a tiny script on the board writing `voom_wifi`. `comms.py` reads it, with
  a hardcoded default network as last resort. Survives every reflash.
- **POV calibration** (`pov_column_offset`): `settings.py` reads/writes
  `voom_pov`/`col_offset` directly, the exact key the native POV driver reads —
  no copy step. On desktop (no `esp32` module) settings fall back to in-memory
  defaults.
- **Mega Drive ROM path**: see §3.

## 3. Launching native apps from MicroPython

The MicroPython menu (`system/launcher`) lists native apps by slug. Selecting one
runs `native_apps.py` → `vshw_native_apps.launch(<name>)`
(`hardware/rotor/modules/native_apps/native_apps.c`), which maps the name to a
partition, sets it as the OTA boot partition, and reboots.

Registry (`native_apps.c`): `voom`→prboom-go, `launcher`→launcher,
`gwenesis`→gwenesis.

Menu slugs (`native_apps.py` `APP_REGISTRY`):
- `native.voom` → Voom (fixed WAD, no ROM arg)
- `native.genesis` → Mega Drive; carries a `rom` path
- `native.launcher` → retro-go launcher (**currently disabled** in the menu: its
  text is unreadable at the POV display's resolution)

**Handing the Mega Drive emulator its ROM.** The retro-go launcher normally
passes a ROM path via its `bootArgs`/settings, but that path uses a
sentinel-namespaced config file that is awkward to write from MicroPython. Since
the launcher is disabled, MicroPython instead writes the ROM path to NVS
`voom_md`/`rom` just before launching, and `gwenesis/main.c` reads it when no
`bootArgs` is present:

```
main menu "Mega Drive"
  → native_apps.py writes voom_md/rom = "/vfs/roms/md/OutRun (USA, Europe).zip"
  → vshw_native_apps.launch("gwenesis")  (OTA → gwenesis, reboot)
  → gwenesis main.c: app->romPath empty → read voom_md/rom → load ROM
```

Genesis ROMs live in `apps/retro-go/roms/md/` (gitignored) and are copied into
the vfs image at `/roms/md/` by `build_micropython_fs.py` (extensions
`md gen bin zip`, scoped to that folder). gwenesis loads `.zip` directly.

## 4. Compressed sprite ROMs

MicroPython sprite ROMs (`apps/micropython/roms/*.rom`, generated from PNGs by
`tools/generate_roms.py`) are palette-indexed image data and compress ~85% with
deflate. `build_micropython_fs.py` stores each as **`<name>.rom.gz`** (gzip) in
the vfs image; `director.py` finds the `.gz` file and inflates it with the
board's `deflate` module, parsing it in RAM. Repo `.rom` files stay
uncompressed, so the desktop/web emulators are unaffected. This freed ~2.4 MB of
the vfs partition — enough to add the gwenesis app partition and Genesis ROMs.

## 5. Emulator audio bridge

The native emulators have no DAC on the spinning board. They stream their sound
chip register writes over the 115200 UART to the base-station host, which
re-synthesizes the audio. See `EMULATOR_AUDIO_PLAN.md`.

## 6. Build & flash

Rebuild after changes:
- MicroPython (`factory`): `make vsdk` — needed for `native_apps.c` / C modules.
- A native app: `cd apps/retro-go && rg_tool.py build <app> --target=ventilastation`.
- vfs image: `python hardware/rotor/build_micropython_fs.py` — needed for any
  Python, sprite ROM, or game ROM change.

Flash (board on `PORT`):
1. `make flash-vsdk PORT=<p>` — bootloader + partition table + MicroPython.
2. `esptool --port <p> erase_region 0xd000 0x2000` — reset OTA selection (keeps
   NVS) so it boots cleanly to MicroPython.
3. `rm -f apps/retro-go/partitions.bin` then
   `rg_tool.py --target=ventilastation --port=<p> flash prboom-go launcher gwenesis`.
4. `make deploy-fs PORT=<p>` — vfs image at 0x5F0000.
