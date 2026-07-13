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

`hardware/rotor/partitions-ventilastation.csv`:

```
# Name,        Type, SubType, Offset,   Size
nvs,           data, nvs,     0x9000,   0x4000
otadata,       data, ota,     0xD000,   0x2000
phy_init,      data, phy,     0xF000,   0x1000
factory,       app,  factory, 0x10000,  0x200000
prboom-go,     app,  ota_0,   0x210000, 0x180000
retro-core,    app,  ota_1,   0x390000, 0x100000
micropython,   app,  ota_2,   0x490000, 0x200000
vfs,           data, fat,     0x690000, 0x970000
```

| Partition | Role | Ever OTA-written? |
|---|---|---|
| `factory` | **Permanent recovery environment** (see below) — not a write-once bootstrap copy. | **Never** — the only USB-writable partition besides NVS; `make flash-recovery` is the bring-up procedure. |
| `prboom-go` | Voom (prboom) binary. | Yes — OTA tier 2. |
| `retro-core` | NES / SMS emulator binary. | Yes — OTA tier 2. |
| `micropython` | Active MicroPython firmware (ota_2). Normal boot target once installed. | Yes — OTA tier 3, via a hand-off through `factory` (see below). |
| `vfs` | LittleFS: Python code, ROMs, user data. | Yes — OTA tier 1 (file-by-file). |

### `factory` is a permanent recovery environment, not a one-time bootstrap copy

Earlier versions of this design treated `factory` as a write-once copy that
migrated to `micropython` (ota_2) on first boot and was never touched again.
That's no longer the model: `factory` is the board's **permanent fallback**,
reached whenever there's no working `micropython` yet, a bad update failed
to prove itself, or a running system needs to hand off a firmware update it
can't safely perform on itself (a running image can never overwrite the
partition it's executing from).

Bring-up is now `make flash-recovery` (see `hardware/rotor/flash_recovery_image.py`):
USB-flashes only bootloader + partition table + `factory`, then provisions
NVS (`vs_board` wiring, `devel_wifi` credentials) if not already present —
read-first, so re-running it doesn't clobber an already-configured board
(pass `FORCE=1` to overwrite). Everything else — `vfs`, the native apps, and
the real `micropython` copy — installs over WiFi via recovery's own retry
loop, never USB. `make flash-vsdk` still writes both `factory` and
`micropython` over USB, but it's a bench-dev convenience now, not the
bring-up procedure.

The vendored MicroPython source tree is unmodified for this: `apps/micropython/boot.py`,
a frozen module, is picked up automatically by the stock
`pyexec_file_if_exists("boot.py")` call in `main.c`. Its only job is to
guarantee some `main.py` exists — if `vfs` has none at all (a fresh board),
it writes a minimal bootstrap stub (`import vsdk_recovery; vsdk_recovery.run()`)
and returns immediately. It deliberately does **not** call recovery
directly: `main.c`'s `mp_usbd_init()` (which activates the USB CDC device
the REPL/Ctrl-C need) only runs *after* `boot.py` returns, so a long-running
call there would starve it forever — confirmed on hardware as a real,
if brief, regression during development. The actual factory-vs-normal
decision lives in `main.py` itself (the stub, or the real one), exactly
where it ran before this redesign: whenever the board is running from
`factory` — a fresh board via the stub, a bootloader rollback, or a
deliberate hand-off — `main.py`'s own top-of-file check runs
`apps/micropython/vsdk_recovery.py`: shows the boot logo, connects WiFi from
`devel_wifi`, and loops calling the same three-tier updater used for
in-place OTA (below) against `http://ventilastation-base.local:5653` — the
base is discovered via mDNS, not a hardcoded IP, so no NVS URL provisioning
is needed for that step. `boot.py`/`vsdk_recovery.py`/`updater.py`/
`vsdk_logo_strip.py` are frozen at the top level (not nested under the
`ventilastation` package) specifically so they work even with `vfs`
completely empty. Once recovery succeeds, tier-1 OTA file sync overwrites
the bootstrap stub with the real, field-updatable `main.py`.

Rollback: `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y` is set for the
MicroPython build. A freshly OTA'd `micropython` image boots in the
bootloader's pending-verify state; `main.py` only calls
`esp32.Partition.mark_app_valid_cancel_rollback()` once the main loop has
genuinely ticked for ~10 real seconds (gated on `Director.step_once()`, not
a bare sleep, so a hang counts the same as a crash), fed by a `machine.WDT`
armed before that point. An image that never confirms — because it hangs or
crashes — leaves the bootloader's rollback state alone; **empirically
confirmed on this board** (2026-07-12) that after exactly two such
unconfirmed boots, the bootloader reverts the boot target to `factory`,
which then resumes its normal recovery retry loop.

---

## Trigger and boot mode

An OTA session is requested over the **serial host link** (the same
line-based command channel that carries sprites/sound — from the base, the
workbench UART bridge, or the desktop emulator):

```
ota_start http://<host-ip>:5653
```

The desktop emulator sends this when you press **U** in the pyglet window
(`emulator/pyglet2x/pygletdraw.py` → `comms.trigger_ota()`). With a TCP
workbench connection it uses that connection's local interface; with a direct
serial board connection it discovers the host's default LAN/Wi-Fi address, so
the serial control link and Wi-Fi OTA server work together. Its
`upgrade_server` (below) is already listening on port 5653.

On a computer with several active networks, specify the address reachable by
the board explicitly:

```sh
python emu.py SERIAL --serial-port /dev/tty.usbserial-144220 --ota-host 192.168.1.42
```

The device does **not** run the update inline: the GPU task and WiFi both
use the SPI bus, and running them concurrently crashes the core. Instead
`director._dispatch_control()` writes the URL to `/ota_request` and resets
the board. Early in the next boot — before `ensure_runtime()` starts the
GPU task — `main.py` sees `/ota_request`, deletes it, and runs
`apps/micropython/updater.py` (frozen at the top level, not nested under
`ventilastation/`) in isolation:

1. Connect WiFi using NVS namespace `devel_wifi` (keys `ssid`/`password`),
   provisioned once per board with
   `make wifi-provision PORT=... WIFI_SSID=... WIFI_PASS=...`
   (`tools/provision_wifi.py`). No credentials → `ota_error`, normal boot.
2. Fetch `GET /manifest`, run the three tiers (below).
3. Disconnect WiFi (if the updater brought it up) and reset into the
   updated system.

This same `updater.py` also runs **automatically**, without any
`ota_start`/`/ota_request` trigger, whenever the board is running from
`factory` (see above) — `vsdk_recovery.py` calls it directly in a retry loop
against the mDNS-discovered base URL. The two entry points share all the
same tier logic; the only difference is what triggers a run.

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

`emulator/upgrade_server.py` runs on port 5653 in a daemon thread, started
by `emulator/comms.py` alongside the display connection. It can also run
standalone (`python3 emulator/upgrade_server.py --bundle <dir> --port 5653`),
serving a fixed pre-built layout instead of computing everything live from
dev build-output paths — for a production base Pi that doesn't have the
ESP-IDF/Retro-Go toolchain installed. Build that bundle directory with
`tools/package_release.py --output <dir>` (reuses this same module's
manifest/file-read logic, so the bundle always matches a live dev-loop OTA
exactly).

`start()` also advertises `ventilastation-base.local` over mDNS itself
(via the `zeroconf` package, in `requirements.txt`), restricted to this
machine's actual LAN interface — registering on every interface (the
`zeroconf` default) causes some clients to intermittently pick an
unreachable duplicate. This matters specifically for the desktop dev loop:
a production Raspberry Pi base gets `<hostname>.local` for free from Avahi
once its OS hostname is set to `ventilastation-base`, but a dev machine's
own Bonjour name is whatever its computer name already is, so without this
the emulator would bind the port fine but never actually be reachable at
that hostname. If `zeroconf` isn't installed, `start()` logs a warning and
continues without advertising (the server still works for anything that
reaches it by IP directly).

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

`apps/micropython/updater.py` (frozen at the top level, not nested under
`ventilastation/` — it must keep working even with `vfs` completely empty,
since recovery depends on it). Persistent state in NVS namespace
`"vsdk_ota"`: `prboom_sha`, `retro_sha`, `mp_sha` — the SHA256 of the last
successfully verified write of each partition, so unchanged binaries are
skipped without downloading.

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
if the NVS-stored SHA256 matches the manifest (a missing/never-set hash
counts as "differs"); otherwise erase, stream in 4096-byte blocks, verify
SHA256, store the hash in NVS. A mismatch leaves NVS unchanged (retried next
session).

The partition currently executing is never written directly — for
`prboom-go`/`retro-core` that's simply skipped for this pass (the board is
presumably running the other one, or `factory`). For `micropython`
specifically, a running image can never safely overwrite the partition it's
booted from, so instead of skipping forever, it **hands off to `factory`**:
finds the `factory` partition, calls `set_boot()`, and resets — without
writing anything to `micropython` yet. The next boot runs recovery from
`factory` (where `running != "micropython"`), which re-fetches the manifest
and this time reaches the normal write path above safely. This is what
actually lets `micropython` itself get OTA-updated at all, and is also
exactly how a merely-stale-but-not-broken `micropython` gets upgraded, not
just a crashed one.

When a fresh `micropython` write does complete directly (i.e. running from
`factory`, not via the hand-off above), it calls `set_boot()` and resets;
the new image confirms itself via `mark_app_valid_cancel_rollback()` in
`main.py` (after ~10s of real ticks — see the rollback section above), or
the bootloader rolls back to `factory`.

---

## Failure / interruption safety matrix

| Failure point | State after reset | Recovery |
|---|---|---|
| WiFi drops mid LFS sync | `.tmp` files on device; old files intact | Next session: `_cleanup_tmp_files()` removes `.tmp`; re-downloads changed files |
| Power loss during LFS write | `.tmp` file partially written; old file intact (rename never happened) | Same as above |
| Power loss during partition block write | Partition contains partial image; MicroPython unaffected | Next session: re-downloads and re-writes entire partition |
| SHA256 mismatch after partition write | NVS not updated; partition is suspect | Next session: NVS hash differs from manifest → full re-download |
| Power loss after `set_boot()`, before `mark_app_valid_cancel_rollback()` | `micropython` pending-verify; two reboots without confirm → bootloader reverts to `factory` (empirically confirmed) | `factory` runs recovery automatically, no user action needed |
| Bad `micropython` binary passes SHA256 (not expected) | Same as above — rollback activates | `factory` covers it, automatically |
| `micropython` stale but not broken, board currently running it | Tier-3 hand-off: `set_boot(factory)` + reset, no write yet | `factory`'s recovery pass re-fetches the manifest and completes the write safely |
| `factory` itself corrupted (extremely unlikely — the only USB-writable app partition, and never OTA-written) | Brick — requires USB flash (`make flash-recovery`) | Prevented by `factory` never being an OTA target |

---

## Key files

| File | Role |
|---|---|
| `apps/micropython/updater.py` | Three-tier OTA client (also the only WiFi user on the board); tier-3 hand-off to `factory` |
| `apps/micropython/vsdk_recovery.py` | Permanent recovery environment: logo, WiFi, retry loop calling `updater.py` against the mDNS-discovered base |
| `apps/micropython/boot.py` | Frozen; picked up by stock (unmodified) `main.c`. Guarantees `main.py` exists (writes a bootstrap stub if not); the factory-vs-normal decision itself lives in `main.py` |
| `apps/micropython/vsdk_logo_strip.py` | Hand-authored logo `ImageStrip`, frozen alongside recovery |
| `apps/micropython/main.py` | WDT + deferred rollback confirm, factory→recovery branch, `/ota_request` boot mode |
| `apps/micropython/ventilastation/director.py` | `ota_start` dispatch → `/ota_request` + reset |
| `emulator/upgrade_server.py` | HTTP server: manifest + files + partition bins; `--bundle <dir>` mode for production base deployment |
| `emulator/comms.py` | Starts `upgrade_server`; `trigger_ota()` sends `ota_start` |
| `hardware/rotor/build_micropython_fs.py` | Single source of truth for the LFS file set (USB image *and* OTA manifest) |
| `hardware/rotor/flash_recovery_image.py` / `make flash-recovery` | Bring-up procedure: USB-flash `factory` + NVS only, everything else over WiFi |
| `tools/package_release.py` | Assembles a fixed bundle directory for `upgrade_server.py --bundle` |
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
