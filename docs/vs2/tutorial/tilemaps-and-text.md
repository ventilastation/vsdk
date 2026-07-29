# 5. Tilemaps and text

A sprite per object stops scaling somewhere around a terrain field or a line of
text. A tilemap draws a whole grid from one record.

## Tilemaps

```python
def build(self):
    world = self.layer("world", projection=vs2.TUNNEL)
    self.ground = world.tilemap("terrain.png", columns=8, rows=17,
                                view_width=256, view_height=128)
```

The tileset is an ordinary strip: one frame per distinct tile. Tile size comes
from the image, so it can never disagree with it —
{py:attr}`~vs2.Tilemap.tile_width` and {py:attr}`~vs2.Tilemap.tile_height` are
read-only.

The grid itself is a flat `bytearray` of tile indices, one byte per cell:

```python
self.ground[col, row] = ROCK           # checked, (column, row) order
tile = self.ground[col, row]
self.ground.fill(GRASS)                # every cell

# The fastest path, when you are filling in bulk and know it is in range:
self.ground.cells[row * self.ground.columns + col] = ROCK
```

{py:data}`vs2.EMPTY_TILE` (255) leaves a cell blank and the renderer skips it.
Freshly allocated grids are filled with it.

### Scrolling

The view is a fixed window onto the grid. Scrolling moves the window, not the
data, so it costs one scalar write and allocates nothing:

```python
def update(self):
    self.depth += 1
    self.ground.view_y = self.depth % self.ground.tile_height
```

Rewriting a row of cells only when a whole tile has scrolled past — rather than
every tick — is what keeps a scrolling terrain affordable.

### Bring your own buffer

Pass `cells=` when the game already owns the data, and object identity is kept,
so writes to your buffer are what the renderer reads:

```python
self.terrain_data = bytearray(TERRAIN_COLS * TERRAIN_ROWS)
self.terrain = world.tilemap("terrain.png",
                             columns=TERRAIN_COLS, rows=TERRAIN_ROWS,
                             cells=self.terrain_data)
```

The length is checked at the call. The buffer cannot be replaced or resized
afterwards — the renderer reads those bytes directly.

## Labels

A label is a tilemap you write strings into. Three lines of text as sprites cost
54 of your 100 slots; as labels they cost one tilemap record each, no matter how
often the text changes.

```python
def build(self):
    hud = self.layer("hud", projection=vs2.HUD)
    self.score  = hud.label("digits.png", columns=5, x=100, y=1)
    self.status = hud.label("tinyfont.png", columns=21, rows=3, x=-42, y=0)
    self.title  = hud.label("rainbow437.png", columns=18, text="READY")
```

Labels and tilemaps can mirror their complete visible area with `flip_x` and
`flip_y`. Setting both rotates a label 180 degrees while leaving the source
font strip in its normal reusable orientation:

```python
self.top_score = hud.label(
    "digits.png", columns=5, x=110, y=1,
    flip_x=True, flip_y=True,
)
```

One-line labels get a `text` property; multi-line ones use
{py:meth}`~vs2.Label.write`:

```python
self.title.text = "GAME OVER"                # truncates and pads
self.status.write(0, 1, "J1:.... .... ..")   # (column, row, text)
```

Both handle the display's storage direction internally: you write ordinary
left-to-right strings and never see the reversed indices the hardware wants.

### Scores without allocating

`"%05d" % value` allocates a string every frame.
{py:meth}`~vs2.Label.set_number` writes the digits straight into the cells:

```python
def update(self):
    self.score.set_number(self.points, width=5, pad="0")
```

### Glyphs

Characters map to frames through a glyph table, resolved once at `build()` in
this order:

1. **A `glyphs=` argument** at the call site, for one-offs:
   `hud.label("digits.png", columns=5, glyphs="0123456789")`.
2. **A `glyphs:` entry in `__images__.yaml`**, next to the strip it describes —
   the artist sees the mapping and the font together:

   ```yaml
   - strip: digits.png
     glyphs: "0123456789"
   ```

3. **CP437**, the default, where `frame = ord(ch)`. This is what
   `rainbow437.png` and the other full font strips use.

Unmappable characters and spaces become {py:data}`vs2.EMPTY_TILE`, so the
renderer skips them. If your font has an opaque background and you want a real
space glyph, include `" "` in the charmap.

Font strips that pack a second colour at a fixed offset are reached with
`frame_offset`:

```python
self.status.write(3, 1, "ABXY", frame_offset=0x80)   # the red variant
```

:::{note}
Labels count against the **tilemap** budget, not the sprite budget — 16 tilemaps
including labels. A score, a message line and a debug overlay are three before
any terrain.
:::

Next: [scenes, input and sound](scenes-and-input.md).
