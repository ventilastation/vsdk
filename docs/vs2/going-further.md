# Going further

Things you can skip until a game needs them. The [tutorial](tutorial/index.md)
covers everything required to build a complete game; this page collects the
extras.

## Sharing one image handle

If several drawables use the same image, resolve it once with
{py:meth}`Scene.image <vs2.Scene.image>` and pass the handle around:

```python
def build(self):
    enemy = self.image("enemy.png")
    self.small = self.world.sprite_pool(enemy, count=12)
    self.boss  = self.world.sprite(enemy, frame=4)
```

A mistyped name is caught at `build()`:

```text
AssetNotFoundError: image 'enemyy.png' is not in myname.mygame
```

## Fractional coordinates

Both axes accept fractional values. The renderer stores signed 8.8 fixed point,
so `ship.x += 0.25` moves a quarter of a column and accumulates properly across
ticks — you do not need to keep your own float and round it.

## Bringing your own tilemap buffer

Pass `cells=` when the game already owns the data, and the object is kept as it
is, so writes to your buffer are what the renderer reads:

```python
self.terrain_data = bytearray(TERRAIN_COLS * TERRAIN_ROWS)
self.terrain = world.tilemap("terrain.png",
                             columns=TERRAIN_COLS, rows=TERRAIN_ROWS,
                             cells=self.terrain_data)
```

The length is checked at the call. The buffer cannot be replaced or resized
afterwards, because the renderer reads those bytes directly.

When you are filling in bulk and know every index is in range, index
`tilemap.cells` directly and skip the bounds check:

```python
self.ground.cells[row * self.ground.columns + col] = ROCK
```

## Flipping tilemaps and labels

`flip_x` and `flip_y` mirror a tilemap's or label's whole visible area. Setting
both rotates a label 180 degrees while leaving the font strip in its normal
orientation:

```python
self.top_score = hud.label(
    "numerals.png", columns=5, x=110, y=1,
    flip_x=True, flip_y=True,
)
```

## Glyph tables in detail

A label maps characters to frames through a glyph table, resolved once at
`build()` in this order:

1. **A `glyphs=` argument** at the call site, for one-offs:
   `hud.label("numerals.png", columns=5, glyphs="0123456789")`.
2. **A `glyphs:` entry in `__images__.yaml`**, next to the strip it describes.
3. **CP437**, the default, where `frame = ord(ch)`.

Characters with no mapping, and spaces, become {py:data}`vs2.EMPTY_TILE`, so
the renderer skips them. If your font has an opaque background and you want a
real space glyph, include `" "` in the table.

Font strips that pack a second colour at a fixed offset are reached with
`frame_offset`:

```python
self.status.write(3, 1, "ABXY", frame_offset=0x80)   # the red variant
```

## Scene-scoped effects

```python
class MyGame(vs2.Scene):
    starfield = True       # applied on entry, restored on exit
```

## Reading idle time directly

`vs2.controls.idle_ms` is the milliseconds since any controller was touched. Most
games want {py:attr}`~vs2.Scene.idle_timeout` and
{py:meth}`~vs2.Scene.on_idle` instead; see the
[reference](reference/services.md).

## Palette animation

Recolouring the loaded palette tints every sprite drawn from that palette group
with one buffer write. See `vs2.display.palettes` in the
[reference](reference/services.md).
