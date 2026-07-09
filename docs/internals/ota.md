# OTA Update System

Safe over-the-air updates for Ventilastation, covering LFS files (Python
code, sprite ROMs, game assets), native app partition binaries, and the
MicroPython firmware itself.

This is also the fast dev loop for real hardware: the device skips every
file whose SHA256 already matches, so after the one-time USB flash you can
test a code change on the spinning fan in seconds — no stopping the fan,
no cover removal, no USB cable.

---

## Goals

- Update everything via WiFi, triggered over the serial host link.
- WiFi is **only** up during an OTA session — the board never joins a
  network at boot (WiFi and the GPU task fight over the SPI bus; see
  "Trigger and boot mode" below).
- Never leave the board unbootable after a failure or power-loss.
- Keep MicroPython usable after any failed update so a retry is possible.
- No USB cable required after the initial factory flash.

---

## Partition layout

`hardware/rotor/partitions-voom.csv`:

```
# Name,        Type, SubType, Offset,   Size
nvs,           data, nvs,     0x9000,   0x4000
otadata,       data, ota,     0xD000,   0x2000
phy_init,      data, phy,     0xF000,   0x1000
factory,       app,  factory, 0x10000,  0x260000
prboom-go,     app,  ota_0,   0x270000, 0x180000
retro-core,    app,  ota_1,   0x3F0000, 0x100000
micropython,   app,  ota_2,   0x4F0000, 0x200000
vfs,           data, fat,     0x6F0000, 0x910000
```

| Partition | Role | Ever OTA-written? |
|---|---|---|
| `factory` | Emergency MicroPython. Bootloader boots this if `otadata` is blank or ota_2 fails rollback check. | **Never** — written once over USB, then left alone. |
| `prboom-go` | Voom (prboom) binary. | Yes — OTA tier 2. |
| `retro-core` | NES / SMS emulator binary. | Yes — OTA tier 2. |
| `micropython` | Active MicroPython firmware (ota_2). Normal boot target after first flash. | Yes — OTA tier 3. |
| `vfs` | LittleFS: Python code, ROMs, user data. | Yes — OTA tier 1 (file-by-file). |

`make flash-vsdk` writes the MicroPython image to both `factory` and
`micropython` (ota_2). On any boot where `main.py` finds itself running from
`factory` (first boot, or after a native app handed control back via the
factory partition), it switches the boot partition to `micropython` and
resets, so OTA updates never touch `factory`.

Rollback: `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y` is set for the
MicroPython build. `main.py` calls
`esp32.Partition.mark_app_valid_cancel_rollback()` first thing at boot; if a
freshly OTA'd ota_2 image can't get that far, two resets later the
bootloader reverts to `factory`.

---

## Trigger and boot mode

An OTA session is requested over the **serial host link** (the same
line-based command channel that carries sprites/sound — from the base, the
workbench UART bridge, or the desktop emulator):

```
ota_start http://<host-ip>:8000
```

The desktop emulator sends this when you press **U** in the pyglet window
(`emulator/pyglet2x/pygletdraw.py` → `comms.trigger_ota()`), deriving the
URL from its own IP on the connection's interface. Its `upgrade_server`
(below) is already listening on port 8000.

The device does **not** run the update inline: the GPU task and WiFi both
use the SPI bus, and running them concurrently crashes the core. Instead
`director._dispatch_control()` writes the URL to `/ota_request` and resets
the board. Early in the next boot — before `ensure_runtime()` starts the
GPU task — `main.py` sees `/ota_request`, deletes it, and runs
`ventilastation/updater.py` in isolation:

1. Connect WiFi using NVS namespace `devel_wifi` (keys `ssid`/`password`),
   provisioned once per board with
   `make wifi-provision PORT=... WIFI_SSID=... WIFI_PASS=...`
   (`tools/provision_wifi.py`). No credentials → `ota_error`, normal boot.
2. Fetch `GET /manifest`, run the three tiers (below).
3. Disconnect WiFi (if the updater brought it up) and reset into the
   updated system.

```
Tier 1: LFS file sync         (full LittleFS content — file-by-file, safe)
Tier 2: Native app partitions (prboom-go, retro-core — stream + verify)
Tier 3: MicroPython firmware  (micropython ota_2 — stream + verify + set_boot)
```

Progress is reported back over the comms channel as
`ota_progress <stage> <detail> <pct>`, completion as `ota_done ok`, errors
as `ota_error <message>`.

---

## Emulator HTTP upgrade server

`emulator/upgrade_server.py` runs on port 8000 in a daemon thread, started
by `emulator/comms.py` alongside the display connection.

```
GET /manifest           → JSON manifest (see format below)
GET /files/<path>       → file bytes, path as it appears on the device
GET /partitions/<name>  → raw .bin bytes from build outputs
```

### Manifest = the LFS image, exactly

The file manifest reuses `hardware/rotor/build_micropython_fs.py`'s
`iter_copy_jobs()` — the same walker that builds the USB-flashed LittleFS
image — so OTA and USB deploys can never drift apart. It covers `main.py`,
`ventilastation/`, sprite ROMs, Doom WADs, console ROMs, `games/` and
`system/`, with the same skip rules. Sprite `.rom` files get the same
deterministic gzip transform as the image and appear as `.rom.gz`.

```json
{
  "files": [
    {"path": "ventilastation/director.py", "size": 4120, "sha256": "aabbcc..."},
    {"path": "games/alecu/vyruss/code/__init__.py", "size": 9311, "sha256": "..."},
    {"path": "roms/menu.rom.gz", "size": 68210, "sha256": "..."}
  ],
  "partitions": {
    "prboom-go":   {"size": 1245184, "sha256": "...", "url": "/partitions/prboom-go"},
    "retro-core":  {"size": 1048576, "sha256": "...", "url": "/partitions/retro-core"},
    "micropython": {"size": 2490368, "sha256": "...", "url": "/partitions/micropython"}
  }
}
```

Partition binaries are picked up from `apps/retro-go/*/build/` and the
MicroPython ESP32 build directory; absent binaries are simply omitted from
the manifest. Hashes (and the gzipped ROM payloads) are cached keyed on the
source file's mtime+size, so repeated manifests only re-hash what changed.

---

## MicroPython update client

`apps/micropython/ventilastation/updater.py`. Persistent state in NVS
namespace `"vsdk_ota"`: `prboom_sha`, `retro_sha`, `mp_sha` — the SHA256 of
the last successfully verified write of each partition, so unchanged
binaries are skipped without downloading.

### Tier 1 — `_sync_lfs_files()`

For each manifest file entry: compute SHA256 of the local file; if it
matches, skip (this is what makes the dev loop fast — an unchanged tree
transfers nothing). Otherwise stream to `<path>.tmp`, verify SHA256, then
`os.rename()` — atomic on LittleFS. Failures skip to the next file and are
retried next session. `_cleanup_tmp_files()` removes stale `.tmp` debris at
the start of each session. Files deleted from the host tree are *not*
deleted on the device; reflash the filesystem (`make deploy-fs`) for that.

### Tiers 2–3 — `_update_partitions()`

For each partition in `retro-core`, `prboom-go`, `micropython` order: skip
if the NVS-stored SHA256 matches the manifest; otherwise erase, stream in
4096-byte blocks, verify SHA256, store it in NVS. A mismatch leaves NVS
unchanged (retried next session) and never touches MicroPython. The
partition currently executing is never written.

`micropython` goes last: after verification it calls `set_boot()` and
resets; the new image confirms itself via `mark_app_valid_cancel_rollback()`
in `main.py`, or the bootloader rolls back to `factory`.

---

## Failure / interruption safety matrix

| Failure point | State after reset | Recovery |
|---|---|---|
| WiFi drops mid LFS sync | `.tmp` files on device; old files intact | Next session: `_cleanup_tmp_files()` removes `.tmp`; re-downloads changed files |
| Power loss during LFS write | `.tmp` file partially written; old file intact (rename never happened) | Same as above |
| Power loss during partition block write | Partition contains partial image; MicroPython unaffected | Next session: re-downloads and re-writes entire partition |
| SHA256 mismatch after partition write | NVS not updated; partition is suspect | Next session: NVS hash differs from manifest → full re-download |
| Power loss after `set_boot()`, before `mark_app_valid_cancel_rollback()` | ota_2 pending-verify; two reboots without confirm → bootloader reverts to `factory` | `factory` runs; user triggers OTA again |
| Bad ota_2 binary passes SHA256 (not expected) | Same as above — rollback activates | `factory` covers it |
| `factory` itself corrupted (shouldn't happen — never OTA-written) | Brick — requires USB flash | Prevented by the "never write factory" rule |

---

## Key files

| File | Role |
|---|---|
| `apps/micropython/ventilastation/updater.py` | Three-tier OTA client (also the only WiFi user on the board) |
| `apps/micropython/main.py` | Rollback confirm, factory→ota_2 migration, `/ota_request` boot mode |
| `apps/micropython/ventilastation/director.py` | `ota_start` dispatch → `/ota_request` + reset |
| `emulator/upgrade_server.py` | HTTP server: manifest + files + partition bins |
| `emulator/comms.py` | Starts `upgrade_server`; `trigger_ota()` sends `ota_start` |
| `hardware/rotor/build_micropython_fs.py` | Single source of truth for the LFS file set (USB image *and* OTA manifest) |
| `tools/provision_wifi.py` / `make wifi-provision` | One-time `devel_wifi` NVS provisioning |

---

## Open questions

- **Deletions**: tier 1 never deletes device files that vanished from the
  host tree. Harmless for the dev loop (stale `.py` files may shadow moves,
  though); a `deleted` list in the manifest would close it.
- **Incremental partition writes**: writing a full 1.5 MB prboom-go binary
  over WiFi takes ~10–15 s at typical ESP32 TCP throughput (~1 MB/s). If
  this becomes a bottleneck, a binary diff (bsdiff) could be layered on top
  of the HTTP endpoint. Not needed for v1.
- **Manifest signing**: nothing in this design authenticates the server or
  the manifest. Acceptable for a local-network dev workflow. If the board
  is ever on an untrusted network, add an HMAC over the manifest using a
  shared secret stored in NVS.
