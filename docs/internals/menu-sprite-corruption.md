# Main-menu sprite corruption investigation

Status as of 2026-07-24 (hardware session): **root cause found and fixed,
verified on real hardware.** Bugs #1 and #2 below were found by an earlier,
board-less static-analysis session; both are real and independently worth
having, but hardware testing showed *neither* was the reported bug — the
corruption reproduced identically before and after both fixes, on schedule,
on this board's actual active code path. See "Bug #3" below for what
actually caused it, confirmed by disabling/re-enabling the real trigger on
hardware. Kept the original bug #1/#2 writeup below since both fixes are
still correct and now hardware-verified in their own right.

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

## Bug #3 (the real cause): `setup()` double-loads the menu ROM, orphaning the buffer live sprites still point at

This board's `/roms/menu.romz` was present and no package had ever been
installed (see "Which loader path is actually active" above), so the active
loader was `_parse_rom_memory` — already GC-safe per bug #1's own caveat, and
never touching bug #2's code at all. Confirmed on hardware: the corruption
reproduced identically (clean until ~65-85s, then garbage, persisting)
*before and after* both fixes above. Same active code path, same timing —
neither fix was the story.

Diagnostic logging added to `gpu.c`'s `render()` (using `mp_printf(&mp_plat_print,
...)`, **not** `ESP_LOGD`/`ESP_LOGW` — this board's ESP-IDF console is wired
to UART0, not the USB-Serial-JTAG port the REPL/mpremote actually read, so
`ESP_LOG*` output is invisible over USB here; that's a real, separate gotcha
worth remembering for next time) showed something neither bug explains: **a
given sprite's cached `image_strip` pointer never changed address, but the
header bytes at that address changed, in two bursts roughly 60 seconds
apart** (e.g. one strip's fields went from `w=25 h=60` to garbage `w=102
h=114 pal=109`, at the *same* address, twice, 60s apart).

That 60-second period matches `system/launcher/code/__init__.py`'s
`GamesMenu`/`SystemMenu` `garbage_collect()`, a `gc.collect()` that
reschedules itself via `self.call_later(60000, self.garbage_collect)` for as
long as the menu is up. But `gc.collect()` itself isn't buggy — MicroPython's
GC is non-compacting, and a retained `memoryview` correctly anchors its
underlying buffer back through `items` (confirmed in `py/objarray.c`, matching
the note already in this doc). The real bug is upstream of that: **the menu
ROM was being loaded twice.**

`Scene.on_enter()` (`ventilastation/scene.py`) already calls
`self.load_images()` — which calls `director.load_rom(...)` — synchronously,
and `director.push()` calls `on_enter()` synchronously too. But
`system/launcher/code/__init__.py`'s `setup()` *also* scheduled
`launcher.call_later(700, launcher.load_images)` right before that same
`director.push(launcher)` call (a leftover from before `Scene.on_enter()`
loaded images automatically, never removed once it did). So `load_rom()` ran
twice: once synchronously inside `push()`, and again ~700ms later. Each call
allocates a brand-new `romdata` buffer and overwrites every entry in
`Director._stripe_buffers` to point at it — but the menu sprites created by
the *first* call had already cached their own raw pointer into the *first*
buffer (`sprite_obj_t.image_strip`, set once by `set_strip()`, never
refreshed). Once the second load ran, that first buffer dropped out of
`_stripe_buffers`/`romdata` and became unreachable — while every on-screen
sprite kept pointing at it. Nothing looked wrong yet: MicroPython's GC never
moves live data, so the orphaned buffer just sat there, unchanged, until the
periodic `gc.collect()` actually swept it and let something else's allocation
land on top — at which point every sprite still holding that stale pointer
started rendering whatever now occupied it. That's the ~65-85s and ~120s
timing, exactly.

`apps/micropython/ventilastation/browser.py`'s `boot_main()` fallback path had
the identical pattern (`main_menu.call_later(700, main_menu.load_images)`
right before `director.push(main_menu)`) and got the same fix.

**Fix:** delete both redundant `call_later(700, ...load_images)` calls; the
synchronous `on_enter()` load is sufficient and was always the one actually
used to build the initial sprites anyway.

**Verified on hardware:** with the fix applied and the periodic
`gc.collect()` left completely intact (not disabled — confirming the real
fix, not just a workaround that avoids running the collector), the menu
stayed clean through t=200s, spanning three full 60-second collect cycles.
Also re-verified bug #2's fix in isolation (forced the streaming path by
dropping `menu.romz` and pushing a plain `menu.rom`): clean through t=100s,
so that fix — and the `readinto()` conversion — are both good and worth
keeping.

## What was done on hardware (completed)

1. Flashed this branch, confirmed `/roms/menu.romz` present and no
   `/packages` installed — bug #2's path was never active on this board.
2. Reproduced on the unfixed firmware: clean to ~65s, corrupted by ~85s,
   persists. Flashed the fix branch (bugs #1+#2) and reproduced again:
   **identical timing, still broken** — neither fix was responsible.
3. Added `mp_printf`-based change-gated logging to `gpu.c`'s `render()`,
   rebuilt/flashed just the `micropython` (ota_2) app slot, captured serial
   output live through a corruption cycle. Found bug #3 (above): same
   pointer, changing content, 60s-periodic.
4. Confirmed causation two ways: (a) disabling the periodic
   `call_later(60000, garbage_collect)` alone made the corruption disappear
   through t=170s; (b) the real fix (removing the redundant `load_images()`
   call) keeps it clean through t=200s with the periodic collect left
   running normally — this is the one that shipped.
5. Re-verified bug #2's fix specifically on the forced streaming path: clean
   through t=100s.

## Also on this branch: an unrelated readinto() cleanup

Same two files also got a separate, correctness-unrelated pass converting
`.read(n)` calls that scale with content size (ROM offset tables, palette
data, per-stripe pixel data in `director.py`; the zip EOCD/central-directory
scan and per-member decompression in `vszip.py`, used by the package
installer) to `.readinto()` on a preallocated/reused buffer, per repo
convention (`.read()` allocates+copies every call; fine for small fixed
fields, wasteful for anything that scales with file content). This was
requested independently of the corruption bug, is verified via the host test
suite (`python3 tests/run_tests.py`), and is now also hardware-verified: both
loader paths (`_parse_rom_memory` via `menu.romz`, and `_load_rom_streaming`
via a forced plain `menu.rom`) loaded correctly on real hardware during this
investigation, exercising the `readinto()` conversion in both.
