# Main-menu sprite corruption investigation

Status as of 2026-07-24: two real bugs found and fixed by static analysis and
host-side tests only. **Neither fix has been verified on hardware yet** —
that's the point of this doc. Written for handoff to a session that has a
board attached.

## The symptom

On the main MicroPython menu (the Director's home screen — app icons for
Voom/NES/SMS/GB/MSX), after some time sitting idle, all the sprites start
showing up positioned and sized wrong, with pixel content that looks like
it's reading from an unrelated area of memory. Input still works; only the
sprite rendering is wrong.

Reported timing: consistently ~70-75 seconds after landing on the menu.

Confirmed by the reporter across two follow-ups in this investigation:

- Happens on a cold boot straight to the menu — **launching Voom first is
  not required**. This rules out anything specific to voom's exit path or to
  retro-go/prboom-go.
- Does *not* reproduce after exiting a NES game — but that returns to a
  different screen (the ROM browser for that console), not the Director's
  top-level menu, so this doesn't clear the menu-specific code paths below.
- Has been happening for **at least a week** — i.e. predates today's
  retro-go POV-decouple and hall-pulse-filter work. Those are a completely
  separate runtime (the retro-go C launcher / `ventilastation_pov.c`, used by
  voom/NES/SMS/GB/MSX) from what's actually affected (the MicroPython
  `Director`'s own menu, rendered through `hardware/rotor/modules/povdisplay/
  gpu.c`). Don't re-chase that avenue.

## Dead ends (already ruled out, don't re-check these)

- **retro-go's `ventilastation_pov.c`** (fb_a/fb_b double buffering, hall
  filter, `vs_exit_fade_active`) — wrong runtime entirely; only applies to
  voom/NES/SMS/GB/MSX, not the MicroPython Director menu. The `vs_exit_*`
  fade flags there are real dead code (never reset) but are only reachable
  from the workbench "reset"/"exit" wire command, not the normal exit path.
- **Motor/disc speed control** — there is no software PWM/speed control for
  the spinning disc anywhere in the tree; the physical RPM isn't
  app-dependent, so nothing to "settle" after a game exits.
- **WiFi reconnect backoff** — `rg_network.c`'s disconnect handler retries
  immediately, no backoff timer that could land around 70s.
- **`menurom.py`'s `refresh_from_packages()`** — runs once at boot only, not
  periodic.
- **`director.py`'s `INPUT_TIMEOUT`/`self.timedout`** (30s idle → intended
  "how-to-play attract screens") — computed but has zero consumers anywhere
  in the tree. Dead/unimplemented feature, not an active scene-push that
  could be reloading ROM data mid-session.
- **`shuffler.py`** — generic Fisher-Yates array shuffle, unrelated.

## Bug #1 (fixed, but probably not the active one): GC lifetime of stripe/palette buffers

`vshw_sprites.set_imagestrip()` and `vshw_povdisplay.set_palettes()` (native
modules, `hardware/rotor/modules/povdisplay/sprites.c` /
`povdisplay.c`) store only the raw C pointer extracted from whatever Python
buffer object they're given — they never keep the owning `mp_obj_t` alive.
If nothing on the Python side retains that object, MicroPython's GC is free
to reclaim and reuse the memory later, while `image_stripes[]`/`palette_pal`
keep pointing at it.

`director.py`'s ROM loaders (`_load_rom_streaming`, `_parse_rom_memory`) were
passing buffers into these calls without retaining a reference anywhere.
Fixed by adding `self._stripe_buffers = {}` (keyed by slot number, never
cleared wholesale) in `Director.__init__`, populated at both call sites.

**Caveat discovered afterwards:** `_parse_rom_memory` (used when
`roms/menu.romz` — the gzip-compressed form — exists) turns out to have
already been safe before this fix, because MicroPython's GC traces pointers
in any reachable `memoryview` back to their owning heap block (confirmed
both by reading `py/objarray.c`'s header comment and by an empirical test
under the local `micropython` unix port — see scratch history if needed,
not preserved). So this fix mattered only for `_load_rom_streaming`, and
**only if `roms/menu.romz` is absent** — see "which loader is actually
active" below.

This fix alone was reported back as **not sufficient** — the glitch still
happened at ~70-75s after applying it. See bug #2.

## Bug #2 (fixed, more likely the real one): type confusion in `_load_rom_streaming`

`_load_rom_streaming` was building `stripmap`/`palette_data` as plain
`bytes` objects (via slicing + `+` concatenation, and `file.read()`), then
passing them straight into `set_imagestrip()`/`set_palettes()`. Those native
functions read their argument by casting it to `mp_obj_array_t*` and
computing `items + free` for the data pointer.

`free` is only a valid element offset for a real `memoryview`/`bytearray`.
For a plain `bytes`/`str` object, that identical struct slot (same offset by
design — see `py/objstr.h`'s `MP_STATIC_ASSERT_STR_ARRAY_COMPATIBLE`) holds
the object's **hash**, not an offset. And MicroPython does *not* leave that
lazily at zero here: `py/objstr.c`'s `mp_obj_new_str_type_from_vstr()` —
the function behind both slicing and `+` concatenation — eagerly computes
`o->hash = qstr_compute_hash(data, len)` for every new bytes object. So the
native code was adding a essentially-arbitrary hash-shaped value in as a
byte offset, reading pixel/header/palette data from the wrong address
outright — independent of GC timing, which fits "positioned/sized wrong,
reading the wrong area of memory" better than bug #1 does.

Fixed by wrapping both `stripmap` and `palette_data` in `memoryview(...)`
before they reach the native calls, in `apps/micropython/ventilastation/
director.py`'s `_load_rom_streaming`.

**This fix has not been tested on hardware at all yet.** It's the one to
prioritize verifying.

## Which loader path is actually active — check this first

`director.load_rom()` prefers `roms/menu.romz` (gzip) when present, which
uses `_parse_rom_memory` (the path that was already safe). It falls back to
plain `roms/menu.rom` via `_load_rom_streaming` (the path with bug #2) when
`.romz` is missing.

Per `menurom.py`'s own docstring: **installing any game package deletes
`roms/menu.romz` and replaces it with a plain `roms/menu.rom`**
(`merge_icon_into_menu` → `_write_menu_rom(..., drop_romz=True)`). If this
board has ever had a package installed, it's on the streaming path — which
is exactly why this has been reproducing for "at least a week."

**First thing to check on hardware:** does `/roms/menu.romz` exist right
now? (`import os; os.stat("/roms/menu.romz")` over the REPL/mpremote — if it
raises `OSError`, the streaming path — and bug #2 — is what's actually been
running.)

## A pre-existing partial mitigation that's still a gap

`hardware/rotor/modules/povdisplay/gpu.c`'s `render()`, in the per-sprite
draw loop:

```c
const ImageStrip* is = s->image_strip;
if ((uintptr_t)is < 1000) {
  // ESP_LOGD(TAG, "BUG en gpu render=%p", s);
  ...
  continue;
}
```

This guard (present since very early history, unrelated to this
investigation) only catches a suspiciously-small/null-ish pointer. It does
**not** catch a stale pointer that's been reused by some other legitimate,
normal-looking heap object — which is exactly the failure mode both bugs
above produce. If the glitch still reproduces after both fixes, temporarily
un-commenting the `ESP_LOGD` lines there (and adding one for the `else`
branch, i.e. every sprite actually drawn, logging `is->frame_width`/
`is->frame_height`/`is->palette`) is the fastest way to catch a bad pointer
live and see what it's pointing at.

## What to do on hardware, in order

1. Flash this branch (`investigate/menu-sprite-corruption`).
2. Check whether `/roms/menu.romz` exists on the board's filesystem (see
   above) — tells you whether bug #2 was even in play.
3. Reproduce: cold boot, sit on the main menu untouched for 90+ seconds,
   watch for the corruption.
4. If fixed: also try forcing a package install (or check if one's already
   installed) to confirm the streaming path specifically is now clean, since
   that's the path that had bug #2.
5. If still broken: enable the `gpu.c` logging described above and capture
   what a corrupted sprite's `image_strip` pointer/fields actually look like
   when it happens — that'll tell us whether it's a third bug or a gap in
   these two fixes.
6. Also worth trying as a diagnostic (not a fix): does forcing
   `platform.disable_gc = True` (skips `gc.enable()`/`gc.collect()` in
   `Director.__init__`, see `platforms/hardware.py`) change the timing or
   make it disappear? That would isolate whether GC-driven reuse (bug #1's
   class of problem) is still contributing versus it being purely the
   pointer-arithmetic bug (#2).

## Also on this branch: an unrelated readinto() cleanup

Same two files also got a separate, correctness-unrelated pass converting
`.read(n)` calls that scale with content size (ROM offset tables, palette
data, per-stripe pixel data in `director.py`; the zip EOCD/central-directory
scan and per-member decompression in `vszip.py`, used by the package
installer) to `.readinto()` on a preallocated/reused buffer, per repo
convention (`.read()` allocates+copies every call; fine for small fixed
fields, wasteful for anything that scales with file content). This was
requested independently of the corruption bug and is verified via the host
test suite (`python3 tests/run_tests.py`) and a couple of throwaway
MicroPython-unix-port smoke tests (not preserved in the repo), but — like
everything else in this doc — **not yet run against real hardware.**
