# Layers and drawables

Everything drawn belongs to a layer, and every layer belongs to a scene:

```text
Scene
 └─ Layer            ordered bottom → top
     └─ Drawable     ordered bottom → top within the layer
         ├─ Sprite
         ├─ SpritePool   (a fixed group of Sprites)
         ├─ Tilemap
         └─ Label        (a Tilemap with text helpers)
```

Two rules follow from that shape:

- **Layers create their own drawables.** There is no free-standing
  `Sprite(...)`; {py:meth}`~vs2.Layer.sprite` and friends allocate and attach in
  one step, so a drawable nothing owns cannot exist.
- **Projection is layer state.** Drawables neither take nor store a projection,
  so attaching one can never silently change how it is drawn.

All drawables share `x`, `y`, `visible`, `show()` and `hide()`. Coordinates are
signed and fractional.

X is an angle: 0 at the bottom, 64 left, 128 top, 192 right, wrapping at
{py:data}`vs2.display.width` (256).

Y is measured **inward from the rim**, so `y = 0` is the outermost LED. Its
range depends on the layer's projection — `0..53` on a {py:data}`vs2.HUD`
layer, where it is a direct LED index, and `0..255` on a {py:data}`vs2.TUNNEL`
layer, where it is depth and the centre is 255. Out-of-range values clip.
See [the circular display](../tutorial/display.md) for the full picture.

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
