# 5. Tilemaps and text

A sprite per object stops scaling somewhere around a tunnel wall or a line of
text. A {term}`tilemap` draws a whole grid from one record.

## Tilemaps

```python
def build(self):
    world = self.layer("world", projection=vs2.TUNNEL)
    self.ground = world.tilemap("trench.png", columns=16, rows=16,
                                view_width=256, view_height=160)
```

The tileset is an ordinary {term}`strip`: one frame per distinct {term}`tile`.

```{figure} ../images/strip-trench.png
:alt: The trench.png strip: eight tiles named plate, seam, pipe, windows, vent, hazard, lights and conduit
:width: 85%
:align: center

A tileset: tile 0 is a plain hull plate, 3 is a row of lit windows, and so on.
Most of the tiles are near-black; the colour is in a few lit structures.
```


Tile size comes from the image, so it can never disagree with it —
{py:attr}`~vs2.Tilemap.tile_width` and {py:attr}`~vs2.Tilemap.tile_height` are
read-only.

The grid is made of {term}`cells <cell>`, one byte each, holding a tile index:

```python
self.ground[col, row] = WINDOWS        # (column, row) order
tile = self.ground[col, row]
self.ground.fill(PLATE)                # every cell
```

Dark or black backgrounds work better on the real Ventilastation, so draw a wall
in near-black tiles and keep the colour for a few lit structures, the way
`trench.png` does. (Always check your colours and intensities on the real
hardware; see [Budgets and real hardware](budgets.md).)

{py:data}`vs2.EMPTY_TILE` (255) leaves a cell blank and the renderer skips it.
Freshly allocated grids are filled with it, so a new tilemap starts out dark.
Here is a 16 by 16 map of the tiles above: a ring of pipe at the rim, a ring of
glowing conduit further in, and some windows, vents and lights between them, with
a ship on top. The map wraps all the way round the tunnel:

```{figure} ../images/tilemaps.png
:alt: A dark tunnel wall of near-black plating with a ring of cyan conduit, orange vents, amber windows and a ring of pipe at the rim, and a ship at the top
:width: 60%
:align: center

A 16 by 16 tilemap on a `TUNNEL` layer. Tiles near the rim are drawn larger.
```


### Scrolling

The {term}`view` is a fixed window onto the grid. Scrolling moves the window,
not the data, so it costs one write:

```python
def update(self):
    self.ticks += 1
    pattern_height = 6 * self.ground.tile_height     # the wall repeats every 6 rows
    self.ground.view_y = (self.ticks // 2) % pattern_height
```

If the picture repeats every 6 rows, the view can wrap back to the top after 6
rows and nobody can tell: the wall scrolls forever without a single cell being
rewritten. A map that does not repeat has to rewrite a row of cells each time a
whole tile has scrolled past instead, which is still much cheaper than rewriting
the grid every tick.

## Labels

A {term}`label` is a tilemap you write strings into. Three lines of text as
sprites cost 54 of your 100 slots; as labels they cost one tilemap record each,
no matter how often the text changes.

```python
def build(self):
    hud = self.layer("hud", projection=vs2.HUD)
    self.score  = hud.label("numerals.png", columns=5, x=246, y=1)   # bottom of the disc: upright
    self.status = hud.label("tinyfont.png", columns=21, rows=3, x=-42, y=0)
    self.title  = hud.label("steel8x8.png", columns=18, text="READY")
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
:alt: A score reading 00420 upright at the top and at the bottom of the disc, over a dark tunnel wall
:width: 60%
:align: center

Two labels: one at the top with `flip_x` and `flip_y`, one at the bottom with no flips.
```

### Glyphs

A label shows a character by picking the {term}`glyph` frame for it. By default
that is {term}`CP437`, where `frame = ord(ch)` — what `steel8x8.png` and the
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
before any tilemap for the world.
:::

## In the game

Give Tunnel Shooter a trench to fly down, and a score. The setting is a derelict
space station: you fly along a maintenance trench between plates of dark hull,
and the colour is in the lit structures on the walls. `trench.png` is the tileset
you saw above, and the wall repeats every six rows, which is what lets it scroll
forever.

A second layer holds the score, so it is drawn over everything in the world. The
wall goes into the world layer *before* the ship, so the ship is painted over it:

```python
# The trench's tiles, in the order they appear in trench.png.
PLATE, SEAM, PIPE, WINDOWS, VENT, HAZARD, LIGHTS, CONDUIT = range(8)
TRENCH_COLUMNS = 16  # around the tunnel
TRENCH_ROWS = 16     # along it
PATTERN_ROWS = 6     # the wall repeats every 6 rows, so it can scroll forever


def trench_tile(col, band):
    """Which tile goes at ``col`` in row ``band`` of the repeating pattern."""
    if band == 0:
        return PIPE
    if band == 4:
        return CONDUIT
    if band == 2:
        if col % 4 == 1:
            return WINDOWS
        if col % 4 == 3:
            return VENT
    if band == 5:
        if col % 8 == 2:
            return LIGHTS
        if col % 8 == 6:
            return HAZARD
    return SEAM if col % 2 else PLATE


def build(self):
    self.world = self.layer("world", projection=vs2.TUNNEL)
    self.hud = self.layer("hud", projection=vs2.HUD)

    # The trench wall: dark plating all the way round, with a few lit
    # structures. Its pattern repeats every PATTERN_ROWS rows.
    self.ground = self.world.tilemap(
        "trench.png", columns=TRENCH_COLUMNS, rows=TRENCH_ROWS,
        view_width=256, view_height=160)
    self.draw_trench()

    self.ship = self.world.sprite("ship.png", x=128, y=0)
    # ... the pools, as before ...

    # Bottom of the disc, so the score reads upright.
    self.score_label = self.hud.label("numerals.png", columns=5, x=246, y=1)

    self.score = 0
    self.ticks = 0
    self.show_score()

def draw_trench(self):
    for row in range(TRENCH_ROWS):
        for col in range(TRENCH_COLUMNS):
            self.ground[col, row] = trench_tile(col, row % PATTERN_ROWS)

def show_score(self):
    self.score_label.set_number(self.score, width=5, pad="0")
```

Scroll the wall toward the ship in `update()`, right after the ship's animation:

```python
    # Scroll the wall toward the ship. After one whole pattern the picture
    # is the same again, so the view can wrap without rewriting any cells.
    pattern_height = PATTERN_ROWS * self.ground.tile_height
    self.ground.view_y = (self.ticks // 2) % pattern_height
```

Add the points when a shot hits, in `move_shots()`:

```python
POINTS = 10

            self.enemies.despawn(enemy)
            boom = self.booms.spawn(x=enemy.x, y=enemy.y)
            boom.frame = 0
            self.shots.despawn(shot)
            self.score += POINTS
            self.show_score()
```

`numerals.png` declares its own glyphs in `__images__.yaml`, as in the glyphs
section above, so `set_number()` knows which frame is which digit. The score sits
at `x = 246`, the bottom of the disc, so it reads upright without any flips:

```{figure} ../images/game-play.png
:alt: Tunnel Shooter: a dark trench wall with a cyan conduit ring, amber windows and orange vents, a ship at the top, a shot, enemies, and a score at the bottom
:width: 60%
:align: center

Tunnel Shooter so far.
```

Next: [scenes, input and sound](scenes-and-input.md).
