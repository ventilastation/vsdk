# vs2 API and Renderer Plan

`vs2` is the new game-facing API for MicroPython games. It will live in
parallel with the legacy `ventilastation.sprites` API while games are ported,
but one game must use only one of them.

## Goals

- Keep existing games and system scenes working unchanged.
- Let new or ported games import the new API as `vs2`.
- Replace getter/setter sprite code with attribute-style objects.
- Support fractional/signed coordinates, consistent Y semantics, named modes,
  sprite flipping, layers, tilemaps, and bitmap-backed orthogonal layers.
- Give the hardware renderer, desktop emulator, and web emulator matching v2
  renderers with parity tests.

## Issue Map

| Issue | API/renderer requirement |
|---|---|
| [#89](https://github.com/ventilastation/vsdk/issues/89) | Fractional coordinates. |
| [#90](https://github.com/ventilastation/vsdk/issues/90) | Python-side sprite objects must allow game instance variables. |
| [#91](https://github.com/ventilastation/vsdk/issues/91) | Replace getters/setters with attributes. |
| [#92](https://github.com/ventilastation/vsdk/issues/92) | Use named modes: `FULLSCREEN`, `TUNNEL`, `HUD`. |
| [#93](https://github.com/ventilastation/vsdk/issues/93) | Make Y axis behavior consistent across modes. |
| [#95](https://github.com/ventilastation/vsdk/issues/95) | Add `flip_x` and `flip_y`. |
| [#96](https://github.com/ventilastation/vsdk/issues/96) | Allow sprites to move reliably outside the visible Y range. |
| [#97](https://github.com/ventilastation/vsdk/issues/97) | Preserve carefully-authored palettes when <=255 colors. |
| [#98](https://github.com/ventilastation/vsdk/issues/98) | Music loop API; already available as `director.music_play(..., loop=True)`. |
| [#109](https://github.com/ventilastation/vsdk/issues/109) | Starfield defaults off and becomes opt-in. |
| [#110](https://github.com/ventilastation/vsdk/issues/110) | Scenes contain layers; layers contain sprites. |
| [#111](https://github.com/ventilastation/vsdk/issues/111) | Tilemap layer/sprite with byte-array frame backing and crop rectangle. |
| [#112](https://github.com/ventilastation/vsdk/issues/112) | 240 x 240 8-bit paletted orthogonal bitmap layer. |

## Current Branch State

The first branch step is intentionally a compatibility-backed vertical slice:

- `apps/micropython/vs2.py` exists as the top-level API module.
- `vs2.Sprite` exposes attributes such as `x`, `y`, `frame`, `strip`, `mode`,
  `visible`, `flip_x`, and `flip_y`.
- `vs2.Scene` and `vs2.Layer` establish the scene/layer/sprite shape.
- `games/alecu/vyruss_vs2` is a copied Vyruss pilot that imports `vs2`, uses
  property-style sprite access, declares `"api": "vs2"`, and has a distinct
  menu icon.
- The compatibility backend still publishes to the old 100 x 5-byte sprite
  table. This is temporary and exists only so porting can begin before the
  v2 renderer is complete.

## Import and API Selection

Game metadata may declare:

```json
{ "api": "vs2" }
```

During app loading, `ventilastation.api_guard` records the active app slug and
declared API. `vs2` claims API `vs2`; `ventilastation.sprites` claims API
`sprites`. If a game declares one API and imports the other, or if a game tries
to use both, the import/use raises `ImportError`.

System scenes can continue using legacy sprites independently because they run
under their own app context.

## Target Public API

```python
from vs2 import FULLSCREEN, TUNNEL, HUD, Layer, Scene, Sprite

class MyGame(Scene):
    stripes_rom = "myname.mygame"

    def on_enter(self):
        super().on_enter()
        self.hud = self.layer("hud", mode=HUD)
        self.ship = self.hud.add(Sprite("ship.png", x=120.5, y=-4, frame=0))

    def step(self):
        self.ship.x += 0.25
        self.ship.flip_x = self.ship.x > 128
```

The long-term renderer-facing model is:

- A scene owns up to a fixed number of layers, initially 10.
- A layer has mode/projection, visibility, and an ordered list of drawables.
- Sprite drawables reference image strips and carry fixed-point signed
  coordinates.
- Tilemap drawables own a byte array of frame/tile ids plus tile dimensions,
  crop rectangle, and optional text backing.
- Bitmap layers own a 240 x 240 8-bit paletted buffer with a transparent color.

The branch now has the first concrete payload for this model:
`vs2.export_scene_payload(scene)` emits a `VS2\0` version-1 byte buffer with
layer records and sprite records. Sprite coordinates are signed 8.8
fixed-point integers. The desktop and web emulators understand the
`vs2_scene <nbytes>` command and adapt visible v2 sprites into the existing
sprite renderer shape while richer native v2 renderers are built.

## Renderer Work

### Hardware

Add a separate render path in `hardware/rotor/modules/povdisplay/gpu.c` rather
than mutating the existing `render()` function immediately. The old renderer
must remain available for legacy games.

Recommended shape:

- Keep `render()` for legacy sprite-table frames.
- Add `render_vs2()` for v2 scene/layer state.
- Move shared color finishing/gamma helpers behind small functions so both
  renderers use the same LED output path.
- Add a v2 memory module, separate from `sprites.c`, that owns the v2 scene
  state and exposes a MicroPython module for `vs2`.
- Starfield becomes an explicit layer/effect or a display flag, default off.

### Desktop Emulator

Add a v2 renderer beside `emulator/povrender.py`'s legacy path. The desktop
emulator now understands both transports:

- legacy `sprites` command: current 500-byte table
- v2 `vs2_scene <nbytes>` command: scene/layer payload

The first emulator milestone decodes v2 sprites and layers into the legacy
render path and now honors `flip_x` / `flip_y` in that adapter. The next pass
should split that adapter into a true v2 renderer with signed/fractional
clipping.

### Web Emulator

Add v2 decoding and rendering beside `web/led-render-core.js`, keeping the
high-frequency bridge rule: pointer + length for frame payloads, not fresh
Python byte objects.

The web renderer has parity fixtures for the version-1 `vs2_scene` decoder and
for `flip_x` / `flip_y`. Next, extend those fixtures for signed Y clipping,
tilemaps, and bitmap layers.

## Suggested Milestones

1. API skeleton and guard: `vs2.py`, app metadata, tooling inclusion, docs.
2. Vyruss pilot copy: port to `vs2`, distinct menu icon, compile check.
3. v2 memory schema: fixed-point signed coordinates, flags, layers, drawables.
   Initial `vs2_scene` payload is in place.
4. v2 hardware module: native MicroPython types and `render_vs2()`.
5. Desktop v2 renderer and parity tests.
6. Web v2 renderer and parity tests.
7. Tilemap support.
8. Bitmap-backed orthogonal layer support.
9. Palette quantization preservation.
10. Deprecation warning path for legacy game docs and, later, runtime use.

## Deprecation Policy

`ventilastation.sprites` remains supported during the `vs2` rollout so old
games keep running. It is now considered the legacy API. New games should use
`vs2`, and existing games should be ported when they are actively maintained.
