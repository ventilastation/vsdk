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

| Error | Usual cause | What to do |
|---|---|---|
| `AssetNotFoundError: image 'ships.png' is not in alecu.my_game` | A typo, or the PNG is not in the game's `images/` folder. The name is the image's id, which defaults to its filename. | Fix the name or add the image. |
| `FrameError: ship.png has 4 frames; frame must be 0..3` | A frame out of range. | Use `sprite.image.frames` instead of a hard-coded count. |
| `ResourceLimitError: sprite 101/100 in Vixeous (world: 62, hud: 39)` | Over a {term}`budget`. The {term}`census` shows which layer is largest. | Shrink a pool, or move text from sprites to a {py:class}`~vs2.Label`. See [Budgets](../tutorial/budgets.md). |
| `SceneSealedError: sprite() is only allowed while MyGame.build() runs` | A drawable was created from `update()` or a timer. | Create it in `build()`, usually as a {py:class}`~vs2.SpritePool`. |
| `SceneSealedError: cannot change x on a sprite from a closed V2 scene` | A drawable handle outlived its scene, often one stored in `__init__`. | Create drawables in `build()`, not `__init__`. |

## Constants

### Projections

Passed to {py:meth}`Scene.layer <vs2.Scene.layer>` as `projection=`, and
decide how a layer maps Y to LEDs. The tutorial's
[circular display](../tutorial/display.md) chapter explains them with examples.

```{eval-rst}
.. py:data:: vs2.TUNNEL
   :value: 1

   Perspective. Y is depth, ``0..255``, from the outermost ring to the centre.
   The usual choice for a game world.

.. py:data:: vs2.HUD
   :value: 2

   Flat, no perspective. Y is a direct LED index, ``0..53``, so ``y = 0`` is the
   outermost LED. The usual choice for scores and overlays, which are most
   legible at low Y.

.. py:data:: vs2.FULLSCREEN
   :value: 0

   One centred image, for planets, backdrops and cloud cover. ``y = 0`` fills all 54 LEDs and
   larger Y contracts it toward the centre. Sprites only — creating a tilemap or
   label on a ``FULLSCREEN`` layer raises during ``build()``.
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
