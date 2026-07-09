# How to make games and apps for Ventilastation

Ventilastation applications are built using the MicroPython language.
This is a version of the Python programming language, but optimized in its
resource and memory usage so it is able to run on microcontrollers like the
ESP32 used by the Ventilastation fan blade.

## Part I: setup and overview

### Requirements: VSDK

To develop for Ventilastation you first need the SDK and the emulator
running: follow the [setup steps for your OS](README.md#the-path). Part of
that installation is cloning the
[VSDK repository](https://github.com/ventilastation/vsdk) (the
Ventilastation Development Kit).

### One folder per game

Every game lives in its own folder, `games/<group>/<name>/` — the group is
usually your name or the game jam it was made at:

* `code/` — the game's Python code; the entry file is `code/<name>.py`
  and must define a `main()` function returning the initial `Scene`
* `images/` — PNG graphics plus the `__images__.yaml` that describes them
* `sounds/` — music and sound effects (MP3)
* `menu.png` — the icon shown in the console menu (64×30 pixels)
* `meta.json` — menu placement (see Part V)

Other folders you'll bump into: `system/` holds the launcher and other
built-in apps, `apps/micropython/ventilastation/` is the SDK runtime, and
`apps/micropython/roms/` is where your PNGs get compiled to ROM files when
the emulator starts.

### Running

`./vs-emu.sh` (or `vs-emu.bat`) regenerates ROMs and starts the desktop
emulator. Arrow keys move the joystick; SPACE is button A; a USB gamepad
works too.

## Part II: How to clone the simplest game

Let's start by cloning a very simple game, `ventap`, as a new game called
`mygame` in your own group folder:

```sh
mkdir -p games/myname/mygame/code
cp games/alecu/ventap/code/ventap.py games/myname/mygame/code/mygame.py
cp -r games/alecu/ventap/images games/myname/mygame/images
cp games/alecu/ventap/menu.png games/myname/mygame/menu.png
```

In `mygame.py`, rename the class called `Ventap` to `MyGame`, including its
use in `super` calls and in the `main()` function at the bottom.

Ventilastation cannot directly open PNG images: the definition file
`images/__images__.yaml` describes how they become sprite strips. The one
you copied looks like this:

```yaml
palettegroups:
  palette1:
    - strip: bola.png
      frames: 12
    - strip: target.png
      frames: 5
    - fullscreen: fondo.png
```

A `strip` is a horizontal filmstrip of equally-sized animation frames; a
`fullscreen` image is projected onto the whole circular display. Whenever
you run the emulator, changed PNGs are recompiled into
`apps/micropython/roms/<group>.<name>.rom` — for us,
`myname.mygame.rom`. Point your game at it by changing the class attribute:

```python
class MyGame(Scene):
    stripes_rom = "myname.mygame"
```

Finally, create `games/myname/mygame/meta.json` so the launcher places it
in the menu (an empty `{}` works too — the game then appears at the end):

```json
{ "order": 15 }
```

That's it: run `./vs-emu.sh` and your game is on the menu. There is no
launcher code or menu asset list to edit — the launcher discovers game
folders and the menu ROM automatically includes every game's `menu.png`.

## Part III: Scenes and the director

Games and applications created for Ventilastation are composed of one or
more `Scene`s. These are a logical grouping of `Sprite`s (defined in the
next section).

Scenes are managed with a singleton called the `director`, which handles
the stack of scenes via its `push(scene)` and `pop()` methods.

A scene can define an `on_enter()` method that gets called whenever the
scene is shown, and an `on_exit()` method that is called when the scene is
popped. Make sure to call `super()` when you define these methods, e.g.
`super().on_enter()`.

After the scene is shown, the `director` will start calling your `step()`
method every 30 milliseconds. Your game logic usually goes in this method.

If you need some action to happen later in the future, `Scene` provides
`call_later(delay, callable)`. The `delay` is in milliseconds, and
`callable` is any function or bound method. If the scene is finished via
`director.pop()`, all its pending calls are automatically discarded.

⚠️ **WARNING**: create all `Sprite`s and other objects in your scene's
`on_enter()` and reuse them as much as possible. Do not create and release
objects in `step()`: for performance reasons, garbage collection only
happens when entering or exiting scenes.

### Input

- `JOY_LEFT`, `JOY_RIGHT`, `JOY_UP`, `JOY_DOWN`, `BUTTON_A`, `BUTTON_B`,
  `BUTTON_C`, `BUTTON_D` — joystick constants
- `is_pressed(button)` — True while the button or direction is held
- `was_pressed(button)` — True only on the step where it went down
- `was_released(button)` — True only on the step where it went up
- `director.timedout` — True after 30 seconds without any input; use it to
  return to attract screens (`director.reset_timeout()` restarts the
  clock)

### Sound and music

Tracks are named `<group>.<game>/<filename>` after the MP3s in each game's
`sounds/` folder — you can also play another game's sounds, which is why
you'll see `alecu.vyruss/shoot1` all over the place.

- `sound_play(track)` — play a one-shot sound effect
- `music_play(track, loop=False)` — start a music track; with `loop=True`
  it repeats until stopped or replaced
- `music_off()` — stop the current music track

By default music stops when a scene is popped; set `keep_music = True` on
the scene class to let it continue.

## Part IV: Ventilastation display and Sprites

New games should use the newer [vs2 API](vs2-api-guide.md). This section
documents the original `ventilastation.sprites` API because existing games and
older tutorials still use it. The original API remains supported for now, but
it is legacy and will be deprecated after `vs2` reaches renderer parity.

The radial display of Ventilastation means that its pixels are not square
but tiny arcs — we call them "arxels". There are 54 LEDs from the center
out, and 256 angular steps where LEDs can change colors. All of this is
handled by optimized C code (or the emulators), so you don't need to worry
about it.

As a game developer you handle graphics through the `Sprite` class. Up to
100 sprites can be shown and animated at once.

Within a scene, sprites created **first** are drawn **on top of** sprites
created later, so the order in which you create them matters.

```python
from ventilastation.sprites import Sprite
```

Do not import `ventilastation.sprites` and `vs2` from the same game. A game can
declare its intended API in `meta.json` with `{ "api": "vs2" }`.

Each `Sprite` has the following methods:

- position: `set_x(int)`, `x()`, `set_y(int)`, `y()`
- image: `set_strip(strip_number)` — look the number up by name with
  `stripes["bola.png"]` (`from ventilastation.director import stripes`)
- animation frame: `set_frame(int)`, `frame()`
- hide: `disable()`; call `set_frame()` again to show it
- perspective mode: `set_perspective(int)`, `perspective()`
- size: `width()`, `height()`
- collisions: `collision([sprites])` — returns the first colliding sprite
  from the list, or `None`

There are three "perspective modes":

### Mode 0: fullscreen images

Declared as `fullscreen:` in `__images__.yaml`. These are always centered;
Y scales them down from full size and X rotates them. Ventap's planet is a
mode 0 sprite. Start from a 320×320 PNG with few colors (16–32
recommended) and hard on/off transparency — there is no alpha blending on
this display. See Vyruss's Saturn for a transparent example.

### Mode 1: perspective sprites

The most common mode: a "tunnel" perspective where objects use fewer LEDs
as they approach the center, giving a scaling effect.

X is the angle: 0 at the bottom, 64 left, 128 top, 192 right, wrapping at
256. Y is the depth: 0 just outside the display, ~16 fully visible at the
edge, up to 255 at the center.

The `tutorial` system app lets you move sprites of every mode around
interactively — the fastest way to internalize these coordinates.

### Mode 2: non-perspective sprites

For images that shouldn't scale, like scoreboards or the Game Over sign.
X is the same angle as mode 1; Y runs from 0 at the outermost LED to
`54 - sprite height` at the innermost.

## Part V: the menu and meta.json

The launcher builds the console menu by scanning `games/*/*/` folders.
Each game's `meta.json` controls how it appears:

```json
{
  "order": 80,
  "menu_frames": 2
}
```

| Field | Meaning |
|---|---|
| `order` | menu position, ascending; omit to appear at the end |
| `hidden` | `true` keeps the game installed but off the menu |
| `menu_frames` | frame count when `menu.png` is an animated strip (default 1) |
| `menu_frame` | frame shown while idle in the menu (default 0) |

`menu.png` should be 64×30 pixels (times `menu_frames` if animated). It is
compiled into the menu ROM automatically.

## Part VI: Submit your game to the Ventilastation project

Submit your game as a GitHub pull request:

- [Fork a repository](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo)
- [Creating a pull request from a fork](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request-from-a-fork)

Keep everything for your game inside its `games/<group>/<name>/` folder —
if you find yourself needing to touch the SDK or launcher, open an issue
instead (or read [internals/](internals/README.md) and send that as its
own PR).
