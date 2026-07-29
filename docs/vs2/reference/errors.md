# Errors and constants

## When things go wrong

VS2 tries to fail at the line that caused the problem, during `build()`, rather
than rendering something wrong later. These are the errors you will actually
meet.

```{eval-rst}
.. autoexception:: vs2.SceneSealedError
   :show-inheritance:

.. autoexception:: vs2.ResourceLimitError
   :show-inheritance:

.. autoexception:: vs2.AssetLimitError
   :show-inheritance:

.. autoexception:: vs2.AssetNotFoundError
   :show-inheritance:

.. autoexception:: vs2.FrameError
   :show-inheritance:
```

### Reading the messages

```text
AssetNotFoundError: image 'ships.png' is not in alecu.my_game
```

A typo, or the PNG is not in the game's `images/` folder. The name is the
image's id, which defaults to its filename.

```text
FrameError: ship.png has 4 frames; frame must be 0..3
```

An out-of-range frame. Frame counts come from the ROM, so
`sprite.image.frames` is the authority — do not hard-code them.

```text
ResourceLimitError: sprite 101/100 in Vixeous (world: 62, hud: 39);
  reduce the sprite budget
```

The census names every layer holding sprites, so the oversized one is visible
without counting by hand. Shrink a `sprite_pool`, or move text from sprites to a
{py:class}`~vs2.Label` — three lines of text as sprites cost 54 slots, and as a
label cost one tilemap.

```text
SceneSealedError: sprite() is only allowed while MyGame.build() runs
```

Something tried to create a drawable from `update()` or a timer. Preallocate it
in `build()`, usually as a {py:class}`~vs2.SpritePool`.

```text
SceneSealedError: cannot change x on a sprite from a closed V2 scene
```

A drawable handle outlived its scene — often a handle stashed on `self` in
`__init__` instead of being rebuilt in `build()`.

## Constants

### Projections

Passed to {py:meth}`Scene.layer <vs2.Scene.layer>` as `projection=`, and
decide how a layer maps Y to LEDs.

```{eval-rst}
.. py:data:: vs2.TUNNEL
   :value: 1

   Perspective. Y is depth, ``0..255``: 0 sits just outside the display and is
   not drawn, around 16 an object is fully visible at the rim, and it shrinks
   and converges toward the centre, reached at 255. The usual choice for a game
   world.

.. py:data:: vs2.HUD
   :value: 2

   Flat, no perspective. Y is a direct LED index measured inward from the rim,
   ``0..53``, so ``y = 0`` is the outermost LED. A sprite ``h`` tall stays
   fully on screen up to ``y = 54 - h``. The usual choice for scores and
   overlays, which are most legible at low Y.

.. py:data:: vs2.FULLSCREEN
   :value: 0

   One image over the whole disc, for backdrops and planets. Always centred: Y
   scales it down from full size and X rotates it. Sprites only — creating a
   tilemap or label on a ``FULLSCREEN`` layer raises during ``build()``.
```

### Tiles and pools

```{eval-rst}
.. py:data:: vs2.EMPTY_TILE
   :value: 255

   A tilemap cell that draws nothing. Newly allocated cell buffers are filled
   with it, and :py:meth:`Label.write <vs2.Label.write>` pads with it.

.. py:data:: vs2.TRANSPARENT
   :value: 255

   The palette index the renderer treats as see-through.

.. py:data:: vs2.RECYCLE

   Passed as ``on_empty=`` to
   :py:meth:`Layer.sprite_pool <vs2.Layer.sprite_pool>`. An exhausted pool then
   reuses its oldest live sprite instead of returning ``None`` — the right
   default for explosions and particles, where dropping one is worse than
   cutting another short.
```
