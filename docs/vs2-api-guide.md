# vs2 API Guide

`vs2` is the new Ventilastation game API. It is available alongside the older
`ventilastation.sprites` API, but a game must use one API or the other, not
both.

For new games, add this to `meta.json`:

```json
{
  "api": "vs2"
}
```

## Basic Scene

```python
from ventilastation.director import director
from vs2 import HUD, TUNNEL, Scene, Sprite


class MyGame(Scene):
    stripes_rom = "myname.mygame"

    def on_enter(self):
        super().on_enter()
        self.world = self.layer("world", mode=TUNNEL)
        self.hud = self.layer("hud", mode=HUD)

        self.ship = self.world.add(Sprite("ship.png", x=120.5, y=16, frame=0))
        self.score = self.hud.add(Sprite("digits.png", x=112, y=0, frame=0))

    def step(self):
        if director.is_pressed(director.JOY_LEFT):
            self.ship.x -= 0.5
        if director.is_pressed(director.JOY_RIGHT):
            self.ship.x += 0.5
```

## Sprites

Sprites and layers are scene-owned. Create them in `Scene.on_enter()` after
`super().on_enter()`, and recreate them each time the scene is shown. When a
scene exits, its VS2 sprites and layers are cleared and should not be reused by
another scene entry. This includes reusing the same `Scene` instance: its
`layers` collection is empty on the next entry, and old sprite/layer references
are detached from the renderer. Keep gameplay state such as scores separately,
but rebuild all drawable objects during `on_enter()`.

Create sprites from image strip names or numeric strip ids:

```python
ship = Sprite("ship.png", x=128, y=16, frame=0, mode=TUNNEL)
```

Sprites created without an explicit `frame` start hidden. Assigning `frame`,
calling `show()`, or passing `visible=True` makes them render; `hide()` and
`visible = False` publish the disabled frame to the legacy renderer.

Use attributes:

```python
ship.x += 0.25
ship.y = -8
ship.frame = 2
ship.visible = True
ship.flip_x = True
ship.flip_y = False
ship.mode = HUD
```

Named modes replace the old numeric perspective values:

| v2 name | Legacy value | Meaning |
|---|---:|---|
| `FULLSCREEN` | 0 | Fullscreen/background projection. |
| `TUNNEL` | 1 | Perspective tunnel sprites. |
| `HUD` | 2 | Non-perspective overlay sprites. |

The compatibility backend publishes integer coordinates to the old sprite table:
X wraps around the circular display (`256 == 0`, `-1 == 255`) and Y clips
vertically. The v2 scene payload preserves signed 8.8 fixed-point coordinates
for the new renderer path.

## Layers

Scenes can own layers:

```python
self.world = self.layer("world", mode=TUNNEL)
self.hud = self.layer("hud", mode=HUD)
self.world.add(Sprite("enemy.png", x=64, y=120))
```

Layers are the future draw-order and grouping unit. The compatibility backend
still draws through legacy sprite order, but new games should already group
sprites by layer so they are ready for the native v2 renderer.

The current v2 payload includes layer visibility and mode, so desktop/web
emulators can already hide whole layers and carry the intended projection mode.

## Memory and Rendering Contract

VS2 is designed for MicroPython on a memory-constrained board. Sprite and layer
objects created during scene setup hold the live records rendered by the native
backend; the renderer does not receive a copied scene graph each frame. Mutate
those objects in `step()`, reuse the same objects and buffers, and avoid making
temporary frame payloads in the hot path.

Desktop and web hosts may serialize a reused compatibility payload at the
transport boundary. That payload is not the authoritative scene state, and its
buffer should be reused while the number of layers and sprites is stable. The
web bridge sends high-frequency data by pointer and length where available, as
described in [Why Pointer Posting Matters](internals/web-emulator-architecture.md#why-pointer-posting-matters).

## Planned Tilemaps (#111)

Tilemaps are planned as a single drawable backed by a caller-owned byte buffer,
not as one `Sprite` object per cell. The intended API is:

```python
from vs2 import Tilemap

terrain = bytearray([0, 1, 1, 0, 1, 2, 2, 1, 1, 2, 2, 1, 0, 1, 1, 0])
world.add(Tilemap(
    "terrain.png", terrain,
    columns=4, rows=4,
    tile_width=8, tile_height=8,
    x=96, y=32,
    crop=(0, 0, 4, 4),
))
```

The supplied fixed-size buffer is retained and shared with the native
renderer. Updating `terrain[index]` changes a cell without allocating a new
tilemap or copying the map. Resizing or replacing the buffer while the
tilemap is active is unsupported. `crop` is measured in tile cells and limits
which cells are rendered. This API is planned, not available in the current
runtime; see [the internal #111 plan](internals/vs2-api-plan.md#tilemap-plan-111).

## Collisions

Use:

```python
hit = laser.collides_with(enemies)
```

It returns the first colliding sprite or `None`.

## Starfield

The v2 renderer will default the starfield to off. Games that want it should
opt in:

```python
from vs2 import set_starfield

set_starfield(True)
```

## Legacy API Deprecation

The old API:

```python
from ventilastation.sprites import Sprite
```

still works for existing games, but it is now the legacy API and will be
deprecated after `vs2` has hardware, desktop emulator, and web emulator parity.
Do not mix it with `vs2` inside the same game.
