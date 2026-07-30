# 6. Scenes, input and sound

## Input

Two controllers, ten buttons, three methods:

```python
from vs2.controls import *

if joy1.held(LEFT):            ...   # level: down right now
if joy1.just_pressed(A):       ...   # edge: went down this tick
if joy1.just_released(B):      ...   # edge: came up this tick
if joy2.just_pressed(START):   ...
```

`held` is a level and `just_*` are edges — true for exactly one tick. Movement
usually wants levels; fire, confirm and menu-stepping want edges. All are plain
bitfield tests, so calling them several times per tick is free.

Buttons are `LEFT` `RIGHT` `UP` `DOWN`, `A` `B` `X` `Y`, `START` and `BACK`.
`from vs2.controls import *` imports exactly those plus `joy1` and `joy2` —
`__all__` is explicit, so the star import is well defined.

## Sound

```python
vs2.audio.sound("shoot")
vs2.audio.music("theme", loop=True)
vs2.audio.stop_music()
```

Names resolve against your game's `sounds/` folder. A name with a `/` is already
qualified, which is how you borrow: `vs2.audio.sound("alecu.vyruss/shoot1")`.

Music follows the **app**, not the scene: a track keeps playing across scene
changes inside your game and stops when the game returns to the launcher. If you
want it to stop sooner, say so with `stop_music()`.

## Moving between scenes

A game is usually several scenes — a title, the game, a game-over:

```python
self.push(PauseMenu())        # suspend this scene, run another on top
self.pop()                    # resume the scene below, or exit the game
self.switch(GameOver(score))  # replace this scene outright
```

All three return `None`, so `return self.pop()` reads as "handle this input,
then stop". No VS2 scene raises `StopIteration`.

Transitions are **queued and committed at the end of the tick**. Once one is
queued no further game callbacks run that tick, so a timer coming due on the
same tick as a game-over can never poke a scene that has already decided to
leave. Queue two in one tick and you get an error naming the scene.

State that should survive a scene being re-entered goes in `__init__`, which
runs once. Drawables must be rebuilt in `build()`, which runs on every entry:

```python
class Game(vs2.Scene):
    def __init__(self):
        vs2.Scene.__init__(self)
        self.score = 0          # survives; not a drawable

    def build(self):
        self.hud = self.layer("hud", projection=vs2.HUD)
        self.label = self.hud.label("digits.png", columns=5)   # rebuilt
```

## Timers

```python
self.call_later(1500, self.respawn)
self.call_later(500, self.spawn_wave, wave, boss=True)
```

Extra arguments are stored with the timer and passed to the callback.

Timers live only as long as the scene is showing: pending callbacks are
discarded the moment it is popped or suspended under a `push`, and a scene shown
again starts from a fresh `build()` with no timers. That is deliberate — timers
touch drawables, and the drawables are gone.

Scheduling is meant to be occasional: menus, respawn delays, wave timers. Do not
call it every tick.

## Leaving without writing any code

Two behaviours every game used to hand-roll are now defaults:

```python
class MyGame(vs2.Scene):
    idle_timeout = 30      # seconds without input; None disables
    back_button = True     # Y or BACK pops the scene
```

**The back button.** `Y` or `BACK` pops the scene. A game that wants those
buttons for play sets `back_button = False` and stays exitable through the idle
timeout and the console's home command.

**The idle timeout.** After `idle_timeout` seconds with no input from *either*
controller, {py:meth}`~vs2.Scene.on_idle` fires. Its default pops the scene, so
an unattended machine walks back out to the attract loop on its own. Override it
for something better:

```python
def on_idle(self):
    self.push(AttractSlideshow())
```

For anything more exotic, `vs2.controls.idle_ms` is readable directly.

## Scene-scoped effects

```python
class MyGame(vs2.Scene):
    starfield = True       # applied on entry, restored on exit
```

Next: [budgets and real hardware](budgets.md).
