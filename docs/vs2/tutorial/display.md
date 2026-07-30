# 2. The circular display

The display is a disc. A spinning bar of LEDs sweeps a full circle, and the
renderer is asked for one column of 54 LEDs at each of 256 angles.

## X is an angle

```text
                x = 128
                   │
       x = 64 ─────┼───── x = 192
                   │
                x = 0
```

X runs 0 at the bottom, 64 at the left, 128 at the top, 192 at the right, and
wraps at `vs2.display.width` (256). A sprite at x=254 that is 8 columns wide
simply straddles the seam, and collisions handle that too.

## Y is a distance inward from the rim

**y = 0 is the outer rim**, and Y grows as you move toward the centre. That is
the opposite of the screen convention, and it is the thing most likely to trip
you up.

What Y means — and how far it goes — depends on the layer's projection:

:::{list-table}
:header-rows: 1
:widths: 18 82

* - Projection
  - Y
* - {py:data}`vs2.HUD`
  - A direct LED index. `y = 0` is the outermost LED, `y = 53` is the centre.
    A sprite `h` tall stays fully on screen up to `y = 54 - h`.
* - {py:data}`vs2.TUNNEL`
  - Depth, running **0 to 255**. `y = 0` is the outermost ring. Increasing Y
    shrinks objects and moves them toward the centre, reached at `y = 255`.
* - {py:data}`vs2.FULLSCREEN`
  - Always centred. It uses the same radial curve as `TUNNEL`: `y = 0`
    expands across all 54 LEDs, and increasing Y contracts it toward the
    centre, down to one LED at `y = 255`. X rotates it.
:::

So a tunnel object at the player's end of the world sits at `y = 0`, and things
move *away* by counting up:

```python
self.player.y = 0                   # at the rim, where the player lives
laser.y += 6                        # flying off down the tunnel
if laser.y > 164:
    self.laser.despawn(laser)       # far enough away to retire
```

:::{warning}
`vs2.display.height` (54) is the **LED count**. It is the Y range for a `HUD`
layer, but a `TUNNEL` layer's Y runs to 255. Do not use it as a general "off
the screen" test — pick a depth threshold that suits your game.
:::

Both axes accept fractional values. The renderer stores signed 8.8 fixed point,
so `ship.x += 0.25` moves a quarter of a column and accumulates properly across
frames — no need to keep your own float and round it. Out-of-range values clip
rather than wrapping or crashing.

## Read the geometry, don't hard-code it

```python
x = (x + 1) % vs2.display.width      # wrap the angle

hud_label.y = 1                      # near the rim, where text is legible
```

{py:data}`vs2.display.width` and {py:data}`vs2.display.height` come from the
same generated target definition the renderer, the emulator and the tests all
use. Writing `% 256` works today but silently breaks on any future display.

## Projections

A layer's `projection` decides how Y becomes an LED. It is layer state, not
sprite state, so attaching a drawable can never silently change how it is drawn.

:::{list-table}
:header-rows: 1
:widths: 20 80

* - Projection
  - What Y means
* - {py:data}`vs2.TUNNEL`
  - Depth. Things shrink and converge toward the centre as Y grows, which reads
    as flying down a tunnel. The usual choice for a game world.
* - {py:data}`vs2.HUD`
  - A direct LED index, no perspective. y=0 is the outermost LED. The usual
    choice for scores, messages and overlays.
* - {py:data}`vs2.FULLSCREEN`
  - One centred image, for backdrops and planets. At `y = 0` it fills the
    disc; increasing Y contracts it with the tunnel depth curve. Sprites only
    — a tilemap or label on a `FULLSCREEN` layer raises during `build()`.
:::

```python
def build(self):
    self.sky   = self.layer("sky",   projection=vs2.FULLSCREEN)
    self.world = self.layer("world", projection=vs2.TUNNEL)
    self.hud   = self.layer("hud",   projection=vs2.HUD)
```

## Draw order

Two rules, and they compose:

1. **Layers paint in creation order**, bottom to top. `sky` above is painted
   first and `hud` last, so the HUD is on top of everything.
2. **Within a layer, drawables paint in creation order**, each over the ones
   before it — sprites, tilemaps and labels alike.

```python
ground = world.tilemap("ground.png", columns=8, rows=17)
player = world.sprite("ship.png")
clouds = world.tilemap("clouds.png", columns=8, rows=4)
```

That paints ground, then the player, then clouds over both. There is no "all
tilemaps, then all sprites" pass to work around.

:::{tip}
Draw order follows the **layer**, not the order you happened to call the
factories in. Creating a HUD label before a world sprite still leaves the label
on top, because the HUD layer was created second.
:::

A whole layer can be toggled or re-projected at runtime, without touching a
single drawable:

```python
self.hud.visible = False
self.radar.projection = vs2.HUD     # was TUNNEL
```

Next: [sprites](sprites.md).
