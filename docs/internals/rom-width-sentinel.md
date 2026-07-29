# Retiring the ROM width sentinel (`255` means `256`)

Status as of 2026-07-28: **planned, not implemented.** This file records the
audit that found the problem, the encoding decision and why the alternatives
were rejected, and the sequenced work order. [rom-format.md](rom-format.md)
remains the normative spec and still documents the current behaviour; it gets
updated in step 5 below, not before.

## The problem

A strip record's four attribute bytes are `(width, height, frames, palette)`,
where `width` is the *per-frame* width. 256 does not fit in a byte, so
`tools/generate_roms.py` clamps `width > 255` to `255` and roughly fourteen
consumer sites across four runtimes reinterpret it:

```python
width = 256 if w == 255 else w
```

So `255` is simultaneously a legal width and a sentinel for `256`. Any strip
that is genuinely 255 pixels wide is read as 256 — one column too many, on
every frame.

This is not theoretical. It is live in two shipped game ROMs.

## The audit

Run against all 34 built ROMs in `apps/micropython/roms/`. The check is that a
record's byte span must exactly equal its declared content:

```python
# for each strip record n at offset `off`:
name_len   = data[off]
w, h, fr   = data[off+1+name_len : off+4+name_len]
real_width = 256 if w == 255 else w
record_end = strip_offsets[n+1] if n+1 < num_strips else palette_offsets[0]
leftover   = record_end - (off + 1 + name_len + 4 + real_width * h * fr)
# leftover must be 0, or exactly the glyph trailer
```

`leftover` was non-zero for 31 of 475 records, in four distinct classes.

### Class 1 — genuinely 255px wide (2 records): out-of-bounds read

| ROM | Strip | PNG | Payload | Readers compute | Over-read |
|---|---|---|---|---|---|
| `vsjam-oct25.2bam_sencom.rom` | `warning.png` | 255×8, 1 frame | 2040 B | 256×8×1 = 2048 B | **8 bytes** |
| `vsjam-may25.ventrack.rom` | `menuInstrumento.png` | 255×10, 1 frame | 2550 B | 256×10×1 = 2560 B | **10 bytes** |

Both PNGs are genuinely 255 wide — confirmed from the IHDR, and neither
declares a `frames:` count. The renderers address pixels as
`base = visible_column * h + frame * w * h` with `w = 256` and
`visible_column` reaching 255, and `sprites.c`'s `set_imagestrip()` stores a
bare pointer with no length, so on hardware this renders whatever follows the
strip in memory as pixels.

### Class 2 — `frames` clamped at 255 (21 records): silent content loss

`generate_roms.py` does `if frames > 255: frames = 255` with **no** sentinel
and no compensating fixup anywhere. Every 256-frame font therefore loses its
last glyph. Affected: `vga_cp437.png` (×5 ROMs), `rainbow437.png` (×4),
`vga_pc734.png`, `letras_edrev/sirg/celeste.png`,
`horizon/noziroh/rainbow/wobniar/steel/leets8x8.png`, `tinyfont_red.png`,
`tinyfont_white.png`.

This matters more than it looks: `rainbow437.png` is the CP437 default font for
the `vs2.Label` API, and `Label._glyph()` returns `EMPTY_TILE` when
`ord(char) >= image.frames`, so `chr(255)` renders blank.

**A "frames 255 means 256" sentinel would have been wrong from day one.**
`other.rom`/`tinyfont_menu.png` has a genuine 255 frames — its payload is
exactly `4 × 6 × 255 = 6120` bytes. 255 frames is a live, correct value.

### Class 3 — floor-truncated width (8 records)

`width = i.width // frames` truncates when the sheet width is not a multiple of
the frame count, so the header under-describes the payload: `pollitos.png`
(256/5 → 51, in both `menu.rom` and `other.rom`), `font8_top.png`,
`font8_bottom.png` (512/63 → 8), `red/yellow/white_numerals.png` (48/10 → 4),
`FallingTembacSmall.png` (42/4 → 10).

### Class 4 — glyph-trailer misfire (29 records)

The optional V2 glyph trailer is located by record-boundary inference. Classes
1–3 make that leftover non-zero, so `glyph_length` gets decoded out of pixel
bytes. It is benign **only by luck**: on every affected record the two bytes
read as `0xFFFF` (or `0xFF43`) because the truncated leftover columns happen to
be transparent, and the `glyph_length <= trailer_size - 2` guard then rejects
them. A leftover column with a non-transparent low byte would pass that guard
and inject a garbage glyph string into `director.image_metadata`.

### Consumers that never apply the fixup at all

Three, and all of them feed collision math:

- `hardware/rotor/modules/povdisplay/sprites.c:111` — `uint8_t width()` returns
  `frame_width` raw. Note the return type: it could not hold 256 even if fixed.
  Reached from `sprite_collision()` (`:147`) and exported to game code as V1
  `sprite.width()` (`:182`), which games call constantly for centering.
- `apps/micropython/ventilastation/emu_sprites.py:51` — desktop *and* browser.
- `apps/micropython/ventilastation/platforms/headless.py:93` (raw branch).

Meanwhile `vs2_native.c:242` *does* apply it. The codebase is inconsistent
about its own rule, which is the structural argument for the fix below.

## Decision: bias-by-one on `width` and `frames`

Store `value - 1`. Byte `0..255` means `1..256`. No special case survives.

```
attrs = (width - 1, height, frames - 1, palette)   # record stays 4 bytes
width  = byte + 1                                  # every consumer, uniformly
frames = byte + 1
```

**Why the header must stay 4 bytes.** Its size is load-bearing in five
independently-engineered places, each with a comment explaining itself:

- the zero-copy `(const ImageStrip*)` casts in `sprites.c:66` and
  `emulator/native/emu_bridge.c:88`;
- `director.py`'s `bytearray(4 + width*h*frames)` construction, whose comment
  documents the MicroPython eager-hash trap;
- `menurom.py`'s `_with_palette`, which does `patched[4 + patched[0]]` and runs
  **on the board**;
- `vsdk_ota_rings.py`'s hand-built headers on the **recovery path**, which must
  work with an empty vfs and is the least testable code in the repo.

**Why a byte is the right size, not a stopgap.** 256 is the true maximum, not
an arbitrary cutoff — `COLUMNS == 256` in all three renderers, and the frame
index is a `uint8_t` in `sprite_obj_t.frame` and in the 5-byte wire sprite
record. A biased byte spans exactly `1..256`; a `u16` would be permanent dead
weight bought at the price of the five items above.

**Why `frames` too.** Class 2 is the more damaging bug today, and bias also
subsumes the existing "frames byte 0 is read as 1" convention — so the
scattered defensive `frames or 1` fallbacks get *deleted* rather than becoming
a second special case.

**Why `height` is deliberately NOT biased.** It has no ambiguity to remove, and
`pycamp-mar25.vong.rom`/`barra_punto.png` uses byte 255 legitimately, so
biasing would silently remap the top of a live range. Height is also the
multiplier in the addressing arithmetic — a missed `+1` on width clips a
column, a missed `+1` on height corrupts addressing. Leaving exactly one raw
field is what makes the compile-time sweep in step 1 work: afterwards
`frame_height` is the only field readable raw, and its *name* says so.

### Alternatives rejected

- **Widen `width` to `u16`.** Explicit and future-proof, but changes the record
  size — see the five load-bearing sites above. It breaks the recovery path for
  a one-bit problem.
- **Forbid a 255px width.** No format change, but the ambiguity survives (byte
  255 still means 256), the rule stays copy-pasted in fourteen places, the three
  no-fixup consumers stay permanently wrong, and it does nothing for `frames`.
  It also requires re-cutting two games' existing art.
- **Zero-means-256** (`store width % 256`). Attractive as a
  minimum-migration option: only 2 of 256 encodings change meaning, so legacy
  widths `1..254` stay bit-identical and both mismatch directions degrade
  benignly. Rejected because it is still a special case, and it cannot be
  applied to `frames` — byte 0 already means 1 frame there. Worth remembering
  as the safe retreat if the rebuild cost in step 4 ever proves unacceptable:
  it is the only option that is memory-safe without a version marker.

### No version marker; rebuild everything

The container has no magic or version field, and none is being added.

The consequence must be stated plainly: under bias-by-one a stale ROM decodes
as `(w+1) × h × (f+1)`, which is **always strictly larger than its payload**, so
every stale strip over-reads — turning today's two-record problem into an
every-record one. **This is why the step 0 bounds guard is load-bearing rather
than defence-in-depth, and why it must land before the encoding flip.** With it,
a stale ROM degrades to a clipped or garbled draw instead of an OOB read.

Accepted residue: a board's previously-installed `.vs2` packages render one
pixel narrow until reinstalled. Nothing in `installer.py` or `meta.json`
changes. `games/vsjam-oct25/2bam_sencom/code/2bam_sencom.py:1304` — a fifth,
in-game container parser — reads only `palette_offsets[0]` and is unaffected, so
no jam-game code is touched.

## Work order

Each step is independently verifiable.

### Step 0 — safety net (no format change; shippable alone)

**0a.** `tests/test_rom_format.py:39` currently asserts
`pixels_start + pixels_len <= len(data)`, which bounds only against the *file*
end — which is exactly why a strip overrunning into the *next strip* passed.
Replace with the record-exact assertion
`record_len == 1 + name_len + 4 + w*h*f + 2 + glyph_len`. Over the built ROMs
this catches all four classes at once. Add a temporary allowlist of the 31
known-bad records; it empties in step 3.

**0b.** C bounds guard. Add `extern size_t image_strip_lengths[NUM_IMAGES];`
beside `image_stripes[]` in `sprites.h`. Populate in both `set_imagestrip`
impls — `sprites.c:66` already holds the `mp_obj_array_t*` via
`memoryview_data()`, so `mv->len` is right there; `emu_gpu_set_image_strip()`
takes a new length parameter (its only caller is
`native_render.set_image_strip`, driven from `povrender.py:340`). Clamp
`base + offset` in `gpu.c`'s three draw loops. Test with a guard byte after a
strip whose header over-declares its payload: render every column, assert the
canary is intact.

**0c.** Fix the three no-fixup consumers *under the current rule*.
`sprites.c:111-117` — change `width()` **and** `height()` to return `int`;
`uint8_t` cannot hold 256, and under bias it would wrap to 0, strictly worse
than today's 255. Callers are already safe (`intersects()` takes `int`;
`sprite_width`/`sprite_height` wrap in `mp_obj_new_int`). Then
`emu_sprites.py:51` and `headless.py:93`, and route
`emulator/scene_shader.py:249` through `povrender._strip_header` instead of
re-decoding `raw[:4]`.

> **Behavioural risk to audit here.** V1 `.width()` on a planet backdrop goes
> 255 → 256, and `intersects(x1, 256, x2, w2)` is unconditionally true — a
> 256-wide sprite collides with everything. At 255 it was very-nearly-always
> true, so this is close but not identical. Check the `.width()` callers that
> can receive a fullscreen strip, notably `2bam_sencom.py:195,235,240,267,520,525,990,1006`.

### Step 1 — one decode helper per runtime (no output change)

Verified by ROMs hashing identically before and after.

- **C:** rename `ImageStrip.frame_width` → `frame_width_minus_1` and
  `total_frames` → `total_frames_minus_1` in `sprites.h`, leaving
  `frame_height` alone, and add `static inline int strip_frame_width(...)` /
  `strip_total_frames(...)`. The rename turns every raw read into a **compile
  error** — `gpu.c` ×3, `vs2_native.c`, `sprites.c`, and
  `tests/native/test_render_vs2.c` — so none can be missed. This is the
  highest-value item in the plan: it converts "remember the rule" into "the
  compiler won't let you forget".
- **MicroPython:** new `ventilastation/romformat.py` (`decode_header`,
  `encode_header`, `pixel_length`, `record_length`), routed through
  `director.py` (both parsers), `menurom.py`, `platforms/browser.py`,
  `vs2/__init__.py` `_strip_metadata`, `emu_sprites.py`, `headless.py`.
  **Sanctioned exception:** `vsdk_ota_rings.py` must stay vfs-independent and
  must not import it — keep its literals, rename `_WIDTH_BYTE` →
  `_WIDTH_MINUS_1`, cross-reference this doc, and add the missing range guard
  to `_build_label_strip` (raises a bare `ValueError` at 64+ characters today).
- **Desktop:** `povrender._strip_header` is already the `id()`-cached choke
  point — one line.
- **Web:** `app-support.js`'s `decodeImageStripPayload` is the single choke
  point. Change it there, then **delete** the now-provably-dead re-widenings in
  `led-render-core.js` (×2) and `scene-shader-core.js`. Their presence is what
  makes the rule look like it belongs in the renderer.

### Step 2 — flip the encoding

Both builders together: `generate_roms.py` emits
`(width - 1, height, frames - 1, palette)`, `web/rom-builder-core.js` mirrors
it. Update `romformat.py`, `_strip_header`, `decodeImageStripPayload`, the
`sprites.h` inline accessors, and the `vsdk_ota_rings.py` literals. Make the
glyph trailer **mandatory** (always write the `u16`, even when zero) so record
size is self-describing rather than inferred — this kills class 4 outright.

### Step 3 — producer hard errors and content fixes

Replace the silent clamps in `generate_roms.py` with errors that **name the
offending file**: `frames` outside `1..256`, `width` outside `1..256`,
`i.width % frames != 0`, and an explicit height check so `bytes(attrs)` cannot
raise a bare `ValueError: bytes must be in range(0, 256)` with no filename.
Note `width = i.width // frames` is currently computed **twice** — once into
`attributes[fn]`, which is never read back for the emitted width, and again at
the write site; collapse it.

Mirror every check in `web/rom-builder-core.js`. Then fix what the new errors
surface: declare `frames: 256` for the 21 class-2 fonts and correct the 8
class-3 declarations. Step 0a's allowlist should now be empty.

**Also close the JS builder's glyph gap.** `parseStripedefsYaml` hard-rejects
`glyphs:` via `^(frames|radius|id):`, so the browser IDE and
`generate_roms_js.cjs` **currently cannot build `alecu/vyruss_vs2` or
`alecu/vixeous` at all**. Accept the key, carry it through
`normalizeStripedefItem`, and emit the trailer in `buildRom`.

### Step 4 — make the change actually propagate

`generate_roms.py` skips regeneration when every source mtime is older than the
ROM, so a format change alone rebuilds **nothing**. This trap is currently
active — it is why no built ROM carries the glyph trailer despite two games
declaring one. Add `Path(__file__)` to that `chain(...)`, and `__filename` plus
`require.resolve("../web/rom-builder-core.js")` in `generate_roms_js.cjs`. Add
`--force` / `FORCE=1` to `make generate-roms`. `tests/test_rom_format.py`
deliberately restores `menu.rom`'s mtime because of this check — the dance
still works, but its comment needs updating.

Make `web-runtime-bundle` depend on `generate-roms`, then regenerate and commit
`web/runtime-bundle.json` (tracked, 6.9 MB, embeds 34 ROMs as base64). Run
`make build-fs` to recompress every `.romz`.

### Step 5 — parity hardening and docs

`test_menu_rom_builder_parity` compares only
`(name, width, height, frames, palette)` tuples — which is exactly why the
glyph-trailer divergence went undetected, since those tuples are identical with
or without a trailer. Replace with a structural byte comparison per record:
name bytes, the **raw 4 header bytes** (not decoded values, so an encoding
drift on either side is caught), `pixel_length`, total `record_length`, and the
trailer bytes exactly. Pixel bytes stay excluded — quantizers differ — but
lengths must match. Add a second parity target that exercises glyphs
(`games/alecu/vixeous/images` is the smallest), which would have caught the JS
glyph gap on day one.

Then update [rom-format.md](rom-format.md): biased width and frames, unbiased
height *and why*, mandatory trailer.

## Verification

Build a fixture ROM in `tests/fixtures/romformat/` — a 255×8×1 strip, a
256×8×1 strip, a 9×16×256 font and a 9×16×255 font — so round-trip tests do not
depend on `menu.rom` having been built. Then:

| Runtime | Assertion |
|---|---|
| Producers | header bytes are literally 254/255 for widths 255/256 and frames 255/256; both builders emit byte-identical records |
| MicroPython | `image_metadata[n]["width"]` is 255 and 256, `["frames"]` likewise, **and** `platform.sprites.Sprite().width()` agrees — that last one fails today against `headless.py`, which is the point |
| C | `strip_frame_width()` returns 255 and 256; `sprite_width()` returns 256; render column 255 of the 255-wide strip with the canary in place |
| Desktop | `povrender._strip_header` on both headers, called twice to exercise the `id()` cache |
| Web | new `tests/test_app_support.mjs` calling `decodeImageStripPayload` on `[254,8,0,0]` and `[255,8,0,0]`. `render-parity-test.js`'s `makeAsset` builds assets *post-decode*, so it does not exercise the decoder today — add a 256-wide parity case drawn at every column against `povrender` |

Plus builder-rejection tests for each new error (each asserting the message
names the file), and a `menurom` adversarial test: `menurom.py:52` slices with
`blob_len = 5 + name_len + real_width*height*frames` and no bound check, so feed
it a malformed icon whose declared size exceeds its span and assert it raises
rather than splicing a neighbour's bytes into the merged menu ROM.

Full suite is `python3 tests/run_tests.py`. Baseline on this tree is green
except `test_apa102_preview.py` and `test_color_profile.py`, which fail on a
missing `numpy` and are unrelated.

On hardware: **full flash, not a code-only OTA.** Then eyeball a planet
backdrop (256 wide), `warning.png` in `2bam_sencom` (255 wide), and a CP437
label rendering `chr(255)`. Confirm `alecu.vyruss_vs2.rom`'s mtime is finally
current and that it carries a glyph trailer.
