# Ventilastation VS2

VS2 is the API for writing Ventilastation games in MicroPython. A game
creates what it wants to draw once, in `build()`, and then moves those things
around in `update()`.

Here is a complete, very small program: a ship you can steer, and a score that
goes up when you press A.

```python
import vs2
from vs2.controls import *


class MyGame(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)

        self.ship = self.world.sprite("ship.png", x=128, y=0)
        self.score = self.hud.label("numerals.png", columns=5, x=246, y=1)
        self.points = 0
        self.score.set_number(self.points, width=5, pad="0")

    def update(self):
        if joy1.held(LEFT):
            self.ship.x -= 0.5
        if joy1.held(RIGHT):
            self.ship.x += 0.5

        if joy1.just_pressed(A):
            self.points += 10
            self.score.set_number(self.points, width=5, pad="0")


def main():
    return MyGame()
```

The back button and the idle timeout return to the launcher on their own, so
the game needs no exit code.

## Start here

**[Tutorial](tutorial/index.md)** — seven short chapters that build a game from
an empty folder: the circular display, sprites and pools, tilemaps and text,
scenes and input, and what the budgets mean when you move to real hardware.

**[API reference](reference/index.md)** — every class, method and constant in
`vs2` and `vs2.controls`, generated from the source. Its
[cheat sheet](reference/index.md#cheat-sheet) is the quickest way to find the
call you want.

**[Glossary](glossary.md)** — what *layer*, *sealed*, *strip*, *projection* and
the rest mean.

Also: [going further](going-further.md) for features you can skip at first, and
[why VS2 works this way](design-notes.md).

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
that returns an instance of it. The launcher finds the game by its folder.

Three rules explain most of the API:

Layers own drawables
: A drawable is created by the layer that will draw it, with
  {py:meth}`~vs2.Layer.sprite`, {py:meth}`~vs2.Layer.sprite_pool`,
  {py:meth}`~vs2.Layer.tilemap` or {py:meth}`~vs2.Layer.label`.

Build and update are separate
: {py:meth}`~vs2.Scene.build` creates everything the scene draws. After it
  returns, the scene is {term}`sealed <sealed>`: {py:meth}`~vs2.Scene.update`
  can move what exists but cannot create more.

Draw order is layer order, then creation order
: Layers paint bottom to top in the order you create them, and within a layer
  each drawable paints over the ones created before it.

```{toctree}
:hidden:
:maxdepth: 2

tutorial/index
reference/index
glossary
going-further
design-notes
```
