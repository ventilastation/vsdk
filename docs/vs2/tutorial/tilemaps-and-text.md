# 5. Tilemaps and text

A sprite per object stops scaling somewhere around a terrain field or a line of
text. A {term}`tilemap` draws a whole grid from one record.

## Tilemaps

```python
def build(self):
    world = self.layer("world", projection=vs2.TUNNEL)
    self.ground = world.tilemap("terrain.png", columns=8, rows=17,
                                view_width=256, view_height=128)
```

The tileset is an ordinary {term}`strip`: one frame per distinct {term}`tile`.
Tile size comes from the image, so it can never disagree with it —
{py:attr}`~vs2.Tilemap.tile_width` and {py:attr}`~vs2.Tilemap.tile_height` are
read-only.

The grid is made of {term}`cells <cell>`, one byte each, holding a tile index:

```python
self.ground[col, row] = ROCK           # (column, row) order
tile = self.ground[col, row]
self.ground.fill(GRASS)                # every cell
```

{py:data}`vs2.EMPTY_TILE` (255) leaves a cell blank and the renderer skips it.
Freshly allocated grids are filled with it.

### Scrolling

The {term}`view` is a fixed window onto the grid. Scrolling moves the window,
not the data, so it costs one write:

```python
def update(self):
    self.depth += 1
    self.ground.view_y = self.depth % self.ground.tile_height
```

Rewriting a row of cells only when a whole tile has scrolled past — rather than
every tick — is what keeps a scrolling terrain affordable.

## Labels

A {term}`label` is a tilemap you write strings into. Three lines of text as
sprites cost 54 of your 100 slots; as labels they cost one tilemap record each,
no matter how often the text changes.

```python
def build(self):
    hud = self.layer("hud", projection=vs2.HUD)
    self.score  = hud.label("digits.png", columns=5, x=100, y=1)
    self.status = hud.label("tinyfont.png", columns=21, rows=3, x=-42, y=0)
    self.title  = hud.label("rainbow437.png", columns=18, text="READY")
```

One-line labels get a `text` property; multi-line ones use
{py:meth}`~vs2.Label.write`:

```python
self.title.text = "GAME OVER"                # truncates and pads
self.status.write(0, 1, "J1:.... .... ..")   # (column, row, text)
```

You write ordinary left-to-right strings; the label handles the display's
direction for you.

### Scores without allocating

Formatting a number with `"%05d" % value` creates a new string every tick.
{py:meth}`~vs2.Label.set_number` writes the digits straight into the cells
instead:

```python
def update(self):
    self.score.set_number(self.points, width=5, pad="0")
```

### Glyphs

A label shows a character by picking the {term}`glyph` frame for it. By default
that is {term}`CP437`, where `frame = ord(ch)` — what `rainbow437.png` and the
other full font strips use. A strip with only a few characters, like a row of
digits, declares its own mapping in `__images__.yaml`, next to the strip:

```yaml
- strip: digits.png
  glyphs: "0123456789"
```

Characters with no mapping, and spaces, are left blank. Other ways to set the
mapping, and strips with a second colour, are in
[going further](../going-further.md).

:::{note}
Labels count against the **tilemap** {term}`budget`, not the sprite budget — 16
tilemaps including labels. A score, a message line and a debug overlay are three
before any terrain.
:::

Next: [scenes, input and sound](scenes-and-input.md).
