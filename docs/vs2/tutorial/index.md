# Tutorial

Seven short chapters that build one game, **Tunnel Shooter**, from an empty folder
to a game running on the console. You fly a ship around the rim of the disc and
shoot the enemies that come down the tunnel at you.

```{figure} ../images/game-play.png
:alt: Tunnel Shooter: a ship at the top of the disc, a shot flying away from it, enemies approaching, and a score at the bottom
:width: 60%
:align: center

Tunnel Shooter, the game you will build.
```

Each chapter teaches one part of the API and ends with an **In the game**
section that adds that part to the same file, so read them in order the first
time:

| Chapter | You learn | The game gets |
|---|---|---|
| [1. Your first game](first-game.md) | the folder, `build()` and `update()` | a ship you can steer |
| [2. The circular display](display.md) | X, Y, projections, draw order | a ship that flies all the way round |
| [3. Sprites](sprites.md) | frames, collisions | an animated ship |
| [4. Sprite pools](pools.md) | `spawn()` and `despawn()` | shots, enemies and explosions |
| [5. Tilemaps and text](tilemaps-and-text.md) | tilemaps, labels, flips | a scrolling trench wall and a score |
| [6. Scenes, input and sound](scenes-and-input.md) | scenes, timers, audio | a title screen, game over, sound |
| [7. Budgets and real hardware](budgets.md) | limits, testing on the disc | a finished game |

The finished game is in `games/demos/tutorial_game/`, and it shows up in the
**Tech Demos** menu. If you get stuck, compare your file with it.

You need the emulator installed — see the setup guides in the `docs/` folder for
Linux, macOS and Windows — and no hardware at all until the last chapter.

```{toctree}
:hidden:
:maxdepth: 1

first-game
display
sprites
pools
tilemaps-and-text
scenes-and-input
budgets
```

## What you are writing for

The Ventilastation display is a bar of 54 {term}`LEDs <LED>` on a spinning arm.
There is no framebuffer: the renderer is asked, 256 times per {term}`rotation`,
"what colour is each of these 54 LEDs at this angle?" and it answers by walking
your scene.

That means the display is a **disc**, not a rectangle: X is an angle that
wraps around, and Y is a distance inward from the rim that does not. Chapter 2
covers this in detail. If you want to know why the API is shaped the way it is,
see [why VS2 works this way](../design-notes.md).

Unlit space is black, and dark or black backgrounds work better on the real
display, so the examples in this tutorial keep their backgrounds dark: empty
space where there is nothing to show, and near-black tiles where a wall is. Test
your colours and intensities on the real hardware before you share a game.

Terms like *layer*, *sealed* and *strip* are defined in the
[glossary](../glossary.md).
