# 3. Sprites

A {term}`sprite` is one image on a {term}`layer`. The layer creates it:

```python
def build(self):
    world = self.layer("world", projection=vs2.TUNNEL)
    self.ship = world.sprite("ship.png", x=128, y=0)
```

## Moving and animating

Every attribute writes straight into the renderer's record, so these are cheap
enough to do on every sprite, every {term}`tick`:

```python
def update(self):
    self.ship.x += 0.5              # angle; wraps at 256
    self.ship.y = 20                # depth on a TUNNEL layer; 0 is the rim
    self.ship.frame = (self.ship.frame + 1) % self.ship.image.frames
    self.ship.flip_x = self.moving_left
```

A sprite shows one {term}`frame` of its strip at a time. A walking character is
the clearest example, since each frame is a different step of the stride. Here are
four sprites showing frames 0 to 3 of `mario_runs.png` (art from the `vugo` game,
in `games/pycamp-mar25/vugo/images/`), set side by side at the bottom of the disc
with a gap between them:

```{figure} ../images/sprites-frames.png
:alt: Four copies of a walking character along the bottom of the disc, each in a different pose of the stride
:width: 60%
:align: center

`frame = 0, 1, 2, 3`: one strip, four poses. The outer two lean because they sit
further round the curve of the disc.
```

`frame` and `visible` are **independent axes**. Setting a frame never reveals a
hidden sprite, which is what lets you prepare something before showing it:

```python
shot.frame = BULLET_FRAME    # still hidden
shot.show()                  # now visible, same frame
```

An out-of-range frame raises at the assignment rather than rendering garbage:

```text
FrameError: ship.png has 4 frames; frame must be 0..3
```

## Frame counts and sizes

Don't hard-code the number of frames. {py:attr}`Image.frames <vs2.Image.frames>`
is read from the {term}`ROM`, so it stays right when you add a frame to the PNG.
The same goes for size: {py:attr}`~vs2.Sprite.width` and
{py:attr}`~vs2.Sprite.height` come from the image:

```python
self.ship.x = target.x - self.ship.width // 2      # centre on the target
```

## Swapping the image

Assigning to {py:attr}`~vs2.Sprite.image` swaps the artwork in place. The frame
is kept if it is still in range, and reset to 0 if not:

```python
self.ship.image = "ship_damaged.png"
```

## Collisions

Two allocation-free axis-aligned tests, with the circular X handled for you:

```python
if shot.overlaps(enemy):
    ...

target = shot.first_overlap(self.enemies)   # a Sprite, or None
if target:
    ...
```

{py:meth}`~vs2.Sprite.first_overlap` takes any iterable of sprites, including a
pool — which is the next chapter.

:::{note}
X wrapping is handled: a sprite straddling column 0 collides correctly with one
at column 254. Y does not wrap, because the disc has an inside and an outside.
:::

## In the game

Let the ship's engine glow flicker by cycling through its four frames. `update()`
runs once per rotation, so count the calls and change frame every few of them
instead of on every one:

```python
def build(self):
    self.world = self.layer("world", projection=vs2.TUNNEL)
    self.ship = self.world.sprite("ship.png", x=128, y=0)
    self.ticks = 0                              # counts update() calls

def update(self):
    self.ticks += 1
    # ... steering, as before ...
    self.ship.frame = (self.ticks // 4) % self.ship.image.frames
```

`self.ticks // 4` stays the same for four ticks in a row, so the frame changes
four times more slowly than `update()` runs. `self.ship.image.frames` supplies
the number of frames, so the line keeps working if you give the ship more frames
later.

Next: [sprite pools](pools.md), for everything you need many of. To share one
image handle between several sprites, see [going further](../going-further.md).
