# Layers and drawables

Everything drawn belongs to a layer, and every layer belongs to a scene:

```{figure} ../images/layer-tree.png
:alt: A scene holds layers; a layer holds sprites, sprite pools, tilemaps and labels
:width: 100%
:align: center

How a scene is put together.
```

Layers create their own drawables — there is no free-standing `Sprite(...)` —
and the projection belongs to the layer, not to its drawables.

All drawables share `x`, `y`, `visible`, `show()` and `hide()`. Coordinates are
signed and fractional. X is an angle that wraps at {py:data}`vs2.display.width`
(256), and Y is measured inward from the rim. What Y means depends on the
layer's projection; see [the circular display](../tutorial/display.md).

## Layer

```{eval-rst}
.. autoclass:: vs2.Layer
   :members: sprite, sprite_pool, tilemap, label, projection, visible,
             sprites, tilemaps
   :member-order: bysource
```

## Sprite

```{eval-rst}
.. autoclass:: vs2.Sprite
   :members:
   :member-order: bysource
```

## SpritePool

```{eval-rst}
.. autoclass:: vs2.SpritePool
   :members:
   :special-members: __len__, __iter__
   :member-order: bysource
```

## Tilemap

```{eval-rst}
.. autoclass:: vs2.Tilemap
   :members:
   :special-members: __getitem__, __setitem__
   :member-order: bysource
```

## Label

```{eval-rst}
.. autoclass:: vs2.Label
   :members: text, write, set_number
   :member-order: bysource
   :show-inheritance:
```

## Image

```{eval-rst}
.. autoclass:: vs2.Image
   :members:
```
