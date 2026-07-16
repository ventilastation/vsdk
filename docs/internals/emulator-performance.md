# Emulator rendering performance: what we learned

Desktop emulator frame time went from ~80ms to ~2.7ms across four rounds of
profiling and fixes (branch `perf/desktop-emulator-render`). This doc is the
reusable part: what was actually slow, why, and the general lessons -- and
now also what happened applying them to the web emulator (see "Applying this
to the web emulator" at the end).

## Status

**Desktop emulator: done.** Five commits on `perf/desktop-emulator-render`:

1. `684773b` -- vectorized + cached the APA102 raw-capture preview decode
   (color-profile handshake had made it ~5x slower: ~9.5fps ceiling).
2. `ad21b6f` -- cached per-strip headers, switched LED quad geometry to
   indexed vertices, made `draw_base_preview()` reuse persistent shapes.
   ~80ms -> ~61ms/frame.
3. `f329b5f` -- render the menu's actual code path (see below) with the real
   hardware C renderer (`gpu.c`) via ctypes instead of the Python port.
   ~61ms -> ~25ms/frame.
4. `ea2ab9a` -- moved per-LED colors from a duplicated per-vertex attribute
   to a sampled texture. ~25ms -> ~2.7ms/frame.

**Web emulator: WebGL color-texture fix landed (`042f42c`), unverified in a
real browser.** Same anti-pattern as desktop step 4 above -- confirmed by
reading `LedRingWebGLRenderer.render()`, not by live profiling (no browser
available in this environment; see "Applying this to the web emulator"
below for what that constrains). JS compositing (`led-render-core.js`'s
`computeLedFramePixels`) was measured directly under Node and is not a
bottleneck (~0.6ms/frame at 14 sprites, ~1.9ms at 50, using
`process.hrtime`) -- so the WASM-compile idea is probably not worth pursuing
for that stage specifically; it might still be worth it to collapse the
three parallel renderer implementations (Python/C/JS) into one, which is a
maintainability argument more than a performance one for this stage.

## Lesson 1: profile the real thing, not your assumption of it

The single biggest wrong turn in this investigation: assuming the desktop
menu used the VS2-scene rendering path (`render_vs2`/tilemaps), because a
screenshot looked tilemap-like. Built an entire native wire-format parser for
VS2 scenes before checking -- then live-polling
`povrender.snapshot_vs2_scene()` for 15 seconds during a real menu session
showed it never leaves `None`. The menu actually uses the older fixed
100-sprite-slot table (`povrender.spritedata`), which has no tilemaps at all.

Fix was cheap (the C renderer already had a `render()` for that path too,
right next to `render_vs2()`), but the lesson is the expensive part: **when
profiling a specific scenario ("running the menu"), instrument and observe
that exact scenario running, don't infer which code path it takes from
appearances.** A quick live poll would have caught this before any code was
written.

## Lesson 2: GPU upload cost can rival or exceed CPU render cost

Early profiling assumed the bottleneck was the Python per-pixel compositing
loop (`render()`/`render_tilemap()`). It was real (~30ms/frame) but
`vertex_list.set_attribute_data("colors", ...)` -- pushing the per-vertex
color buffer to the GPU -- cost just as much, because:

- Each LED's color was duplicated across all 6 (later 4) vertices of its
  quad, multiplying the upload size for no visual benefit.
- The whole buffer was re-packed (Python `struct.pack` + list repetition) and
  re-uploaded every redraw, even when the underlying frame data hadn't
  changed.

**Fix that mattered most:** stop treating per-entity (per-LED) data as a
per-vertex GL attribute at all. Move it to a small texture (`COLUMNS x
led_count` RGBA, one texel per LED) uploaded whole via `glTexSubImage2D`
once per frame; give each vertex a static `led_uv` texture-coordinate
attribute (identical across a quad's corners, uploaded once at init, never
touched again) and sample the color in the fragment shader. This is what
took ~25ms down to ~2.7ms -- bigger than the entire native-renderer change.

General version of the lesson: **if the same small piece of per-entity data
is being duplicated into every vertex that entity touches, and it changes
every frame, that's a signal to move it into a texture lookup instead of a
vertex attribute.** Static per-vertex data (geometry, shape UVs) should
still be uploaded once and left alone.

## Lesson 3: indexed geometry is a smaller, safer, still-worthwhile win

Before the texture change, 6 vertices/LED (2 duplicated corners per quad, so
every triangle could inline its own points) became 4 unique vertices + a
static index buffer. Cut the (still per-vertex-attribute at the time) color
upload by a third, no visual change, low risk. Worth doing on its own even
without the bigger texture-based fix, and it's the standard mechanical
transformation whenever the same vertex is being duplicated to avoid an
index buffer.

## Lesson 4: reuse a canonical, already-tested implementation over porting

`gpu.c` (`hardware/rotor/modules/povdisplay/`) is the real hardware POV
renderer, and it already builds and runs on the host
(`tests/native/test_render_vs2.c` compiles it with stub MicroPython headers
and runs parity fixtures against it). Rather than hand-optimizing the
Python port further, we wrote a thin ctypes bridge
(`emulator/native/emu_bridge.c`, `vs2_wire.c`, `native_render.py`) that calls
the real C renderer directly. This is better than a fresh C port in two
ways: it's already correct (parity-tested), and it collapses two parallel
implementations (Python port + C original) that had to be kept in sync by
hand into one canonical source. `native_render.py` falls back to the Python
renderer whenever the shared library isn't built (no compiler on PATH), so
this is additive, not a hard dependency.

Two format mismatches surfaced doing this, both worth remembering:

- **Don't decode wire bytes into language-native objects and then re-encode
  into the C structs.** Parse the wire format directly into the C structs
  (`vs2_wire.c` mirrors `decode_vs2_scene()`'s `struct.unpack_from` calls but
  writes straight into `vs2_sprite_t`/`vs2_tilemap_t` arrays). Also: image
  strip data didn't need parsing at all -- `ImageStrip`'s C layout is
  byte-identical to the wire blob already sitting in `povrender.all_strips`,
  so installing a strip natively is a zero-copy pointer cast.
- **A byte layout that's correct for one target isn't automatically correct
  for another.** `gpu.c`'s own pipeline packs colors for a real APA102 SPI
  word (R at bits 24-31, per `color_pipeline_encode_rgb`'s doc comment: "[GB,
  B, G, R]" in memory). The desktop preview's own convention is
  `0xAABBGGRR` (confirmed empirically: dumped real palette data and found
  every entry has byte 0 == `0xff`, i.e. it's alpha-first). Got the
  direction of this conversion backwards once and shipped a visibly broken
  color swap; caught it with an isolated, deterministic test (synthetic
  1-sprite scene, no star-position noise) before trusting a live comparison.
  **When two formats need reconciling, verify byte meaning against real
  captured data -- don't guess from a synthetic test with arbitrary values.**

## Lesson 5: cache at the producer, not the consumer

The APA102 raw-capture preview (Lesson-1-adjacent, from the color-profile
work) was re-decoding the same captured frame's pixels on every redraw, even
though redraws can happen more often than new frames arrive over the wire.
Decoding once when a new frame (or calibration profile) actually arrives,
caching the result, and having the redraw path just slice the cache turned a
per-redraw cost into a per-network-frame cost. Same principle applies to the
image-strip header parsing in Lesson 2's neighborhood: `_strip_header()`
caches the parsed `(w, h, total_frames, pal_base)` by strip identity instead
of re-running `struct.unpack` on the same static bytes for every sprite on
every column.

## Numbers (desktop, real menu, Intel HD 620 integrated graphics)

| Stage | Frame time |
|---|---|
| Original | ~80 ms |
| Header caching + indexed geometry + persistent shapes | ~61 ms |
| + native C renderer (ctypes) | ~25 ms |
| + texture-based per-LED colors | ~2.7 ms |

Measured with a live-instrumented harness (monkeypatched timers around
`render()`/`display_draw()` and its GL sub-calls) driving the real local
MicroPython + pygletengine stack against the actual menu ROM, not a
synthetic benchmark. Verified visually via screenshots at each stage and
against the existing test suite (`tests/test_apa102_preview.py`,
`tests/test_color_profile.py`, `tests/native/test_render_vs2.c`, etc.).

## Applying this to the web emulator

**Investigated and one fix landed (`042f42c`); not verified in a real
browser** -- this sandbox has no browser, no Playwright/Puppeteer, no
headless-GL. Everything below was confirmed by reading code and by running
`led-render-core.js` under plain Node (it's Node-importable via its UMD
wrapper, same trick `tests/test_web_input_v2.mjs` already uses to import
browser JS headlessly), not by loading a real page. Test in a real browser
before trusting the WebGL change; see the commit message for what to check
(the diagnostics panel's existing "Color Expand"/"Upload" timings, Force 2D
Fallback toggle for a before/after comparison).

Confirmed structure (see `docs/internals/web-emulator-architecture.md` for
the wider architecture):

- **Rendering is JS, not WASM.** MicroPython (running as WASM,
  `web/wasm-worker.js`) only hands over raw sprite/VS2-scene bytes via
  `post_present_ptr`; `app.js` decodes them and calls
  `computeLedFramePixels()` in `web/led-render-core.js` every frame -- a
  full JS reimplementation of `povrender.py`'s per-column/per-sprite
  compositing loop. `web/render-parity-test.js` confirms this is a third
  hand-maintained parallel implementation (Python/C/JS), kept in sync by
  copying test fixtures across all three by hand (per
  `tests/native/test_render_vs2.c`'s doc comment).
- **That JS compositing stage is not the bottleneck.** Measured directly
  under Node (`process.hrtime`, warmed-up loop): ~0.6ms/frame at 14 sprites
  (roughly the desktop menu's sprite count), ~1.9ms at 50. V8's JIT handles
  this fine; unlike the desktop's CPython interpreter, there's no
  Lesson-4-shaped win available here on performance grounds alone. Reusing
  `gpu.c` via a WASM build (Emscripten already builds a MicroPython
  webassembly variant via `tools/build-micropython-webassembly.sh`, using
  the standard `USER_C_MODULES`-equivalent variant mechanism -- so linking
  `gpu.c` in is plausible, not from zero) would still be worth considering,
  but as a maintainability move (collapse three parallel implementations
  into one canonical source) rather than a performance one.
- **The WebGL renderer had the exact Lesson-2 anti-pattern.**
  `LedRingWebGLRenderer.render()` (`web/led-ring-renderers.js`) called
  `fillRepeatedLedColors(ledPixels, this.colorWords, 6)` every frame --
  duplicating each LED's color into 6 vertices -- then re-uploaded the
  whole buffer via `bufferSubData` every frame. Fixed in `042f42c` the same
  way as desktop step 4: static per-vertex `ledUV` (uploaded once) plus a
  small per-LED color texture uploaded via `texSubImage2D` each frame,
  sampled in the fragment shader. Convenient simplification here: the
  `ledPixels` array is already column-major/led-minor (row-major for a
  `PIXELS`-wide x `COLUMNS`-tall image), so the texture upload needs no
  reshape/transpose the way the desktop one did.
- **The Canvas 2D fallback (`LedRingCanvasRenderer`) was not touched.** It
  does a `save()/translate()/rotate()/fillRect()/restore()` per lit LED (up
  to 13,824 calls/frame) -- a different problem shape (per-shape Canvas API
  call overhead, not vertex/texture upload), only reached when WebGL is
  unavailable or forced off, and not something the JS-compositing
  measurement above rules in or out. Worth its own profiling pass if it
  turns out to matter in practice.
- The existing "Current Memory Rule" in
  `docs/internals/web-emulator-architecture.md` (prefer pointer+length over
  fresh `bytes` objects across the MicroPython<->JS bridge, since that
  caused heap growth in the WASM build) wasn't implicated here -- the
  texture upload happens entirely on the JS/WebGL side, downstream of
  where `ledPixels` already lands as a `Uint8Array`. Keep it in mind if a
  future fix moves compositing into WASM, though: that would reopen the
  same bridge-payload question this rule was written for.
