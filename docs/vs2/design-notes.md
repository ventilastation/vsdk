# Why VS2 works this way

You do not need this page to write a game. It explains the reasons behind the
rules you meet in the tutorial, so they are easier to remember.

## The physical display has a deadline

The display is a bar of 54 LEDs on a spinning arm. A column has to be ready
before the arm reaches it. The current renderer projects scenes into two polar
framebuffers; physical LED-column service uses the published buffer independently
of the projection work. Game updates are independent of rotation timing.
See [hardware acceptance](../internals/vs2-hardware-acceptance.md) for the separate
projection and column-service budgets.

## The hardware is small

Games are written in MicroPython, which runs on the console's ESP32-S3: two cores
at 240 MHz, with about 8 MB of external RAM shared between the interpreter's heap
and the image strips. Sound never lives on the console: the base station plays your
game's MP3s when the code asks for them. One core runs MicroPython and your game; the
other runs the renderer and the LED output, which is timing-critical. The
renderer reads the sprite and tilemap records that Python created directly, in
place, rather than being handed copies.

Your game's `update()` is called on a fixed 30 ms timer, about 33 times a second,
whatever the fan speed. The renderer does not wait for it: on the console it
draws on its own, driven by the hall sensor, and at 400 to 700 RPM there are three
to five updates per rotation. A tick that takes longer than 30 ms is not
caught up on.

MicroPython frees memory with a garbage collector that stops the interpreter while
it walks the heap. The console's director turns automatic collection off, so
there are no surprise pauses in the middle of a tick, and runs the collector
itself when a scene is pushed, popped or switched. The catch is that garbage made
in `update()` is not freed until then, so a game that allocates every tick fills
the heap and can run out of memory mid-game. The desktop emulator keeps
automatic collection on, so there the same habit shows up as occasional pauses.

## The display graph is fixed

Everything a scene draws is created once, in `build()`. After that, moving
something is a write into a record the renderer already holds. Sealing prevents new render objects; it cannot prevent your Python code from
allocating tuples, strings or other temporary objects. Build once and reuse
objects, and measure heap behavior for frequent updates. Timers also store their
callbacks and arguments.

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
a session it is the difference between a stable heap and one that fills up before
the next scene change.

## Layers own drawables

A drawable is created by the layer that will draw it, so one that nothing
owns cannot exist. A layer's projection is layer state, not sprite state, so
attaching a drawable can never silently change how it is drawn.

## Failures happen early

Most mistakes — a missing image, a frame out of range, too many sprites, a
structural call after `build()` — raise at the line that caused them, instead
of rendering something wrong later.
