# Tutorial

Seven short chapters that go from an empty folder to a game running on the
console. Each one builds on the last, so read them in order the first time.

You need the emulator installed — see the setup guides in the `docs/` folder for
Linux, macOS and Windows — and no hardware at all until the last chapter.

```{toctree}
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

The Ventilastation display is a bar of 54 LEDs on a spinning arm. There is no
framebuffer: the renderer is asked, 256 times per rotation, "what colour is each
of these 54 LEDs at this angle?" and it answers by walking your scene.

That single fact explains most of the API's shape. There is a hard deadline
every column, so the answer has to be cheap: the display graph is fixed while
the game runs, and moving something is a write into a record the renderer
already holds. It also means the display is a **disc**, not a rectangle — X is
an angle that wraps around, and Y is a distance inward from the rim that does
not.
