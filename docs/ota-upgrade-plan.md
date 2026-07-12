# WiFi OTA Upgrade Plan

> **Superseded.** This was an early, never-implemented proposal (an A/B
> `micropython_a`/`micropython_b` partition scheme, referencing code that no
> longer exists) written before the OTA system was actually built. The real,
> live implementation — a single `micropython` (ota_2) partition, a
> permanent `factory` recovery environment, and a tier-3 hand-off instead of
> an A/B pair — is documented in `docs/internals/ota.md`. Kept here as
> design history, not as current guidance.

This document describes a safe WiFi upgrade path for the rotor firmware, the
LittleFS/VFS content partition, and native binary app partitions.

## Goals

- Updates are triggered from the `system/upgrade` MicroPython app.
- The transport works over WiFi and can be driven by the desktop emulator.
- A failed or interrupted update must still leave MicroPython usable.
- A failed native app update may leave that native app unavailable until the
  next successful update, but it must not prevent MicroPython from booting.
- File updates are incremental: unchanged VFS files are skipped.
- Binary app partitions are rewritten only when their image hash changed.
- The update process is restartable after reset, power loss, or WiFi loss.

## Current Starting Point

Useful existing pieces:

- `system/upgrade/code/__init__.py`
  - current upgrade UI shell
  - currently calls `ventilastation.sync.sync_with_server(...)`
- `apps/micropython/ventilastation/sync.py`
  - current prototype TCP sync client
  - simple `HEAD` / `PUT` file protocol
- `in-progress/sync-server.py`
  - matching host-side prototype server
- `hardware/rotor/partitions-ventilastation.csv`
  - current rotor partition layout
- `hardware/rotor/build_micropython_fs.py`
  - authoritative list of files packed into the VFS image
- `hardware/rotor/modules/native_apps/native_apps.c`
  - current MicroPython-to-native-app boot handoff
- `emulator/emu.py` and `emulator/comms.py`
  - desktop emulator entrypoint and transport layer

The current sync prototype is good enough as a sketch of the host/client
relationship, but not safe enough as an OTA boundary. It writes files directly,
does not verify files after write, does not journal a transaction, and does not
handle app partitions.

## Partition Strategy

The important product decision is:

> After any failed update, MicroPython must still boot and be able to run the
> upgrade app again.

That means MicroPython should move to an A/B layout. Native apps do not need A/B
protection initially because MicroPython is the recovery environment and can
retry those updates.

Recommended 16 MB layout, preserving current native app sizes and shrinking
`vfs` by one MicroPython slot:

```csv
# Name,          Type, SubType, Offset,   Size,     Flags
nvs,             data, nvs,     0x9000,   0x4000,
otadata,         data, ota,     0xd000,   0x2000,
phy_init,        data, phy,     0xf000,   0x1000,
micropython_a,   app,  ota_0,   0x10000,  0x260000,
micropython_b,   app,  ota_1,   0x270000, 0x260000,
prboom-go,       app,  ota_2,   0x4D0000, 0x180000,
retro-core,      app,  ota_3,   0x650000, 0x100000,
gwenesis,        app,  ota_4,   0x750000, 0x100000,
vfs,             data, fat,     0x850000, 0x7B0000,
```

This reduces VFS from `0xA10000` to `0x7B0000`, a loss of `0x260000`
bytes, exactly one MicroPython slot.

Open detail: confirm the first-flash boot behavior for a factory-less ESP-IDF
partition table. If that is awkward, use `factory` as the label for
`micropython_a` while still treating it as part of the A/B set. In that case,
native app return code still must not hardcode `factory`; it must return to the
currently selected known-good MicroPython slot.

## Native App Safety Model

Native app partitions can be updated in place from MicroPython:

- `prboom-go`
- `retro-core`
- `gwenesis`

The updater must mark a native app image invalid before erasing its partition,
then mark it valid only after the full partition image verifies.

If reset happens halfway through `retro-core`, for example:

1. MicroPython still boots from `micropython_a` or `micropython_b`.
2. The launcher sees `retro-core` as invalid or missing.
3. `system/upgrade` can run again and resume or rewrite that partition.

This deliberately avoids spending flash on A/B native app slots.

## MicroPython Safety Model

MicroPython update flow:

1. Determine the current MicroPython slot.
2. Select the other MicroPython slot as the inactive target.
3. Download/write the new MicroPython image to the inactive slot.
4. Verify the full image hash by reading flash back.
5. Mark the target slot as pending.
6. Switch boot target to the target slot.
7. Reboot.
8. New MicroPython boots, runs a small early self-check, and marks itself good.

If the update fails before step 6, the old MicroPython slot remains active. If it
fails after step 6 but before the new slot marks itself good, the boot/rollback
logic must return to the previous slot.

This needs a small hardware module exposed to MicroPython, likely extending the
existing `vshw_native_apps` idea or adding a separate `vshw_upgrade` module.

Needed operations:

- list app partitions by label, subtype, offset, size
- identify current boot partition
- identify last known-good MicroPython partition
- erase/write/read/hash a named inactive partition
- set boot partition
- mark current MicroPython slot good
- record per-partition image metadata in NVS

## VFS File Safety Model

File updates should be transaction-based. No target file is modified until all
new content for the transaction has been downloaded and verified.

Suggested on-device paths:

- `/vfs/.vsdk/current.json`
- `/vfs/.vsdk/pending.json`
- `/vfs/.vsdk/staging/<transaction-id>/...`
- `/vfs/.vsdk/partition-state.json`

Flow:

1. Server sends a manifest with file paths, sizes, hashes, and content IDs.
2. Device compares against local file hashes and existing `current.json`.
3. Device downloads changed files into staging.
4. Each staged file is verified after write.
5. Device writes `pending.json`.
6. Device renames staged files into final paths.
7. Device removes deleted files listed by the manifest.
8. Device writes `current.json` last.
9. Device removes `pending.json`.
10. Device calls `os.sync()` and reboots if needed.

On boot, MicroPython should check for a leftover `pending.json`. If present, it
should either complete the commit if all staged files verify, or discard staging
and leave the previous `current.json` in place.

## Content Budget

The smaller VFS means the packed filesystem needs a stricter default profile.

Keep in base VFS:

- `main.py`
- `ventilastation/`
- `system/launcher`
- `system/settings`
- `system/upgrade`
- `system/calibrate`
- essential shared fonts/images
- a small default set of games and ROMs

Move to optional OTA bundles:

- large game ROMs
- console ROMs under `/vfs/roms/md`, `/vfs/roms/nes`, `/vfs/roms/sms`
- rarely used MicroPython games
- large sound packs
- gallery/demo content

`hardware/rotor/build_micropython_fs.py` should grow profiles, for example:

- `base`: bootable launcher plus upgrade path
- `demo`: base plus selected bundled games
- `full`: best effort, useful for local images if it still fits

The OTA server can expose optional bundles independently of the base image.

## OTA Protocol

Replace the current ad-hoc `HEAD` / `PUT` protocol with manifest-driven sync.

Recommended request sequence:

1. Device connects to the upgrade server.
2. Device sends identity:
   - hardware model
   - partition table version
   - current MicroPython slot
   - current VFS manifest ID
   - native partition image IDs
3. Server responds with an upgrade plan:
   - files to add/update/delete
   - partition images to update
   - required free VFS space
   - minimum client/protocol version
4. Device applies files first.
5. Device applies native partitions.
6. Device applies inactive MicroPython partition last.
7. Device switches boot slot only after all required content verifies.

Each content transfer should support chunk resume:

- content ID is a sha256 hash
- chunks have offset, length, and hash
- client can ask for the next missing chunk
- server is stateless enough that reconnecting is cheap

## Server Integration With The Emulator

Move `in-progress/sync-server.py` into the emulator area as a real tool:

- `emulator/upgrade_server.py`

Add emulator entrypoints:

```sh
python emulator/emu.py --upgrade-server
python emulator/upgrade_server.py --profile demo
```

The emulator server should build its manifest from the same sources as hardware:

- VFS files from `hardware/rotor/build_micropython_fs.py`
- MicroPython image from the MicroPython build output
- native app images from Retro-Go build outputs

For local desktop testing, emulate partitions as files:

- `.emulator/partitions/micropython_a.bin`
- `.emulator/partitions/micropython_b.bin`
- `.emulator/partitions/prboom-go.bin`
- `.emulator/partitions/retro-core.bin`
- `.emulator/partitions/gwenesis.bin`

Add fault injection flags:

- disconnect after N bytes
- reset after N chunks
- corrupt one chunk
- fail during commit rename
- fail after setting pending boot slot

This lets us test interruption behavior without repeatedly flashing hardware.

## Work Plan

1. Document and land the partition-table v2.
2. Add `build_micropython_fs.py --profile base|demo|full`.
3. Add the host upgrade server under `emulator/upgrade_server.py`.
4. Replace `ventilastation.sync` with `ventilastation.upgrade_client`.
5. Update `system/upgrade` to show manifest, progress, active file/partition,
   and failure/retry state.
6. Add the MicroPython hardware upgrade module for partition operations.
7. Update native app return paths to return to the current known-good
   MicroPython slot, not hardcoded `factory`.
8. Implement VFS staging and transaction commit.
9. Implement native partition write/verify/metadata.
10. Implement MicroPython inactive-slot write/verify/boot switch.
11. Add emulator fault-injection tests.
12. Test on hardware with forced resets during each update phase.

## Rollout Recommendation

Do this in three milestones.

Milestone 1: safe VFS OTA in emulator.

- manifest server
- staged file writes
- transaction recovery
- emulator fault tests

Milestone 2: safe native app partition OTA.

- partition write module
- native partition metadata
- launcher refuses invalid native apps
- MicroPython remains bootable after interrupted native image writes

Milestone 3: MicroPython A/B OTA.

- partition table v2
- current-slot/known-good tracking
- inactive-slot write and verification
- boot switch and rollback
- native apps return to the current known-good MicroPython slot

This sequence gives useful file updates early while keeping the risky boot-slot
work isolated until the file and server machinery is already proven.
