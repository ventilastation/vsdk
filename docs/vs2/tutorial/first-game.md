# 1. Your first game

A game is a folder. Create one under your own group name:

```sh
mkdir -p games/myname/mygame/code games/myname/mygame/images
```

Four things go in it:

```text
games/myname/mygame/
├── code/mygame.py        your game; the module name matches the folder
├── images/               PNGs plus __images__.yaml
├── menu.png              the icon shown in the console menu
└── meta.json             how the launcher lists it
```

## meta.json

This is what opts your game into VS2:

```json
{
  "api": "vs2",
  "api_revision": 2,
  "title": "My Game",
  "order": 50
}
```

`api` and `api_revision` are both required. `title` and `order` control the
menu entry.

## Images

Ventilastation cannot open PNGs directly. `images/__images__.yaml` describes how
they become sprite strips:

```yaml
palettegroups:
  main:
    - strip: ship.png
      frames: 4
```

A {term}`strip` is a horizontal filmstrip of equally sized frames — a 4-frame
animation is one PNG four times as wide as one frame:

```{figure} ../images/strip-ship.png
:alt: The ship.png strip: four 18 by 13 pixel frames side by side
:width: 85%
:align: center

`ship.png` is 72 pixels wide and holds four frames, so its entry says `frames: 4`.
```

A {term}`palette group` is a set of images that share 256 colours; put images
that look alike in one group.

To follow along, copy the art Tunnel Shooter uses into your `images/` folder
from `games/demos/tutorial_game/images/`: `ship.png`, `shots.png`, `enemy.png`,
`explosion.png`, `trench.png`, `numerals.png` and `steel8x8.png`. You only
need `ship.png` for this chapter; the others appear later.

The emulator recompiles changed PNGs into a ROM every time it starts, so you
just edit and rerun.

## The code

`code/mygame.py` needs a {term}`scene` — a {py:class}`~vs2.Scene` subclass — and
a `main()` that returns an instance:

```python
import vs2
from vs2.controls import *


class Game(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.ship = self.world.sprite("ship.png", x=128, y=0)

    def update(self):
        if joy1.held(LEFT):
            self.ship.x -= 1
        if joy1.held(RIGHT):
            self.ship.x += 1


def main():
    return Game()
```

That is a complete, playable game. Run `./vs-emu.sh` (or `vs-emu.bat`) and it is
on the menu. The ship sits at the top of the disc, because `x = 128` is the top:

```{figure} ../images/first-game.png
:alt: The emulator showing the ship at the top of the disc
:width: 60%
:align: center

The ship at `x = 128`, `y = 0`: the top of the disc, on the rim.
```

Hold the left button and `x` counts down, so the ship slides toward the left
side of the disc:

```{figure} ../images/first-game-moved.png
:alt: The emulator showing the ship moved toward the upper left
:width: 60%
:align: center

After holding left for a moment.
```


## What those two methods mean

{term}`Build <build>` runs once each time the scene is entered and creates
everything the scene will ever draw. {py:meth}`~vs2.Scene.update` runs once per
{term}`rotation` and moves what already exists.

```{figure} ../images/scene-lifecycle.png
:alt: A scene starts building, becomes sealed when build returns, and is closed by pop, push or switch
:width: 100%
:align: center

A scene's life. Only the building state may create layers and drawables.
```

The split is enforced. When `build()` returns, the scene is {term}`sealed`: try
to create a sprite from `update()` and you get

```text
SceneSealedError: sprite() is only allowed while Game.build() runs
```

So running out of sprites becomes an error the first time you enter the scene,
not a surprise in the middle of play.

## Leaving the game

Players leave with the back button (`Y` or `BACK`), or after 30 seconds without
input. Both return to the launcher on their own, so your game needs no exit
code.

This ship is where Tunnel Shooter starts. Next: [the circular display](display.md),
and why `x` behaves differently from `y`.
