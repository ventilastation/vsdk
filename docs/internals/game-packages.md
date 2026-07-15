# Game packages (.vs2): build, push, install

How a single game travels from the web editor (or a dev checkout) to a
running console, without a full OTA sync. One zip per game; the base keeps
it zipped and decompresses only what each consumer needs.

Status: implemented on branch `feature/game-packages`; host-side fully
covered by tests; the hardware validation checklist at the bottom has not
been run on a real board yet.

## The two files

**Package** — `<group>.<name>.vs2`, a plain zip built by
`tools/package_game.py` or the web editor (`web/package-builder.js`):

| Member | Zip method | Notes |
|---|---|---|
| `meta.json` | DEFLATE | launcher manifest, unchanged schema (`ventilastation/catalog.py`) |
| `menu.png` | DEFLATE | icon source, for editor/gallery display |
| `code/**.py` | DEFLATE | entry point `code/<name>.py` with `main()` |
| `roms/<group>.<name>.rom` | DEFLATE | compiled sprite rom — the single source of truth for images; PNG sources do not travel (the editor will round-trip ROM→PNG) |
| `menu-icon.rom` | DEFLATE | one-strip rom (strip id `<group>/<name>/menu.png` + its palette); merged into the board's menu rom at install time |
| `sounds/*.mp3` | STORE | played by the base, never sent to the board |

**Stripped package** — `<group>.<name>.no-sound.vs2`, derived on demand by
the base (`emulator/package_manager.py`). Member paths are device paths
minus the leading `/`, except `menu-icon.rom` which is consumed by the
merger rather than extracted:

| Member | Zip method |
|---|---|
| `games/<g>/<n>/meta.json`, `games/<g>/<n>/code/**.py` | DEFLATE |
| `roms/<slug>.rom.gz` (gzip -9, mtime 0 — the board cannot compress) | STORE |
| `menu-icon.rom` | DEFLATE |

## Flow

```
editor "Push to console"            tools/package_game.py + curl
        \                            /
         POST /packages/<slug>.vs2  (base stores installed_packages/<slug>.vs2)
                    |
                    |  base: audio rescan (sounds play straight from the zip
                    |  via a build/base/sound_cache), stripped file built
                    |  lazily into build/base/board_files/
                    v
         POST /packages/<slug>/install
                    |
                    |  comms.trigger_install: sends over serial
                    |  "install_start <url> <sha256> <size>"
                    v
    board director._dispatch_control writes /install_request, machine.reset()
                    |
                    |  main.py _check_install_boot() — before the GPU task
                    |  starts (WiFi and GPU share the SPI bus)
                    v
    ventilastation/installer.run(): WiFi up (frozen updater helpers),
    fetch the one file, SHA256 verify, keep it at
    /packages/<slug>.no-sound.vs2, install_from_file(), WiFi down, reset
```

`install_from_file()` stages everything under `/games/<g>/.<n>.new/` first,
then — the upgrade path — deletes any existing `/games/<g>/<n>/` and stale
rom variants, renames the staging dir and rom into place, and merges
`menu-icon.rom` into the menu rom. Progress mirrors the OTA family:
`install_progress <stage> <detail> <pct>`, `install_done <slug>`,
`install_error <msg>` (relayed into `/packages/<slug>/status` by
`emulator/comms.py`).

## Menu rom merging (board-side)

The launcher renders all icons from one monolithic rom and
`director._parse_rom_memory()` clears strips on every load, so installed
games' icons must live inside `roms/menu.rom`. `ventilastation/menurom.py`
splices each package's icon strip + palette in (replace-by-name on
re-install, unreferenced palettes garbage-collected). Because the board
cannot gzip and `director.load_rom()` prefers `menu.rom.gz`, the merged rom
is written plain and the `.gz` is deleted — and the `.gz` reappearing after
a system OTA is exactly the re-merge signal: `main.py` calls
`menurom.refresh_from_packages()` at boot, which rebuilds the merged rom
from the icon roms stored in `/packages/*.no-sound.vs2` (no network
needed). `ventilastation/menu.py` falls back to a generic strip if an icon
is ever missing instead of crashing the menu.

## OTA interplay (by design)

- Packages are **not** part of the system OTA: `installed_packages/` sits
  outside every `iter_copy_jobs()` root, so the manifest never includes
  them, and tier-1 never deletes board files, so installed games survive
  OTAs. A full USB vfs reflash does wipe them — reinstall from the base.
- For a game that also exists in the repo tree (the vyruss_vs2 pilot),
  tier-1 OTA re-syncs the tree's `code/` over a newer pushed package on
  the board. Expected during migration; resolved by removing migrated
  games from the tree.

## Base endpoints (emulator/upgrade_server.py, port 5653)

- `POST /packages/<slug>.vs2` — upload (validated by
  `package_manager.validate_package`); triggers an audio rescan.
- `GET /packages` — JSON list with meta titles and install status.
- `GET /packages/<slug>.vs2` / `GET /packages/<slug>.no-sound.vs2` — the
  stored package / the derived board file.
- `POST /packages/<slug>/install` — sends `install_start` to the board.
- `GET /packages/<slug>/status` — `uploaded → triggered → serving →
  installing → done|error` (poll; the board reboots mid-flow, that's
  normal).
- `GET /api/listdir?path=games/...` — tree listing for the editor's sound
  collection.
- Any other GET serves the **web editor** from `web/` (same-origin pushes;
  a GitHub-Pages HTTPS editor cannot POST to this plain-HTTP server). The
  push button only appears when the probe of `/packages` succeeds.
- `/manifest`, `/files/`, `/partitions/` unchanged.

The Pi base now runs with the server enabled
(`hardware/base/base-remote.sh` dropped `--no-ota-server`).

## Building a package without the editor

```
python3 tools/package_game.py alecu/vyruss_vs2          # → dist/alecu.vyruss_vs2.vs2
curl -X POST --data-binary @dist/alecu.vyruss_vs2.vs2 \
     http://ventilastation-base.local:5653/packages/alecu.vyruss_vs2.vs2
curl -X POST http://ventilastation-base.local:5653/packages/alecu.vyruss_vs2/install
curl http://ventilastation-base.local:5653/packages/alecu.vyruss_vs2/status
```

## Tests

All in `tests/run_tests.py`: `test_vszip.py`, `test_menurom.py`,
`test_installer.py`, `test_install_dispatch.py` (CPython, board modules),
`test_package_game.py` (CLI on the real vyruss_vs2, byte-identical
rebuilds), `test_package_server.py` (live HTTP), `test_package_builder_zip.mjs`
(the editor's zip writer read back by CPython zipfile), and
`test_installer_micropython.py` (the whole board path under the MicroPython
unix port — this one caught that `deflate.DeflateIO(..., RAW)` needs an
explicit `wbits=15`).

## Hardware validation checklist (not yet run)

Prereqs: workbench + DUT attached (`make list-boards`), WiFi provisioned in
NVS (`make wifi-provision`), repo on `feature/game-packages` with `.venv`.

1. **Sync the board to this branch.** All board-side changes are
   vfs-resident (`main.py`, `ventilastation/*`), so a normal tier-1 OTA is
   enough: run the desktop emulator against the board and press Ctrl-U
   (or `make dev-emulator BOARD_IP=...`). Wait for `ota_done ok` + reboot.
2. **Pilot install (upgrade path).** `python3 tools/package_game.py
   alecu/vyruss_vs2`, then the three curls above against the machine
   running the emulator (`http://localhost:5653`). Watch the emulator
   console for `install [downloading] ...`, `install_done alecu.vyruss_vs2`.
   The board reboots twice (into install mode, then after install).
   - Menu must still show Vyruss VS2 with its icon (the merged menu rom).
   - `mpremote fs ls :/packages` shows `alecu.vyruss_vs2.no-sound.vs2`;
     `:/roms` has `alecu.vyruss_vs2.rom.gz` and a plain `menu.rom` (no
     `menu.rom.gz` anymore).
   - Game plays; shoot/explosion sounds come from the base ("Loaded N
     sounds from package ..." in the emulator log after upload).
   - This exercises LittleFS **directory rename** (staging → final). If
     install_error mentions rename, that's risk #5 from the plan — fall
     back to per-file extract+rename in `installer.install_from_file`.
3. **Fresh-install path.** Package a slug that is *not* in the tree (e.g.
   copy `games/alecu/mapdemo` to `games/alecu/mapdemo2`, `package_game
   alecu/mapdemo2`, delete the copy) and install it: a brand-new
   `/games/alecu/mapdemo2` must appear in the menu with its icon.
4. **OTA re-merge.** Ctrl-U again (tree OTA restores `roms/menu.rom.gz`).
   After the post-OTA reboot the console must print
   `main: menu rom re-merged from installed packages` and installed icons
   must still render. Note vyruss_vs2's `code/` is re-synced from the tree
   (expected for an in-tree pilot).
5. **Editor push.** Open `http://localhost:5653/` (the served editor) in a
   browser, open a game, press **Push to console**; the status line should
   walk upload → install → done and the game should appear on the fan.
6. **Watch for**: boot loops (must never happen — `/install_request` is
   deleted before the installer runs; a failed install continues to normal
   boot), `install_error no_space` (statvfs guard), palette count growth on
   repeated re-installs of the same game (must stay constant), and RAM
   headroom during the menu merge (whole rom in RAM, ~120 KB today).
