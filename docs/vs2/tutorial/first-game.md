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

`api` and `api_revision` are required together — the loader refuses a `vs2` game
without `"api_revision": 2`, so a game written against an older draft of the API
fails at load with a clear message instead of misbehaving. `title` and `order`
control the menu entry.

:::{note}
A game uses VS2 **or** the older `ventilastation.sprites` API, never both.
Importing both from one game is rejected on purpose.
:::

## Images

Ventilastation cannot open PNGs directly. `images/__images__.yaml` describes how
they become sprite strips:

```yaml
palettegroups:
  world:
    - strip: ship.png
      frames: 1
    - strip: shot.png
      frames: 1
```

A **strip** is a horizontal filmstrip of equally sized frames — a 4-frame
animation is one PNG four times as wide as one frame. A **palette group** is a
set of images that share 256 colours; put images that look alike in one group.

The emulator recompiles changed PNGs into a ROM every time it starts, so you
just edit and rerun.

## The code

`code/mygame.py` needs a {py:class}`~vs2.Scene` subclass and a `main()` that
returns an instance:

```python
import vs2
from vs2.controls import *


class MyGame(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.ship = self.world.sprite("ship.png", x=128, y=0)

    def update(self):
        if joy1.held(LEFT):
            self.ship.x -= 1
        if joy1.held(RIGHT):
            self.ship.x += 1


def main():
    return MyGame()
```

That is a complete, playable game. Run `./vs-emu.sh` (or `vs-emu.bat`) and it is
on the menu — there is no registry to edit, the launcher discovers game folders.

## What those two methods mean

{py:meth}`~vs2.Scene.build` runs once each time the scene is entered and creates
everything the scene will ever draw. {py:meth}`~vs2.Scene.update` runs once per
rotation and moves what already exists.

The split is enforced, not just conventional. When `build()` returns, the scene
is **sealed**: try to create a sprite from `update()` and you get

```text
SceneSealedError: sprite() is only allowed while MyGame.build() runs
```

That is the point. Running out of sprites becomes an error the first time you
enter the scene — reproducible, at a known line — instead of a crash ten minutes
into play when a boss spawns one too many.

## What you did not have to write

No exit handling: the back button (`Y` or `BACK`) and a 30-second idle timeout
both return to the launcher on their own. No `super()` call. No ROM name — the
asset pack defaults to your game. No director import.

Next: [the circular display](display.md), and why `x` behaves differently from
`y`.
