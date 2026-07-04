# OTA Update System

Safe over-the-air updates for Ventilastation via the pyglet emulator, covering LFS
Python files, native app partition binaries, and the MicroPython firmware itself.

---

## Goals

- Update everything via WiFi, triggered from the emulator UI.
- Never leave the board unbootable after a failure or power-loss.
- Keep MicroPython usable after any failed update so a retry is possible.
- No USB cable required after the initial factory flash.

---

## Partition layout

Remove `gwenesis` (slow on this CPU) and add a `micropython` OTA slot in its place,
extended to match the `factory` size. The freed 1 MB from `gwenesis` plus the
1.375 MB net cost of replacing the 1 MB `gwenesis` slot with a 2.375 MB `micropython`
slot results in a LFS partition of 9.3 MB — only 0.75 MB smaller than the original
10 MB — which is acceptable.

### New `hardware/rotor/partitions-voom.csv`

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

Address arithmetic check (16 MB = 0x1000000):
`0x6F0000 + 0x910000 = 0x1000000` ✓

LFS = 0x910000 = 9.5 MB (was 10 MB; 0.5 MB reduction, acceptable).
`micropython` = 0x200000 = 2 MB — fits the 1.6 MB binary with 400 KB headroom.

### Roles of each partition

| Partition | Role | Ever OTA-written? |
|---|---|---|
| `factory` | Emergency MicroPython. Bootloader boots this if `otadata` is blank or ota_2 fails rollback check. | **Never** — written once over USB, then left alone. |
| `prboom-go` | Voom (prboom) binary. | Yes — OTA tier 2. |
| `retro-core` | NES / SMS emulator binary. | Yes — OTA tier 2. |
| `micropython` | Active MicroPython firmware (ota_2). Normal boot target after first flash. | Yes — OTA tier 3. |
| `vfs` | LittleFS: Python code, ROMs, user data. | Yes — OTA tier 1 (file-by-file). |

---

## First-time USB flash

After the partition table changes, the board must be flashed once over USB to establish the
new layout. Subsequent updates are WiFi-only.

A new Makefile target `make first-flash` should:

1. Flash `factory` with the current MicroPython firmware.
2. Flash `micropython` (ota_2) with the same firmware binary.
3. Write `otadata` pointing to `ota_2` as the active boot partition.
4. Flash `prboom-go` and `retro-core` with their current binaries.
5. Flash the LFS partition with the initial filesystem image.

After this, normal boot is: bootloader → `otadata` → `micropython` (ota_2) → MicroPython runs.
`factory` sits untouched as the permanent safety net.

### Native app return path change

Currently `hardware/rotor/modules/native_apps/native_apps.c` returns to `factory` after a
native app exits (via `esp_ota_set_boot_partition()` on the factory partition). After the
migration, it must return to `micropython` (ota_2) instead:

```c
// Find the "micropython" partition; fall back to factory if not present
// (handles the transition period where ota_2 hasn't been written yet).
esp_partition_t *mp = esp_partition_find_first(
    ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_ANY, "micropython");
if (!mp)
    mp = esp_partition_find_first(
        ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_APP_FACTORY, NULL);
esp_ota_set_boot_partition(mp);
esp_restart();
```

This change is backward-safe: before `make first-flash`, `micropython` partition does not
exist and the code falls back to `factory`. After `make first-flash`, it uses ota_2.

---

## Rollback protection for MicroPython

Enable `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y` in the MicroPython ESP-IDF sdkconfig.

With rollback enabled, an app image starts in `ESP_OTA_IMG_PENDING_VERIFY` state. If the
chip resets twice without the app calling `mark_app_valid_cancel_rollback()`, the
bootloader reverts to the previous valid image (i.e., `factory`).

Add the confirmation call in `apps/micropython/ventilastation/comms.py`, immediately after
WiFi connects successfully:

```python
try:
    import esp32
    esp32.Partition.mark_app_valid_cancel_rollback()
except Exception:
    pass  # not an OTA image, or already confirmed — safe to ignore
```

This means: if a new MicroPython ota_2 image cannot connect to WiFi, two reboots later the
bootloader falls back to `factory` automatically.

---

## Update protocol overview

Three tiers are always run in order within a single update session. If any tier fails, the
session aborts — whichever tiers completed successfully are done; the failed tier and
anything after it will be retried on the next session.

```
Tier 1: LFS file sync        (Python code, ROMs — file-by-file, safe)
Tier 2: Native app partitions (prboom-go, retro-core — stream + verify)
Tier 3: MicroPython firmware  (micropython ota_2 — stream + verify + set_boot)
```

---

## Emulator HTTP upgrade server

The pyglet emulator adds a lightweight HTTP server on port 8000 running in its own thread.
It is started when the emulator launches and serves build artefacts directly from the
working tree.

### Server module: `emulator/upgrade_server.py`

```
GET /manifest           → JSON manifest (see format below)
GET /files/<path>       → raw bytes, path relative to apps/micropython/
GET /partitions/<name>  → raw .bin bytes from build outputs
```

The server is started from `emulator/comms.py` alongside the existing TCP server:

```python
import upgrade_server
upgrade_server.start(port=8000)  # launches a daemon thread
```

### Manifest format

```json
{
  "version": "<git-describe or timestamp>",
  "files": [
    {"path": "ventilastation/director.py", "size": 4120, "sha256": "aabbcc..."},
    {"path": "main.py",                    "size": 312,  "sha256": "112233..."}
  ],
  "partitions": {
    "prboom-go":   {"size": 1245184, "sha256": "...", "url": "/partitions/prboom-go"},
    "retro-core":  {"size": 1048576, "sha256": "...", "url": "/partitions/retro-core"},
    "micropython": {"size": 2490368, "sha256": "...", "url": "/partitions/micropython"}
  }
}
```

The server generates this dynamically at request time: it walks `apps/micropython/` for the
file list, hashes each file, and looks for the pre-built `.bin` artefacts in
`hardware/rotor/build/` and `apps/retro-go/*/build/`.

### Triggering from the emulator UI

Add a keyboard shortcut `U` in the pyglet window (`pygletdraw.py`). Pressing it:
1. Checks that a device connection is active.
2. Determines the emulator's own IP address from the existing TCP connection's local socket.
3. Sends the comms command `ota_start http://<emulator-ip>:8000` to the device.

A new branch in `dispatch_command()` handles the reverse direction: the device sends back
`ota_progress <tier> <item> <percent>` lines that the emulator prints to the console (and
optionally displays in a status overlay).

---

## MicroPython update client

### New file: `apps/micropython/ventilastation/updater.py`

Called when the device receives `ota_start <base_url>` over the comms channel.

Persistent state in NVS namespace `"vsdk_ota"`:
- `"fw_ver"` — version string of last successful full update (string blob, max 64 bytes)
- `"prboom_sha"` — SHA256 hex of last successfully verified prboom-go (blob)
- `"retro_sha"` — SHA256 hex of last successfully verified retro-core (blob)
- `"mp_sha"` — SHA256 hex of last successfully verified micropython firmware (blob)

```python
def run(base_url):
    manifest = fetch_json(base_url + "/manifest")
    _cleanup_tmp_files()          # scan & delete any leftover .tmp from previous session
    _sync_lfs_files(base_url, manifest["files"])
    _update_partitions(base_url, manifest["partitions"])
    _send_comms("ota_done ok")
```

#### `_cleanup_tmp_files()`

Called at the start of each update session (not at boot). Walks the entire LittleFS tree,
finds any file ending in `.tmp`, logs it, and deletes it. This cleans up the debris from
any previously interrupted file-sync without adding latency to normal boot.

#### `_sync_lfs_files(base_url, files)`

For each entry in `manifest["files"]`:

1. Compute SHA256 of the local file (if it exists).
2. If it matches the manifest SHA256, skip.
3. Otherwise:
   a. Download to `<path>.tmp` (streaming, 4 KB chunks).
   b. Verify SHA256 of the downloaded `.tmp`.
   c. `os.rename("<path>.tmp", path)` — atomic on LittleFS.
   d. On any error: delete `.tmp`, log, continue to next file.

Files that fail do not abort the session — the others are still updated. The failed file
will be retried in the next session.

#### `_update_partitions(base_url, partitions)`

For each named partition in `manifest["partitions"]`:

1. Read the stored SHA256 from NVS. If it matches the manifest, skip.
2. Find the partition: `esp32.Partition.find(label=name)[0]`.
3. Erase the partition.
4. Download in 64 KB blocks, write each block immediately:
   ```python
   offset = 0
   sha = hashlib.sha256()
   while offset < size:
       chunk = fetch_chunk(url, offset, 65536)
       partition.writeblocks(offset // 512, chunk)
       sha.update(chunk)
       offset += len(chunk)
       _send_comms(f"ota_progress partition {name} {offset*100//size}")
   ```
5. Compare computed SHA256 against manifest.
6. **On mismatch**: log error, do not update NVS, continue to next partition.
   The bad partition stays on flash but MicroPython is unaffected. The native app
   will not launch correctly, but the next OTA session will overwrite it.
7. **On match**: store the SHA256 in NVS.

Partition update order: `retro-core` → `prboom-go` → `micropython`.

`micropython` is handled last with one extra step after SHA256 verification:

```python
mp_partition = esp32.Partition.find(label="micropython")[0]
mp_partition.set_boot()
_send_comms("ota_progress micropython reboot")
import machine
machine.reset()
# After reboot, comms.py calls mark_app_valid_cancel_rollback() on WiFi connect.
```

If the device resets before `set_boot()` is called, the `micropython` partition has been
written but `otadata` still points to the old image (or factory). The next OTA session
will re-download and re-write it — partition writes are idempotent.

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

## Files to create or modify

### New files

| File | Purpose |
|---|---|
| `apps/micropython/ventilastation/updater.py` | Three-tier OTA client |
| `emulator/upgrade_server.py` | HTTP server serving manifest + files + partition bins |

### Modified files

| File | Change |
|---|---|
| `hardware/rotor/partitions-voom.csv` | Add `micropython` (ota_2), remove `gwenesis`, shrink `vfs` |
| `hardware/rotor/modules/native_apps/native_apps.c` | Return to `micropython` partition instead of `factory` |
| `hardware/rotor/micropython/ports/esp32/boards/VENTILASTATION/sdkconfig` (or equivalent) | Add `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y` |
| `apps/micropython/ventilastation/comms.py` | Call `mark_app_valid_cancel_rollback()` after WiFi up |
| `emulator/comms.py` | Add `ota_start` command dispatch; import and start `upgrade_server` |
| `emulator/pygletdraw.py` | Add `U` key binding → send `ota_start` command |
| `Makefile` | Add `first-flash` target; remove `gwenesis` from flash steps |
| `apps/retro-go/partitions.csv` | Remove `gwenesis` row |
| `apps/micropython/ventilastation/native_apps.py` | Remove `native.genesis` entry from `APP_REGISTRY` |

---

## Implementation order

These are roughly ordered by dependency. Each step can be independently tested.

1. **Partition table** — update `partitions-voom.csv` and `apps/retro-go/partitions.csv`.
   Remove `gwenesis` from `APP_REGISTRY` and the Makefile. Build and USB-flash the new
   layout as `make first-flash`. Verify the board boots from ota_2 (log should show
   `"Booting from ota_2"`).

2. **Native app return path** — update `native_apps.c` to find and boot the
   `"micropython"` partition label on exit. Rebuild MicroPython. Test: launch Voom, exit,
   confirm MicroPython resumes.

3. **Rollback + confirm** — add `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y` to sdkconfig,
   add `mark_app_valid_cancel_rollback()` call in `comms.py`. Test: flash a known-bad
   ota_2 (e.g. zeroed header), confirm two reboots later the board is running `factory`.

4. **Emulator HTTP server** — implement `upgrade_server.py`. Test with `curl` from the
   host: `curl http://localhost:8000/manifest | python3 -m json.tool`.

5. **LFS file sync** — implement `updater._sync_lfs_files()` using SHA256. Test by
   modifying one Python file on the host, triggering OTA, confirming only that file is
   transferred and the device reflects the change after the session.

6. **Partition OTA (native apps)** — implement `updater._update_partitions()` for
   `prboom-go` and `retro-core`. Test by building a trivially different binary (bumped
   version string), triggering OTA, verifying the new binary is running.

7. **MicroPython OTA** — extend `_update_partitions()` for `micropython`. Test by flashing
   a build with an incremented version string, confirming `mark_app_valid_cancel_rollback()`
   is called, and that the manifest version in NVS is updated.

8. **Emulator UI** — add `U` key and `ota_progress` display in `pygletdraw.py`. End-to-end
   test: full update cycle from emulator keypress.

---

## Open questions

- **ROM storage in LFS**: at 9.3 MB the LFS can hold a few small ROMs (NES, SMS).
  Larger ROMs (MD was ~2 MB) no longer fit comfortably alongside Python code. Options:
  stream ROMs directly to retro-core at launch time rather than storing them in LFS, or
  accept that only one large ROM can be stored at a time. This is independent of the OTA
  system but the decision affects which ROMs should be listed in the file manifest.

- **Incremental partition writes**: writing a full 1.5 MB prboom-go binary over WiFi takes
  ~10–15 s at typical ESP32 TCP throughput (~1 MB/s). If this becomes a bottleneck, a
  simple binary diff (bsdiff) could be layered on top of the HTTP endpoint — the server
  diffs against the SHA256-matched previous version and the device patches in place.
  Not needed for v1.

- **Manifest signing**: nothing in this design authenticates the emulator or the manifest.
  Acceptable for a local-network dev workflow. If the board is ever on an untrusted network,
  add an HMAC over the manifest using a shared secret stored in NVS.
