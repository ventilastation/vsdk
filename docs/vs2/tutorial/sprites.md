# 3. Sprites

A sprite is one image on a layer. The layer creates it, which is what makes it
impossible to have a sprite that nothing draws:

```python
def build(self):
    world = self.layer("world", projection=vs2.TUNNEL)
    self.ship = world.sprite("ship.png", x=128, y=0)
```

## Moving and animating

Every attribute writes straight into the renderer's record, so these are cheap
enough to do on every drawable, every tick:

```python
def update(self):
    self.ship.x += 0.5              # angle; wraps at 256
    self.ship.y = 20                # depth on a TUNNEL layer; 0 is the rim
    self.ship.frame = (self.ship.frame + 1) % self.ship.image.frames
    self.ship.flip_x = self.moving_left
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

## Frame counts come from the ROM

Don't hard-code them. {py:attr}`Image.frames <vs2.Image.frames>` is parsed from
the ROM, so it is right even after you add a frame to the PNG:

```python
self.ship.frame = (self.ship.frame + 1) % self.ship.image.frames
```

Same for size — {py:attr}`~vs2.Sprite.width` and {py:attr}`~vs2.Sprite.height`
are read from image metadata and cost no renderer call:

```python
self.ship.x = target.x - self.ship.width // 2      # centre on the target
```

## Swapping the image

Assigning to {py:attr}`~vs2.Sprite.image` swaps the artwork in place. The frame
is kept if it is still in range, and reset to 0 if not:

```python
self.ship.image = "ship_damaged.png"
```

## Resolving an image once

If several drawables share one image, resolve it once with
{py:meth}`Scene.image <vs2.Scene.image>` and pass the handle around:

```python
def build(self):
    enemy = self.image("enemy.png")
    self.small = self.world.sprite_pool(enemy, count=12)
    self.boss  = self.world.sprite(enemy, frame=4)
```

A typo is caught at `build()`:

```text
AssetNotFoundError: image 'enemyy.png' is not in myname.mygame
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

Next: [sprite pools](pools.md), for everything you need many of.
