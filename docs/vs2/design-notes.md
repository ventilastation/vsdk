# Why VS2 works this way

You do not need this page to write a game. It explains the reasons behind the
rules you meet in the tutorial, so they are easier to remember.

## The display has a deadline, not a framebuffer

The display is a bar of 54 LEDs on a spinning arm. The renderer is asked, 256
times per rotation, "what colour is each LED at this angle?" and answers by
walking your scene. A column has to be ready before the arm reaches it, so the
answer must be cheap.

## The display graph is fixed

Everything a scene draws is created once, in `build()`. After that, moving
something is a write into a record the renderer already holds. Nothing is
allocated while the game runs, so no garbage collection pause can land on a
visible frame.

That one idea explains several rules:

- The scene is **sealed** after `build()`, so a game that would run out of
  sprites fails the first time the scene is entered, at a known line, instead
  of ten minutes into play when a boss spawns one too many.
- **Pools** reserve their sprites up front. The sprite {term}`budget` is spent
  in a few numbers you can add up, and a game cannot quietly exceed it.
- **Labels** write digits and text straight into tilemap cells, and
  {py:meth}`~vs2.Label.set_number` exists so a score never needs a formatted
  string. `view_x` and `view_y` are two scalars rather than a viewport tuple.
- **Budgets** are checked at `build()`, so you find out then rather than
  mid-game.

A per-frame tuple, dict or formatted string is not "a little garbage" here: over
a session it is the difference between a stable heap and a pause landing on a
visible frame.

## Layers own drawables

A drawable is created by the layer that will draw it, so one that nothing
owns cannot exist. A layer's projection is layer state, not sprite state, so
attaching a drawable can never silently change how it is drawn.

## Failures happen early

Most mistakes — a missing image, a frame out of range, too many sprites, a
structural call after `build()` — raise at the line that caused them, instead
of rendering something wrong later.
