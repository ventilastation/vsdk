# VS2 API Rework Proposal

Status: unified proposal
Baseline: `main` at `31e65f3`
Working branch: `design/v2-api-rework-v4`

This document merges three independently written drafts of the same rework
(`design/v2-api-rework`, `-v2`, `-v3`, all cut from the same `main` commit).
All three converged on the same core architecture — a strong sign it is the
right one. Where they disagreed (surface scope, draw-order mechanics,
enforcement strictness, naming), this document resolves the disagreement and
records the choice. It supersedes the three earlier drafts.

## Why this exists

`vs2` (`apps/micropython/vs2.py`) was built as a vertical slice to prove that
a layered, mixed sprite/tilemap renderer could work on the rotor hardware. It
did that job. But its public shape still reads like an implementation log:
allocation happens in constructors instead of through an owner, a `Sprite`'s
`mode=` argument is silently overwritten the moment it joins a layer, and
every V2 game either hand-rolls an object pool or hand-rolls a text renderer
because `vs2` offers neither. Six real apps
(`system/tutorial_vs2`, `games/demos/input_demo`, `games/demos/povstress`,
`games/alecu/mapdemo`, `games/alecu/vixeous`, `games/alecu/vyruss_vs2`) have
each independently discovered and worked around the same handful of rough
edges. That repetition is the signal that the API, not the games, should
change.

This proposal gives `vs2` one ownership model, separates allocation from
mutation into enforced phases, adds first-class sprite pools and text labels,
lets any number of tilemaps interleave with sprites, and completes the V2
surface (controls, audio, scene transitions) so a V2 game never needs to
import V1 modules. `ventilastation.sprites` (V1) is untouched: every V1 game
and system app keeps working with zero source changes.

## Design goals, in priority order

1. **A developer should not be able to leak or crash by omission.** Creating
   a drawable and forgetting to attach it, creating one too many, or naming a
   missing image should either be structurally impossible or fail
   immediately with a message naming the scene, the resource, and the fix.
2. **Multiple tilemaps must compose freely with sprites and each other.**
   Draw order is one ordered list per layer, not a renderer pass that
   privileges one drawable kind over another.
3. **Text should not cost a sprite per character or hand-written column
   reversal.** Labels are common enough (HUD scores, debug overlays,
   dialogue) to belong in the API.
4. **The common path is short.** Most games want "put this image at this
   position in this layer" and should not think about tile dimensions,
   viewport tuples, or numeric strip ids to get there.
5. **Nothing in the hot path allocates.** The board has on the order of 8 MB
   of usable RAM shared between MicroPython's heap, image strips, audio, and
   the interpreter, and the renderer must produce a new column of LEDs every
   rotation tick. A per-frame tuple, dict, or formatted string is not "a
   little garbage" — over a session it is the difference between a stable
   heap and a GC pause landing on a visible frame.
6. **V1 is a closed, working system.** `ventilastation.sprites`, its
   100×5-byte sprite table, and every existing V1 game/app are out of scope.
   They keep working unmodified, and `api_guard` keeps rejecting an app that
   mixes both APIs.

## What the current implementation gets wrong

Cited against the actual code on `main`:

- **Allocation happens before ownership.** `Sprite.__init__` unconditionally
  calls `backend.Sprite()` (`vs2.py:556`), consuming one of the 100 native
  slots *before* the caller has decided whether — or where — to attach it.
  `layer=` is an optional kwarg (`vs2.py:543`); a `Sprite("x.png")` never
  added to a layer still occupies a slot for the scene's life. Same for
  `Tilemap`. `Sprite(replacing=...)` exposes slot recycling as a public
  workaround for the missing free.
- **A layer silently overwrites what you just set.** `Layer.add()` does
  `drawable.mode = self.mode` (`vs2.py:495`). A `Sprite("x.png", mode=HUD)`
  added to a `TUNNEL` layer quietly becomes a `TUNNEL` sprite.
- **Frame and visibility are coupled in one direction.** The `frame` setter
  always sets `self._visible = True` (`vs2.py:640-645`). There is no way to
  preload a frame on a hidden sprite (priming a pooled bullet) without an
  extra `hide()` right after.
- **Tilemaps coexist but cannot interleave with sprites.** `gpu.c:319` draws
  every tilemap, then (`gpu.c:358`) every sprite — two hard-coded passes. A
  game cannot express "ground tile, player sprite, cloud tile" in one paint
  order. The cap, `VS2_MAX_TILEMAPS = 8` (`gpu.h:15`), surfaces as a bare
  `RuntimeError("too many vs2 tilemaps")` with no scene name, count, or fix.
- **Viewport is a tuple, reassigned every frame to scroll.**
  `Tilemap.viewport` is a 4-tuple (`vs2.py:874-880`); `mapdemo.py:96`
  allocates a fresh one per step, in the hot path, for the lifetime of every
  scrolling map.
- **Text is either 54 sprites or a hand-rolled tilemap.**
  `tutorial_vs2/code/__init__.py:12-24` spends 54 of the 100 sprite slots on
  three lines of text. `input_demo.py:83-90` uses one tilemap but must
  hand-write the clockwise-column reversal
  (`self.text_frames[offset + LINE_LENGTH - 1 - index] = frame`) and the
  "OR in 0x80 for the red variant" packing itself, with a comment explaining
  why, because no shared helper exists.
- **There is no sprite pool.** `vixeous.py:142-149` hand-rolls a
  `PooledSprite` base class subclassed five times; `vyruss_vs2.py:185-186`
  preallocates flat lists (50 baddies, 8 bombs, a 9-sprite scoreboard, …)
  with no budget check — close to the 100-sprite ceiling with nothing
  surfacing that fact before the native allocator raises.
- **Strip mistakes surface late or not at all.** A typo'd image name raises
  a bare `KeyError` from the `stripes` dict; a frame index past the strip's
  end silently renders garbage; frame counts aren't queryable, so games
  hardcode them (`tutorial_vs2` keeps `"frames": 12` literals next to each
  sprite). The native strip table retains raw buffer pointers, worked around
  by the director's `_stripe_buffers` keep-alive dictionary and its long
  explanatory comment (`director.py:113-123`).
- **V2 has no services of its own.** Every V2 game imports
  `ventilastation.director` for input, sound, and scene changes, inheriting
  V1's naming: the separate `is_pressed2`/`was_pressed2` family for player
  2, and `director.pop()` followed by `raise StopIteration()` to leave a
  scene. None of this is a V2 contract; it leaked through.
- **Global mutable module state stands in for scene ownership.**
  `_live_sprites`, `_live_tilemaps`, and the scratch lists (`vs2.py:124-129`)
  collect every drawable ever created; `export_scene_payload()` filters them
  down to the active scene by linear scan per call. Scoping is reconstructed
  after the fact from a `_scene` attribute instead of existing by
  construction.

None of this is a criticism of the original slice — it proved the renderer.
But it is not a shape to build six more games against.

## The ownership model

```text
Scene
 └─ Layer (ordered, bottom → top)
     └─ Drawable (ordered, bottom → top within the layer)
         ├─ Sprite
         ├─ SpritePool (a fixed group of Sprites)
         ├─ Tilemap
         └─ Label (a Tilemap with a text-writing helper)
```

Rules that follow directly from the shape:

- **A layer creates its own drawables.** There is no free-standing
  `Sprite(...)`. `layer.sprite(...)`, `layer.sprite_pool(...)`,
  `layer.tilemap(...)`, and `layer.label(...)` allocate the native slot
  *and* attach in one step. A drawable that isn't owned cannot exist, so it
  cannot leak.
- **Build and run are enforced phases.** `Scene.build()` creates layers and
  drawables; when it returns, the scene is *sealed* and every structural
  call raises `SceneSealedError` naming the offending method. `update()`
  can only mutate what exists. "The 101st sprite" becomes a build-time
  error the first time the scene is entered, not a runtime surprise
  mid-game.
- **One ordered list per layer, mixing every kind.** Drawables paint in
  creation order, bottom to top — sprite, tilemap, or label alike.
- **Projection is layer state, full stop.** Drawables neither accept nor
  store a projection; it is set on the layer and cannot be silently
  overwritten by attachment.

## Public API

```python
import vs2
```

### The smallest game

```python
import vs2
from vs2.controls import *


class MyGame(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)

        self.ship = self.world.sprite("ship.png", x=120.5, y=16)
        self.bullets = self.world.sprite_pool("shot.png", count=8)
        self.score = self.hud.label("digits.png", columns=5, x=100, y=1,
                                    glyphs=vs2.DIGITS)

    def update(self):
        if joy1.held(LEFT):
            self.ship.x -= 0.5
        if joy1.held(RIGHT):
            self.ship.x += 0.5

        if joy1.just_pressed(A):
            self.bullets.spawn(x=self.ship.x, y=self.ship.y - 4)

        if joy1.just_pressed(BACK):
            return self.pop()


def main():
    return MyGame()
```

No `stripes_rom`, no `super().on_enter()`, no `director` import, no numeric
perspective constants, no tuple viewport, and nothing in `update()` can
allocate a slot.

### Scene lifecycle

```python
class MyGame(vs2.Scene):
    def build(self):
        ...        # create layers and drawables; runs on every scene entry

    def update(self):
        ...        # every tick; may only mutate existing drawables

    def teardown(self):
        ...        # optional: cancel timers, save state — never required
```

`build`/`update`/`teardown` are V2-only names, deliberately different from
V1's `on_enter`/`step`/`on_exit` so a game cannot half-migrate by accident.
Internally `vs2.Scene` implements the V1-facing hooks as private adapters:
they activate the scene's native arena, load its asset pack, call `build()`,
seal the scene, then drive `update()` and call `teardown()` on the way out.
V2 games never override the V1 hooks. Persistent non-render state (scores,
progress) may live in `__init__`; drawable handles are rebuilt in `build()`.

Leaving a scene is a method call, not a control-flow exception:

```python
self.push(PauseMenu())        # suspend this scene, run another on top
self.pop()                    # resume the scene below, or exit the app
self.switch(GameOver(score))  # replace this scene outright
```

All three return `None`, so `return self.pop()` reads as "handle input, then
stop." No V2 game raises `StopIteration`. One transition may be queued per
tick; a second request raises a diagnostic error.

`self.after(ms, callback)` schedules a one-shot callback, discarded if the
scene leaves first. It replaces `call_later` for V2 code. It is allowed at
runtime because it is intentionally infrequent (menus, respawn delays) —
never per-tick.

Scene-scoped display effects are declarative:

```python
class MyGame(vs2.Scene):
    starfield = True    # applied on entry, restored to default on exit
```

### Layers

```python
background = self.layer("background", projection=vs2.TUNNEL)
hud = self.layer("hud", projection=vs2.HUD, visible=True)
```

```python
hud.visible = False       # whole-layer toggle, no drawable touched
hud.projection = vs2.HUD  # writable at runtime (e.g. a radar layer that
                          # flips between TUNNEL and HUD)
```

Layers are created bottom-to-top; a drawable's `layer` is read-only for its
whole life, so draw order is never ambiguous. `vs2.FULLSCREEN` remains valid
for sprite layers only; creating a `tilemap()` or `label()` on a
`FULLSCREEN` layer raises during `build()` instead of silently drawing
nothing, which is what happens today.

All drawables share `x`, `y`, `visible`, `show()`, `hide()`. Coordinates are
signed 8.8 fixed point in the native records; X wraps around the 256-column
display, Y clips at the visible radial range. Projection defines how a
renderer maps Y to LEDs, not whether negative values are accepted.

### Sprites

```python
ship = world.sprite("ship.png", x=128, y=16, frame=0, visible=True,
                    flip_x=False, flip_y=False)
```

```python
ship.x, ship.y           # signed 8.8 fixed point
ship.frame               # validated against the image's frame count;
                         # never changes .visible
ship.visible             # never changes .frame
ship.flip_x, ship.flip_y
ship.width, ship.height  # read-only, from image metadata — no native call
ship.image               # read/write; assign a name or an Image handle;
                         # keeps .frame if still valid, else resets it to 0
ship.show(), ship.hide()
```

Defaults are unsurprising: frame 0, visible. `frame` and `visible` are
independent axes, so priming a pooled bullet is simply:

```python
shot.frame = BULLET_FRAME    # still hidden
shot.show()                  # now visible, same frame
```

Assigning an out-of-range frame raises `FrameError` at the assignment line —
one integer compare, always on — instead of rendering garbage pixel data.

Collision helpers:

```python
if shot.overlaps(enemy):
    ...
target = shot.first_overlap(enemies)   # Sprite or None; accepts any
                                       # iterable of sprites, incl. a pool
```

Allocation-free axis-aligned tests with circular X semantics, unchanged in
math from today. The V1-compat shims (`set_x`, `set_frame`,
`set_perspective`, `disable`, `collision`, `replacing=`) are not part of the
revised surface; V1's own `Sprite` keeps all of them.

### Sprite pools

The pattern every V2 game hand-rolls becomes a primitive:

```python
self.enemies = world.sprite_pool("enemy.png", count=16, frame=0)
self.booms = world.sprite_pool("explosion.png", count=4,
                               on_empty=vs2.RECYCLE)

enemy = self.enemies.spawn(x=spawn_x, y=spawn_y)   # live sprite, or None
...
self.enemies.despawn(enemy)
self.enemies.despawn_all()                          # level reset
```

- `sprite_pool()` allocates `count` hidden sprites during `build()`, so the
  sprite budget is spent visibly, up front, in one reviewable number.
- `spawn(x, y, frame=0, flip_x=False, flip_y=False)` takes a free sprite,
  positions it, shows it. On exhaustion it returns `None` by default —
  "no free bullet this frame" is a game rule, not an error — or, with
  `on_empty=vs2.RECYCLE`, reuses the oldest live sprite (the right default
  for explosions and particles).
- `despawn(sprite)` hides it and returns it to the free list. Double
  despawn and foreign sprites raise `ValueError` in development builds.
- All calls are O(1) index bookkeeping; nothing allocates a Python object
  or native record.
- Iterating the pool yields live sprites only, and despawning the current
  sprite during iteration is supported — it is the #1 loop:

```python
for shot in self.shots:
    shot.y += SHOT_SPEED
    if shot.y > 54:
        self.shots.despawn(shot)
        continue
    baddie = shot.first_overlap(self.baddies)
    if baddie:
        self.baddies.despawn(baddie)
        self.booms.spawn(x=baddie.x, y=baddie.y)
        self.shots.despawn(shot)
```

`len(pool)` is the live count; `pool.free` the remainder. This replaces
vixeous's `PooledSprite` hierarchy and gives vyruss's flat lists a visible
budget.

### Tilemaps

Tile size comes from the tileset image, not a repeated argument:

```python
self.ground = world.tilemap("terrain.png", columns=8, rows=17, x=0, y=64,
                            view_width=256, view_height=128)
```

- If `cells=` is omitted, `tilemap()` allocates the `columns * rows`
  bytearray during `build()`, filled with `vs2.EMPTY_TILE`; it is exposed as
  `tilemap.cells`. Callers that already own a buffer (a scroll ring shared
  between maps, a level file) pass `cells=` and keep object identity — the
  zero-copy contract with the renderer is unchanged. Length is validated at
  the call.
- `tile_width`/`tile_height` are read-only, from the image. They had to
  match it anyway; now they can't not.
- The view is the fixed on-screen window; scrolling mutates scalar native
  fields and allocates nothing:

```python
self.ground.view_x = 0
self.ground.view_y = self.depth % self.ground.tile_height
```

- Cell access is checked indexing in `(column, row)` order — the same axis
  order as `(x, y)` everywhere else — with the raw buffer still available
  for bulk work:

```python
self.ground[col, row] = ROCK
tile = self.ground[col, row]
self.ground.fill(GRASS)
self.ground.cells[row * self.ground.columns + col] = ROCK   # fastest path
```

`vs2.EMPTY_TILE` (255) leaves a cell empty and the renderer skips it. The
buffer cannot be replaced or resized while active.

#### Multiple tilemaps, freely interleaved

Draw order is creation order within a layer, so this works exactly as
written:

```python
ground = world.tilemap("ground.png", columns=8, rows=17)
river  = world.tilemap("river.png", columns=8, rows=17)
player = world.sprite("ship.png")
clouds = world.tilemap("clouds.png", columns=8, rows=4)
```

Paints back-to-front: ground, river, player, clouds. Splitting `clouds` into
its own layer above `world` gives the same visual result; a game chooses
whichever reads better. The renderer must not keep the hard-coded "all
tilemaps, then all sprites" passes — see "Under the hood".

The API promises *multiple*, not *unbounded*: the budget is 16 tilemap
records (labels included), doubled from today's native cap of 8 because
labels make tilemaps the routine drawable — a score, a message line, and a
debug overlay are already three before any terrain. The matching trim is
layers, 16 → 8: current games use 2–4, and halving the layer table offsets
the tilemap growth. Each tilemap record is ~40 bytes, so memory is
negligible; phase 4's acceptance scene (a scrolling terrain map, several
HUD labels, one overlay map) validates the per-column render cost with the
full budget live.

### Labels: text is a tilemap you write into

```python
self.status = hud.label("tinyfont_menu.png", columns=21, rows=3, x=-42, y=0)

self.status.write(0, 0, "     LRUD ABXY S B")
self.status.write(0, 1, "J1:.... .... ..")
```

`write(column, row, text)`:

- maps characters to glyph frames through the label's glyph table;
- handles the circular display's storage-direction reversal internally, so
  callers write left-to-right text and never see the reversed-index
  arithmetic `input_demo.py:90` currently writes by hand;
- clips to the fixed grid and pads with `vs2.EMPTY_TILE` (the renderer
  skips those cells);
- touches only the bytes it changes — no allocation.

One-line labels (`rows=1` is the default) get property sugar:

```python
title = hud.label("rainbow437.png", columns=18, text="VS2 SPRITES")
title.text = "GAME OVER"          # truncates at columns, pads with empty
```

Numeric HUDs avoid building a formatted string every frame:

```python
self.score.set_number(value, width=5, pad="0")
```

Glyph mapping is resolved once at `build()`:

- `glyphs=vs2.CP437` (default): `frame = ord(ch)`, matching
  `rainbow437.png`; unmappable characters and spaces become `EMPTY_TILE`.
- `glyphs=vs2.DIGITS`: for fonts like `digits.png` whose frame 0 is `"0"`.
- `glyphs="0123456789/-"`: a literal charmap string for sparse icon fonts —
  `frame = charmap.index(ch)`. Include `" "` in the charmap to get a real
  space glyph on fonts with opaque backgrounds.

Style variants that today require OR-ing a magic `0x80` into frame ids
become a named argument:

```python
self.status.write(3, 1, "ABXY", frame_offset=0x80)
```

Cost: one tilemap record and `columns * rows` bytes, regardless of how much
text changes per frame. Replacing `tutorial_vs2`'s three 18-sprite
`TextDisplay` instances with three labels frees 53 of 100 sprite slots;
replacing `input_demo`'s hand-rolled reversal removes the only code in that
file that needed a comment to explain itself.

The first implementation is deliberately fixed-cell ASCII/CP437: no
variable-width glyphs, wrapping, or Unicode shaping. Those do not belong in
the 8 MB game runtime.

### Images and strip allocation

The common case names an image inline and never sees a number:

```python
player = world.sprite("ship.png")
```

Resolving once for reuse:

```python
enemy_image = self.image("enemy.png")   # Image: .name .width .height .frames
self.small = world.sprite_pool(enemy_image, count=12)
self.boss = world.sprite(enemy_image, frame=4)
```

`Image` is a small read-only handle. The numeric strip id becomes private to
the asset bank — today `stripes[name]` returns the raw id and games/`vs2.py`
pass it around, which is exactly where typos and stale-after-ROM-reload ids
hide. Name lookup happens at `build()` or explicit assignment, never in the
renderer. `.frames` comes from ROM metadata the director already parses and
currently throws away; recording it kills the hardcoded frame-count
literals and powers `FrameError` validation.

The asset pack defaults to the current app slug; `stripes_rom` disappears
from V2 games. Shared/system scenes opt into another pack explicitly:

```python
class Tutorial(vs2.Scene):
    asset_pack = "other"
```

The asset bank owns strip allocation and lifetime:

1. ROM generation rejects duplicate image ids, more strips than the target
   supports, invalid frame counts, malformed dimensions.
2. Loading binds slots densely and validates every slot before native calls.
   No modulo slot wrapping.
3. The native binding roots the MicroPython buffer as a real GC reference,
   replacing the director's `_stripe_buffers` keep-alive workaround.
4. A bank is replaced only while both renderers are inactive and sprite
   tables are reset; exactly the current bank is rooted, so old packs are
   released at a safe boundary instead of accumulating.

V1's loader and `set_imagestrip()` keep their surface; they gain the same
bounds checking and rooting internally, changing no V1 game source.

Errors name the app, asset, and limit:

```text
AssetNotFoundError: image 'ships.png' is not in alecu.my_game
FrameError: ship.png has 4 frames; frame must be 0..3
AssetLimitError: alecu.my_game defines 103 images; this target supports 100
```

### Controls

```python
from vs2.controls import *

if joy1.held(LEFT):
    ...
if joy2.just_pressed(START):
    ...
if joy1.just_released(A):
    ...
```

`vs2.controls` is a small submodule (making `vs2` a package) holding the
two controller views — `joy1` and `joy2`, named after the wire protocol's
joy1/joy2 fields — and one button namespace: `LEFT`/`RIGHT`/`UP`/`DOWN`,
`A`/`B`/`X`/`Y`, `START`, `BACK`. The suggested pattern is
`from vs2.controls import *`: the module's `__all__` is exactly those
names, so the star import is well-defined and game code reads
`joy1.held(LEFT)`. Qualified access (`vs2.controls.joy1`,
`vs2.controls.LEFT`) works too.

One method vocabulary applies to both controllers, in the Godot style:
`held` = the button is down right now (level), `just_pressed` /
`just_released` = the transition happened this tick (edge). The mapping
from V1 is mechanical — `is_pressed` → `held`, `was_pressed` →
`just_pressed`, `was_released` → `just_released` — and unambiguous in both
directions: `held` cannot be misread as an edge, `just_*` cannot be
misread as a level, and no method collides with the `DOWN` constant. In
today's games, level reads are mostly movement (held directions, held
accelerate/brake modifiers) and edge reads are fire/confirm/exit and menu
stepping — but both combine freely with any button, as V1 usage shows.

The implementation is a thin, allocation-free wrapper over the director's
existing bitfields: the wire protocol and V1 surface do not change; V2
code just stops seeing the `is_pressed2` family and the wire-protocol
"extra" bits.

### Audio

```python
vs2.audio.sound("shoot")
vs2.audio.music("theme", loop=True)
vs2.audio.stop_music()
vs2.audio.notes(notes)
```

Defaults to the current app's sound folder; a name containing `/` is
already-qualified for shared assets (`vs2.audio.sound("alecu.vyruss/shoot1")`).
Still sends compact commands to the host — nothing is decoded on the board.

### Base hardware

Unchanged in shape from today's `vs2.base`, because it already reads well:

```python
vs2.base.leds.set_all(255, 0, 0)
vs2.base.servo.set(128)
vs2.base.buttons.set(vs2.base.BUTTON_LED_ALL, blink_ms=250)
```

Values stay normalized, range-checked, deduplicated, and safe on systems
without a physical base.

## Resource limits become diagnostics, not surprises

Caps stay explicit, per-target, and shared between native code, Python, and
tests through one generated definition (not the independently maintained
copies in `gpu.h`/`gpu.c` today). `vs2.limits` exposes them read-only.

```text
layers         8
sprites      100
tilemaps      16   (a label counts as one tilemap)
image strips 100
```

Because structural calls are only legal during `build()`, every cap is
enforced the first time the offending scene is entered — never mid-game when
a spawn tips the count. Errors carry a per-layer census so the fix is
obvious:

```text
ResourceLimitError: sprite 101/100 in Vixeous
  (world: 62, bullets: 16, hud: 22, explosions: 1);
  use a smaller sprite_pool or reuse an existing sprite
```

```text
ResourceLimitError: tilemap 17/16 in MapDemo (labels count as tilemaps);
  combine cell data into fewer maps or drop a label
```

After `build()`, a debug build may print a compact usage line
(`Vixeous: layers=2/8 sprites=38/100 tilemaps=2/16 strips=9/100`); release
builds allocate nothing for diagnostics unless an error needs formatting.

## What has to change under the hood

- **A scene arena replaces the module globals.** `_live_sprites`,
  `_live_tilemaps`, and the scratch lists go away. The scene owns layers;
  each layer owns one ordered list of drawable handles; the native backend
  owns fixed-capacity record tables for the active scene. Nothing filters
  by `_scene is scene` because nothing outside the owning scene ever holds
  a reference.
- **A tagged draw-order table, not two hard passes.** Native state gains an
  ordered list of `(kind, record-index)` pairs per layer; the renderer
  walks layers bottom-up and dispatches per entry. At the proposed caps
  that is ~116 two-byte entries — negligible next to the existing records
  — and it
  is the only native data-model change required to let a cloud tilemap draw
  over a player sprite. Labels dispatch through the tilemap path; no new
  tag.
- **Build/sealed/closed is a real state machine.** Structural methods check
  the phase and raise `SceneSealedError` from `update()` or a timer. This
  mechanism — not convention — is what turns "ran out of sprites mid-game"
  into "failed at scene entry."
- **The asset bank is the only strip allocator**, with the validation and
  GC rooting described above. Pure hardening below the API boundary; V1
  source unaffected.
- **Nothing renders from a rebuilt Python structure.** On hardware, a
  property write goes straight into the existing native record; the GPU
  task reads the same record. The payload path exists only for the desktop
  and web emulators, which cannot render from board memory. The payload
  gains a new version carrying layer records, sprite records, tilemap
  records, ordered tagged draw references, and packed cell bytes; its
  bytearray is sized after `build()` and reused while the scene is sealed.
  The browser bridge keeps sending pointer + length across the WASM
  boundary.

## V1 stays exactly as it is

- `ventilastation.sprites` keeps its class and method surface unchanged, as
  do V1 `Scene.on_enter`/`step`/`on_exit`/`call_later` and the V1 sprite
  table and render pass.
- Implicit V1 `meta.json` values remain valid; no V1 game or system app is
  migrated as part of this work.
- `api_guard` continues to reject an app that imports both APIs.
- Installed `.vs2` game packages built against the current draft API need a
  compatibility check: package metadata records the V2 API revision (and/or
  minimum SDK revision), checked at load, so a stale package fails with one
  actionable message instead of erroring halfway through scene setup.
  Packages using V1 are unaffected.

The revised V2 is a deliberate breaking change to the current experimental
`vs2` draft: the old constructors, `layer.add()`, per-drawable `mode`,
`viewport` tuples, the `set_*` shims, `set_starfield()`, and `replacing=`
are removed, and the six in-tree V2 apps are migrated in the same release.

## Migration examples

**Sprite and controls:**

```python
# before
from ventilastation.director import director
from vs2 import HUD, Scene, Sprite

class Game(Scene):
    stripes_rom = "me.game"

    def on_enter(self):
        super().on_enter()
        hud = self.layer("hud", mode=HUD)
        self.ship = hud.add(Sprite("ship.png", frame=0))

    def step(self):
        if director.is_pressed(director.JOY_LEFT):
            self.ship.x -= 1

# after
import vs2
from vs2.controls import *

class Game(vs2.Scene):
    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        self.ship = hud.sprite("ship.png")

    def update(self):
        if joy1.held(LEFT):
            self.ship.x -= 1
```

**Scrolling terrain** (`mapdemo`/`vixeous` shape):

```python
# before: six required args, a fresh tuple every step
self.terrain = self.world.add(Tilemap(
    "terrain.png", self.cells, columns=8, rows=17,
    tile_width=32, tile_height=16, viewport=(0, 0, 256, 128)))
self.terrain.viewport = (0, self.depth % 16, 256, 128)

# after: tile size from the image, scalar write, nothing allocated
self.terrain = self.world.tilemap("terrain.png", columns=8, rows=17,
                                  cells=self.cells,
                                  view_width=256, view_height=128)
self.terrain.view_y = self.depth % self.terrain.tile_height
```

**Score display** (`vyruss_vs2` shape):

```python
# before: 9 Sprite slots, per-digit frame pokes
self.chars = [Sprite("numerals.png", x=110 + n * 4, y=0, frame=10, mode=HUD)
              for n in range(9)]
for n, l in enumerate("%05d" % value):
    self.chars[n].frame = ord(l) - 0x30

# after: one tilemap record
self.score = hud.label("numerals.png", columns=5, x=110, y=0,
                       glyphs=vs2.DIGITS)
self.score.set_number(value, width=5, pad="0")
```

**Runtime entities** (`vixeous`/`vyruss_vs2` shape):

```python
# before: hand-rolled PooledSprite hierarchy / unbudgeted flat lists
# after:
self.shots = world.sprite_pool("shot.png", count=4)
self.explosions = world.sprite_pool("explosion.png", count=5,
                                    on_empty=vs2.RECYCLE)
```

**Leaving a scene:**

```python
# before
director.pop()
raise StopIteration()

# after
return self.pop()
```

## Rollout, in dependency order

Each phase lands green on the existing suites (`test_vs2_api`,
`test_emulator_vs2_render`, `test_mapdemo_vs2`, `test_vixeous_vs2`,
`test_povstress_vs2`, `test_tutorial_vs2`) plus the new tests it adds.

0. **Baselines.** Record hardware heap (before load / after assets / after
   build / after exit) and render timing for `povstress` and `vixeous`;
   snapshot desktop/web parity fixtures; add a V1 compatibility test set
   before touching shared runtime code.
1. **Asset hardening (no V1 source changes).** Shared limits definition;
   ROM-builder validation; bounds-checked `set_imagestrip` without modulo
   wrap; native GC rooting of strip buffers; `AssetBank` + `Image` metadata
   (including frame counts recorded at load). Testable in isolation.
2. **Scene arena and lifecycle.** Scene-owned structure replaces the module
   globals; `build()`/`update()`/`teardown()` adapters; sealing;
   `layer.sprite()` / `sprite_pool()`; frame/visibility decoupled;
   projection layer-only; queued `push`/`pop`/`switch`; `after()`;
   resource-census diagnostics. Keep the current two-pass renderer behind an
   adapter so this phase is independently testable.
3. **Ordered draw table and tilemap cleanup.** Tagged draw-order list in
   native state and the new payload version; native caps move to the
   agreed budgets (`VS2_MAX_TILEMAPS` 8 → 16, `VS2_MAX_LAYERS` 16 → 8);
   `layer.tilemap()` with inferred tile size, scalar `view_*`,
   `[col, row]` indexing, `fill()`;
   FULLSCREEN tilemaps rejected at build; parity fixtures for
   tilemap/sprite/tilemap interleaving, layer order, X wrap, Y clip, and
   overlapping maps on hardware, desktop, and web.
4. **Labels.** `layer.label()` on the interleavable tilemap path: glyph
   tables, storage-direction reversal, `write()`, `.text`, `set_number()`,
   `frame_offset`. Port `input_demo` and `tutorial_vs2` first — they are
   the acceptance fixtures — and measure the sprite/heap savings and the
   per-column cost of a full 16-tilemap scene on hardware.
5. **Services and app migration.** `vs2.controls`, `vs2.audio`, declarative
   `starfield`, base-output lifecycle; port `mapdemo`, `vixeous`,
   `vyruss_vs2`, `povstress`; add the package API-revision check; remove
   the old draft surface only when every in-tree V2 app has moved.
6. **Docs and freeze.** Replace `docs/vs2-api-guide.md` with the accepted
   API and recipes; update the developer guide so its simplest-game path
   starts with V2; full Python/MicroPython/native/web suite; heaviest scene
   on physical hardware before the names freeze.

## Acceptance checks

- Every V1 game/app runs with no source changes; V1 renderer fixtures stay
  byte-compatible; mixing APIs in one app still fails clearly.
- Scene structure cannot change after `build()`; a long fixed-input soak of
  the heaviest migrated scene shows no per-frame heap growth and needs no
  in-`update()` GC.
- Pool spawn/despawn, scalar tilemap scrolling, label writes, control
  reads, and property updates allocate nothing.
- The 101st sprite, 17th tilemap, 9th layer, and 101st image fail at build
  time with the census error — identically on hardware, desktop, web, and
  headless tests. No strip id silently wraps; no tilemap is silently
  skipped; no out-of-range frame renders garbage.
- At least three tilemaps and one sprite interleave correctly in one
  acceptance scene with parity across all render targets.
- A label updates in place and costs one tilemap record regardless of
  string length; text reads left-to-right on the physical display.
- Migrated `povstress` meets the real-time hardware render deadline; any
  regression versus the current native path is measured and explained.
- Peak heap for the migrated heavy fixtures fits the 8 MB environment with
  documented headroom; browser payloads still cross the WASM boundary by
  pointer + length.

## Deliberately out of scope

- Rewriting or auto-porting V1 games.
- Unbounded sprites, tilemaps, layers, fonts, or asset packs.
- Creating or destroying render objects during `update()`.
- Variable-width text, wrapping, Unicode shaping, or rich text.
- A general retained-mode UI toolkit, animation timelines, scene-graph
  transforms, or entity components in the renderer API.
- Alpha blending or changes to the palette/transparency model.

## Resolved in this revision

Recorded so the debate doesn't reopen by accident:

- **Full V2 surface** (controls, audio, transitions, lifecycle), not a
  display-only rework: V2 games currently inherit V1's naming and
  StopIteration control flow, which is exactly the incoherence this work
  exists to remove.
- **Sealed scenes** over a soft "only while entering" guard: the hard phase
  boundary is the mechanism that makes allocation mistakes impossible, not
  merely discouraged.
- **Tagged per-layer draw list** over "tilemaps first within each layer":
  true interleaving is the only native data-model change in the proposal,
  it is small, and it removes the last renderer pass that privileges a
  drawable kind.
- **Naming**: `projection`; `sprite_pool` with `spawn`/`despawn` and
  `on_empty=vs2.RECYCLE`; `Image`/`self.image()`; `view_x`/`view_y`;
  `[col, row]` indexing; `overlaps`/`first_overlap`; `build`/`update`/
  `teardown`; `push`/`pop`/`switch`; controller views are `joy1`/`joy2`
  (matching the wire protocol's field names) and button constants live in
  `vs2.controls`, designed for `from vs2.controls import *` — not in the
  `vs2` root namespace. Input methods are Godot-style
  `held`/`just_pressed`/`just_released`: `down` was rejected for colliding
  with the `DOWN` constant, and a bare `pressed` edge method was rejected
  because V1's `is_pressed` means the level — reusing the word with the
  other meaning inside the same ecosystem is the kind of incoherence this
  rework removes.
- **Budgets**: tilemaps go 8 → 16 because labels make tilemaps the routine
  drawable, and layers go 16 → 8 because current games use 2–4 and the trim
  offsets the tilemap growth. Phase 4's measurement validates the
  per-column cost of a full 16-tilemap scene rather than deciding the cap.
- **Frame validation**: always on (one integer compare per assignment).

## Open for review

1. Should `Label` ship only built-in `CP437`/`DIGITS` glyph tables plus
   literal charmap strings, or should the image manifest carry a compact
   custom mapping table for games with non-standard font strips?
2. Package metadata: an integer `api_revision`, a `min_sdk_version` string,
   or both, for rejecting stale installed `.vs2` packages?
3. Does app-owned base LED/servo state reset on every scene transition, or
   only when the whole app returns to the launcher?
4. Is `Scene.after()` part of the stable surface from day one, or held as
   advanced until its behavior across nested transitions is fully tested?

None of these blocks starting: phase 0 (baselines) and phase 1 (asset
hardening) do not depend on any of the answers.
