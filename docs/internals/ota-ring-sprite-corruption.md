# OTA ring sprite corruption — hand-off

Status as of 2026-07-26: **not fixed, not yet verified on hardware.** Root
cause below is from static code reading only (no logging added, no fix
flashed) — it is a strong, specific lead, not a confirmed diagnosis. Verify
on hardware before trusting it. See
[ota-progress-rings-plan.md](ota-progress-rings-plan.md) for the original
feature request this is blocking, and [ota.md](ota.md)'s "On-device
progress display" section for how the feature is meant to work end to end.

## The symptom

`vsdk_ota_rings.py` (see [ota.md](ota.md)) renders OTA progress as
concentric single-LED rings via `vshw_vs2` sprites. On real hardware,
during an actual partition write, the rings that should be clean
concentric bands instead show a chaotic patch of random-colored single-LED
noise speckles — not a coherent ring at all — localized to part of the
arc, with the rest of the arc showing clean bands. Screenshots from the
2026-07-26 hardware session (captured via the workbench, see
[workbench.md](workbench.md) and `tools/pov_screenshot.py`) showed this
consistently across multiple captures during the same partition-write OTA;
the user independently flagged it from the screenshots without seeing this
doc first ("the sprites might have been replaced with any other memory
content") — that description is exactly right, see below.

![Corrupted ring during a partition write — noise speckle at the top of an otherwise clean set of concentric bands](../images/ota-ring-glitch-1.png)
![A second capture from the same OTA session, same pattern at a different ring radius](../images/ota-ring-glitch-2.png)

This is very likely **the same bug shape already investigated and fixed
once before in this codebase**, in a different file:
[menu-sprite-corruption.md](menu-sprite-corruption.md)'s "Bug #1" and
"Bug #3". Read that doc first — it has the debugging technique and the
exact fix pattern this bug almost certainly also needs.

## Root cause (strong lead, not yet hardware-confirmed)

`vshw_sprites.set_imagestrip()` (native, `hardware/rotor/modules/povdisplay/
sprites.c`) stores only the raw C pointer extracted from whatever Python
buffer object it's given — it never keeps the owning `mp_obj_t` alive (this
is documented in `sprites.c` and is exactly what
[menu-sprite-corruption.md](menu-sprite-corruption.md)'s Bug #1 already
describes for `director.py`). If nothing on the Python side retains that
buffer object, MicroPython's GC is free to reclaim and reuse its memory
later, while the sprite's cached `image_strip` pointer keeps pointing at
it — and the next `render_vs2()` draws whatever now occupies that address.

`vsdk_ota_rings.py`'s `_set_ring()` (line ~181) does exactly this:

```python
_sprites.set_imagestrip(_STRIP_SLOT[name], _build_ring_strip(name, row))
```

`_build_ring_strip()` returns a freshly allocated `bytes` object built
inline as a call argument. Nothing stores it anywhere — `_row[name]` only
tracks the row *number*, not the buffer. As soon as `set_imagestrip()`
returns, that `bytes` object has zero references and is immediately
GC-eligible.

`director.py`'s fix for the identical problem was a module-level
`self._stripe_buffers = {}` dict, keyed by slot number, populated
alongside every `set_imagestrip()` call, specifically to keep a live Python
reference for as long as the slot is in use. `vsdk_ota_rings.py` has no
equivalent — there is no dict anywhere in the module that roots a strip
buffer.

**This is not a "might eventually get collected" risk — it's
near-immediate and deterministic**, because `updater.py`'s own partition
write loop calls `gc.collect()` explicitly, once per HTTP chunk, in the
exact same loop that calls into the ring functions:

```python
def write_chunk(chunk):
    ...
    if block_pos == _BLOCK:
        part.writeblocks(offset // _BLOCK, block_buf)
        ...
        vsdk_ota_rings.pulse_partition_activity()        # <- builds + sets a fresh, unrooted strip
        vsdk_ota_rings.set_partition_progress(done_blocks, total_blocks)  # <- and another one

for pct in _http_stream(url, write_chunk, size):
    _progress("writing", name, pct)
    gc.collect()   # <- runs right after write_chunk(), while the strip(s) just set have zero refs
```

(`apps/micropython/updater.py`, `_update_partitions()`.) This lines up
exactly with the symptom: the corrupted screenshots were all captured
during a partition write (the gray/yellow rings), which is the one phase
with an explicit `gc.collect()` sitting immediately after the ring update
call. The file-sync loop (`_sync_lfs_files()`, white/green rings) has no
equivalent per-chunk `gc.collect()` in its download loop — only before
hashing a file that needs re-verification — so it may be less reliably
affected, or affected on a longer delay; that's a prediction to check on
hardware, not something already confirmed either way.

## Suggested fix (not implemented, not tested)

Mirror `director.py`'s pattern in `vsdk_ota_rings.py`: add a module-level
dict that roots each slot's current buffer for as long as it's in use,
e.g.

```python
_strip_buffer = {}  # name -> bytes, keeps set_imagestrip()'s buffer GC-rooted

def _set_ring(name, row):
    ...
    built = _build_ring_strip(name, row)
    _strip_buffer[name] = built          # keep alive before/alongside the native call
    _sprites.set_imagestrip(_STRIP_SLOT[name], built)
    sprite.set_frame(0)
    sprite.set_flags(_VS2_FLAG_VISIBLE)
```

Total footprint: 5 ring slots × `WIDTH * PIXELS` bytes (256×54 = 13,824)
plus a 4-byte header ≈ 68 KB worst case, all five held at once — cheap on
this board.

After applying, re-run the same kind of hardware test that reproduced the
bug (see below) and confirm the rings render as clean, stable bands
through a real partition write, not just briefly after each update. If
they still glitch, don't assume this was the whole story — go straight to
the debugging technique in
[menu-sprite-corruption.md](menu-sprite-corruption.md)'s "Bug #3" section
before spending time on other theories: add `mp_printf(&mp_plat_print, ...)`
logging (**not** `ESP_LOGD`/`ESP_LOGW` — this board's ESP-IDF console is
wired to UART0, not the USB-Serial-JTAG port the REPL/mpremote actually
reads, so `ESP_LOG*` output is invisible over USB here, a gotcha that cost
real time last time) in `gpu.c`'s `render_vs2()` to print each ring
sprite's cached `image_strip` pointer plus header fields
(`frame_width`/`frame_height`/`palette`) on change, and watch for the same
signature as before: a stable address whose *content* changes underneath
it.

## How to reproduce on hardware

This uses the workbench rig — see [workbench.md](workbench.md) for how it
taps the DUT's LED bus and re-streams it over Wi-Fi, and
`tools/pov_screenshot.py --help` for the capture tool itself.

1. Force a real partition write so the gray/yellow rings actually run
   long enough to capture: pick a **safe, currently-inactive** partition —
   `prboom-go`, `retro-core`, or `fmsx`, whichever the board is *not*
   currently booted from (check with
   `mpremote exec "import esp32; print(esp32.Partition(esp32.Partition.RUNNING).info()[4])"`
   first) — and erase it, e.g.
   `esptool.py --port <port> erase_region <offset> <size>` for that
   partition's entry in the partition table CSV, or corrupt a few bytes.
   **Never erase the partition reported as `RUNNING`** — that bricks the
   board's current boot target; this happened once already this session
   and was recovered via `make flash-full`, see `ota.md`'s history/git log
   if the details matter.
2. Optionally also drop a stale/wrong entry into `/.vsdk_lfs_cache.json`
   or corrupt a couple of small LFS files if you also want to exercise the
   white/green file-sync rings in the same run.
3. Trigger the OTA exactly once, then go hands-off: `mpremote` always
   sends Ctrl-C on connect, which can interrupt an in-progress OTA if you
   run another `mpremote exec` to "check on it" mid-flight (this cost real
   time earlier this session — don't do it). The working pattern:
   - One `mpremote exec` call that writes `/ota_request` (or whatever
     currently triggers the in-place path in `main.py` — check
     `_check_ota_boot()`) and returns.
   - Then an explicit `esptool.py ... --after hard_reset run` (or just let
     the board's own hardware reset happen) — do **not** issue a further
     `mpremote` command after this until the test is over.
   - Then run a passive, non-interrupting observer: a plain pyserial
     reader (no Ctrl-C, reconnect-on-drop) is safer than repeated
     `mpremote` calls for watching boot logs live.
4. While that runs, repeatedly call
   `python3 tools/pov_screenshot.py --no-launch --out <path>.png` (no
   `--slug`/launch — this just captures whatever the display is currently
   showing) every second or two, across the whole OTA. Expect ~20-30
   captures for a partition write that takes tens of seconds.
5. Inspect the captures for: clean concentric bands (fixed) vs. localized
   noise speckle within an otherwise-clean ring (still broken — the
   speckle is real corrupted content, not just the capture method's
   normal cross-revolution smearing artifact, which produces stepped/
   doubled bands rather than per-pixel random color noise).

## Files involved

| File | Role |
|---|---|
| `apps/micropython/vsdk_ota_rings.py` | Where the fix goes — `_set_ring()`, needs a buffer-rooting dict |
| `apps/micropython/updater.py` | Calls into the ring functions; the `gc.collect()` in `_update_partitions()`'s write loop is what makes this reproduce almost immediately rather than eventually |
| `hardware/rotor/modules/povdisplay/sprites.c` | `set_imagestrip()` — the native call that only stores a raw pointer |
| `hardware/rotor/modules/povdisplay/gpu.c` | `render_vs2()` — where a stale pointer would actually get drawn; add diagnostic logging here if the buffer-rooting fix alone isn't enough |
| `docs/internals/menu-sprite-corruption.md` | The prior investigation of the same bug shape in a different file — read this first |
