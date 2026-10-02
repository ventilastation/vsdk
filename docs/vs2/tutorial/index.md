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

The Ventilastation display is a bar of 54 {term}`LEDs <LED>` on a spinning arm.
There is no framebuffer: the renderer is asked, 256 times per {term}`rotation`,
"what colour is each of these 54 LEDs at this angle?" and it answers by walking
your scene.

That means the display is a **disc**, not a rectangle: X is an angle that
wraps around, and Y is a distance inward from the rim that does not. Chapter 2
covers this in detail. If you want to know why the API is shaped the way it is,
see [why VS2 works this way](../design-notes.md).

Unlit space is black, and dark or black backgrounds work better on the real
display, so the examples in this tutorial leave most of the disc empty.

Terms like *layer*, *sealed* and *strip* are defined in the
[glossary](../glossary.md).
