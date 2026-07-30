# Ventilastation VS2

VS2 is the API for writing Ventilastation games in MicroPython. A game
describes its display once, as a fixed graph of layers and drawables, and then
spends the rest of its life moving that graph around. Nothing is allocated
while the game runs, so the renderer can keep feeding the spinning LED bar a
fresh column every rotation tick without a garbage collection pause landing on
a visible frame.

Here is a complete game:

```python
import vs2
from vs2.controls import *


class MyGame(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)

        self.ship = self.world.sprite("ship.png", x=120.5, y=0)
        self.bullets = self.world.sprite_pool("shot.png", count=8)
        self.score = self.hud.label("digits.png", columns=5, x=100, y=1)

    def update(self):
        if joy1.held(LEFT):
            self.ship.x -= 0.5
        if joy1.held(RIGHT):
            self.ship.x += 0.5

        if joy1.just_pressed(A):
            self.bullets.spawn(x=self.ship.x, y=self.ship.y + 4)


def main():
    return MyGame()
```

There is no exit code in that game because it does not need any: the back
button and the idle timeout return to the launcher on their own.

## Start here

**[Tutorial](tutorial/index.md)** — seven short chapters that build a game from
an empty folder: the circular display, sprites and pools, tilemaps and text,
scenes and input, and what the budgets mean when you move to real hardware.

**[API reference](reference/index.md)** — every class, method and constant in
`vs2` and `vs2.controls`, generated from the source.

## The shape of a game

A game folder lives at `games/<group>/<name>/` and holds `code/`, `images/`,
`sounds/`, a `menu.png` icon, and a `meta.json` that opts into this API:

```json
{
  "api": "vs2",
  "api_revision": 2
}
```

Your `code/<name>.py` defines a {py:class}`~vs2.Scene` subclass and a `main()`
that returns an instance of it. The launcher finds the game by the folder
existing — there is no registry to edit.

Three rules explain most of the API:

Layers own drawables
: There is no free-standing `Sprite(...)`. A drawable is created by the layer
  that will draw it, with {py:meth}`~vs2.Layer.sprite`,
  {py:meth}`~vs2.Layer.sprite_pool`, {py:meth}`~vs2.Layer.tilemap` or
  {py:meth}`~vs2.Layer.label`, so a drawable that nothing owns cannot exist.

Build and run are separate phases
: {py:meth}`~vs2.Scene.build` creates the graph. When it returns, the scene is
  *sealed*: {py:meth}`~vs2.Scene.update` may move and re-frame what already
  exists, but may not create more. Running out of sprites becomes an error the
  first time you enter the scene, not a surprise ten minutes into play.

Draw order is layer order, then creation order
: Layers paint bottom to top in the order you create them, and within a layer
  each drawable paints over the ones created before it — sprites, tilemaps and
  labels alike.

```{toctree}
:hidden:
:maxdepth: 2

tutorial/index
reference/index
```
