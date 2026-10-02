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

```{figure} ../images/strip-terrain.png
:alt: The terrain.png strip: six tiles named grass, water, rock, sand, marker and wall
:width: 85%
:align: center

A tileset: tile 0 is grass, 1 is water, and so on.
```


Tile size comes from the image, so it can never disagree with it —
{py:attr}`~vs2.Tilemap.tile_width` and {py:attr}`~vs2.Tilemap.tile_height` are
read-only.

The grid is made of {term}`cells <cell>`, one byte each, holding a tile index:

```python
self.ground[col, row] = ROCK           # (column, row) order
tile = self.ground[col, row]
self.ground.fill(GRASS)                # every cell
```

Fill only the cells that have something in them. Dark or black backgrounds work
better on the real Ventilastation, so leave the rest of the grid empty.

{py:data}`vs2.EMPTY_TILE` (255) leaves a cell blank and the renderer skips it.
Freshly allocated grids are filled with it, so a new tilemap starts out dark.
Here is a 16 by 16 map of the tiles above with an island of terrain in it and a
ship on top. Every other cell is empty, so the rest of the disc stays black:

```{figure} ../images/tilemaps.png
:alt: A fan-shaped island of grass, water, rock and sand tiles on a black background, with a ship at the top
:width: 60%
:align: center

A 16 by 16 tilemap on a `TUNNEL` layer with only some cells filled. Tiles near the rim are drawn larger.
```


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
    self.score  = hud.label("numerals.png", columns=5, x=246, y=1)   # bottom of the disc: upright
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
direction for you. Which way up the text reads depends on where you put it, as
the next section explains.

### Scores without allocating

Formatting a number with `"%05d" % value` creates a new string every tick.
{py:meth}`~vs2.Label.set_number` writes the digits straight into the cells
instead:

```python
def update(self):
    self.score.set_number(self.points, width=5, pad="0")
```

### Which way up? Flips

Glyphs are drawn with their tops pointing toward the centre of the disc. At the
bottom of the disc the centre is above the text, so it reads upright. At the top
the centre is below the text, so the same label is **upside-down**. On the sides
it runs sideways.

```{figure} ../images/labels-flips.png
:alt: Three copies of the score: upside-down at the top without flips, upright at the top with flips, and upright at the bottom without flips
:width: 60%
:align: center

The same label in three places. Only the top one without flips is upside-down.
```

To read upright at the top, {term}`flip` the label both ways:

```python
self.top = hud.label("numerals.png", columns=5, x=118, y=14,
                     flip_x=True, flip_y=True)
```

`flip_x` mirrors the label left to right and `flip_y` mirrors it top to bottom.
Doing both turns it through 180 degrees, which is what you want at the top of
the disc. One flip on its own just gives you mirrored text.

:::{warning}
**Upside-down text at the top of the disc is the most common newcomer
mistake.** Nothing is wrong with your string or your font. Add
`flip_x=True, flip_y=True` to the label. The scoreboards in the games under
`games/` all do this. Sprites and tilemaps take the same two arguments.
:::

A label with both flips, next to one with none, over a small map:

```{figure} ../images/labels.png
:alt: A score reading 00420 upright at the top and at the bottom of the disc, above an island of terrain
:width: 60%
:align: center

Two labels: one at the top with `flip_x` and `flip_y`, one at the bottom with no flips.
```

### Glyphs

A label shows a character by picking the {term}`glyph` frame for it. By default
that is {term}`CP437`, where `frame = ord(ch)` — what `rainbow437.png` and the
other full font strips use. A strip with only a few characters, like a row of
digits, declares its own mapping in `__images__.yaml`, next to the strip:

```yaml
- strip: numerals.png
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
