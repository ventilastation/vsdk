# Glossary

The terms the tutorial and reference introduce, in alphabetical order. In the
tutorial, the first use of most of them links back here.

```{glossary}
:sorted:

API revision
  The `"api_revision": 2` line in `meta.json`. It must accompany `"api": "vs2"`.
  See [Your first game](tutorial/first-game.md).

Asset pack
  The images and sounds a game loads, compiled into a {term}`ROM`. It defaults
  to your own game's folder, so you rarely name it. Each pack has its own
  {term}`budget` of image strips.

Back button
  The `Y` or `BACK` button. By default it pops the current {term}`scene`; set
  {py:attr}`~vs2.Scene.back_button` to `False` to use those buttons in play.

Budget
  A fixed limit on how many layers, sprites, tilemaps and image strips a game
  may use. Exceeding one raises an error the first time the scene is entered.
  See [Budgets and real hardware](tutorial/budgets.md).

Build
  {py:meth}`Scene.build() <vs2.Scene.build>`. It runs once each time a scene is
  entered and creates everything the scene will draw. When it returns, the scene
  is {term}`sealed`.

Cell
  One byte in a {term}`tilemap`'s grid. It holds a {term}`tile` index, or
  {py:data}`vs2.EMPTY_TILE` for "draw nothing".

Census
  The per-layer breakdown in a `ResourceLimitError` message, such as
  `(world: 62, hud: 39)`. It shows which layer is over {term}`budget`.

Column
  One slice of the display: the colour of all 54 LEDs at a single angle. The
  renderer is asked for 256 of them per {term}`rotation`.

Console
  The real Ventilastation machine, as opposed to the {term}`emulator`.

CP437
  The default {term}`glyph` mapping, where a character's frame is `ord(ch)`.
  Full font strips such as `steel8x8.png` use it.

Depth
  What Y means on a {py:data}`vs2.TUNNEL` layer: `0` at the {term}`rim`, `255`
  at the centre. Objects shrink as depth grows.

Display
  The disc the {term}`rotor` sweeps out. X is an angle that wraps around it; Y is
  a distance inward from the {term}`rim`. See
  [The circular display](tutorial/display.md).

Drawable
  Anything a {term}`layer` draws: a {term}`sprite`, a {term}`sprite pool
  <pool>`, a {term}`tilemap` or a {term}`label`. A layer creates its own
  drawables; there is no free-standing `Sprite(...)`.

Edge
  An input test that is true for exactly one {term}`tick`:
  {py:meth}`~vs2.controls.joy1.just_pressed` and
  {py:meth}`~vs2.controls.joy1.just_released`. Compare {term}`level`.

Emulator
  Runs your game on a computer with the same renderer semantics as the
  {term}`console`. It does not enforce the per-column deadline.

Flip
  `flip_x=True` mirrors a sprite, tilemap or label left to right and
  `flip_y=True` mirrors it top to bottom. Both together turn it through 180
  degrees, which is how a label reads upright at the top of the {term}`display`.
  See [Tilemaps and text](tutorial/tilemaps-and-text.md).

Frame
  One image inside a {term}`strip`, counted from 0. Setting a sprite's frame
  never changes whether it is {term}`visible`.

Glyph
  The image frame that stands for one character. A *glyph table* maps
  characters to frames. See [Tilemaps and text](tutorial/tilemaps-and-text.md).

Garbage collection
  How MicroPython frees memory that nothing refers to any more. On the
  {term}`console` it runs only when a scene starts or ends, so garbage made every
  tick piles up until then and a long game can run out of memory; the desktop
  emulator collects automatically and pauses instead. VS2 avoids both by
  creating everything in {term}`build` and reusing it with {term}`pools <pool>`.
  See [Why VS2 works this way](design-notes.md).

Idle timeout
  Seconds without input from either controller before
  {py:meth}`~vs2.Scene.on_idle` fires. The default pops the scene.

Image
  A {term}`strip` as loaded from the {term}`ROM`. Its id defaults to its
  filename, and {py:attr}`~vs2.Image.frames` says how many frames it has.

Label
  A {term}`tilemap` you write strings into, with `text`, `write()` and
  `set_number()`. It counts against the tilemap {term}`budget`.

Launcher
  The console's menu. It finds your game by its folder, so there is nothing to
  register.

Layer
  An ordered container of {term}`drawables <drawable>` with a {term}`projection`
  and a `visible` flag. Layers paint bottom to top in creation order.

LED
  One of the 54 lights on the spinning bar. On a {py:data}`vs2.HUD` layer, Y
  is an LED index.

Level
  An input test that is true while a button is down:
  {py:meth}`~vs2.controls.joy1.held`. Compare {term}`edge`.

MicroPython
  A compact implementation of Python 3 for microcontrollers. Games are written in
  it and run on the {term}`console`'s ESP32-S3, with limited memory and CPU.

Palette group
  A set of images in `__images__.yaml` that share one 256-colour palette. Put
  images that look alike in the same group.

Pool
  A fixed group of sprites reserved in `build()` with
  {py:meth}`~vs2.Layer.sprite_pool`. You {term}`spawn` and {term}`despawn`
  from it instead of creating sprites while the game runs.

Projection
  How a layer turns Y into LEDs: {py:data}`vs2.TUNNEL`, {py:data}`vs2.HUD` or
  {py:data}`vs2.FULLSCREEN`. It belongs to the layer, not to its drawables.

Recycle
  `on_empty=vs2.RECYCLE` on a {term}`pool`. An exhausted pool then reuses its
  oldest live sprite instead of returning `None`.

Rim
  The outer edge of the {term}`display`, at `y = 0`.

ROM
  The compiled form of a game's images and sounds. Frame counts and image sizes
  are read from it.

Rotation
  One full sweep of the bar around the disc, a few times per second. It is not
  tied to {py:meth}`~vs2.Scene.update`: at the fan's usual 400 to 700 RPM there
  are three to five {term}`ticks <tick>` per rotation.

Rotor
  The spinning arm that carries the LED bar.

Scene
  One screen of a game: a subclass of {py:class}`vs2.Scene` with a `build()` and
  an `update()`. A game is usually several scenes.

Sealed
  The state of a scene after `build()` returns. Existing drawables can be moved,
  re-framed, shown and hidden, but creating new ones raises
  {py:exc}`vs2.SceneSealedError`.

Spawn
  Take a free sprite from a {term}`pool`, position it and show it:
  {py:meth}`SpritePool.spawn() <vs2.SpritePool.spawn>`. It returns `None` when
  the pool is empty. Opposite of {term}`despawn`.

Despawn
  Hide a sprite and return it to its {term}`pool`:
  {py:meth}`SpritePool.despawn() <vs2.SpritePool.despawn>`. Despawning a sprite
  twice raises `ValueError`.

Sprite
  One image on a {term}`layer`, with `x`, `y`, `frame` and `visible`.

Strip
  A horizontal filmstrip of equally sized {term}`frames <frame>` in one PNG. A
  four-frame animation is a PNG four times as wide as one frame.

Tick
  One call to `update()`. Ticks come every 30 ms, about 33 a second, whatever the
  fan speed.

Tile
  One picture in a tilemap's tileset, referred to by its frame number. Tile
  size comes from the image.

Tilemap
  A grid of {term}`cells <cell>` drawn from a tileset strip, costing one
  renderer record however many cells it has. Good for terrain and backdrops.

Timer
  A callback queued with {py:meth}`~vs2.Scene.call_later`. Pending timers are
  discarded when the scene is popped or suspended.

Transition
  {py:meth}`~vs2.Scene.push`, {py:meth}`~vs2.Scene.pop` or
  {py:meth}`~vs2.Scene.switch`. It is queued and committed at the end of the
  {term}`tick`.

View
  The fixed window a tilemap shows onto its grid. Scrolling moves the view
  (`view_x`, `view_y`), not the data.

Visible
  Whether a drawable or layer is drawn. It is independent of a sprite's
  {term}`frame`.
```
