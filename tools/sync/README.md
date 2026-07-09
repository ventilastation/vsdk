# File sync (dormant)

Host side of the on-device `ventilastation/sync.py` file-sync client and the
`system/upgrade` app. This flow predates the three-tier OTA updater
(`ventilastation/updater.py` + `emulator/upgrade_server.py`) and is kept for
future resurrection, not currently wired into any Makefile target.

- `sync-server.py` — serves a folder tree over TCP port 9000; the client
  compares per-file MD5 hashes and downloads what changed.
- `sample-sync.sh` — example of pushing `sync.py` to a board with `mpremote`
  and running a sync.
