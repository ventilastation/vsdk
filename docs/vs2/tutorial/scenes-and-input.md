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

`held` is a {term}`level` and `just_*` are {term}`edges <edge>` — true for
exactly one {term}`tick`. Movement usually wants levels; fire, confirm and
menu-stepping want edges. Calling them several times per tick is free.

Buttons are `LEFT` `RIGHT` `UP` `DOWN`, `A` `B` `X` `Y`, `START` and `BACK`.
`from vs2.controls import *` imports exactly those plus `joy1` and `joy2`.

## Sound

```python
vs2.audio.sound("shoot")
vs2.audio.music("theme", loop=True)
vs2.audio.stop_music()
```

Names resolve against your game's `sounds/` folder. A name with a `/` is already
qualified, which is how you borrow: `vs2.audio.sound("alecu.vyruss/shoot1")`.

Music keeps playing across scene changes inside your game and stops when the
game returns to the launcher. To stop it sooner, call `stop_music()`.

## Moving between scenes

A game is usually several {term}`scenes <scene>` — a title, the game, a
game-over. These calls are {term}`transitions <transition>`:

```python
self.push(PauseMenu())        # suspend this scene, run another on top
self.pop()                    # resume the scene below, or exit the game
self.switch(GameOver(score))  # replace this scene outright
```

All three return `None`, so `return self.pop()` reads as "handle this input,
then stop".

A transition is queued and takes effect at the end of the tick, and queueing
two in one tick raises an error. The details are in the
[scene reference](../reference/scene.md#transitions).

State that should survive a scene being re-entered goes in `__init__`, which
runs once. Drawables must be created in `build()`, which runs on every entry:

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

A {term}`timer` runs a function after a delay, in milliseconds:

```python
self.call_later(1500, self.respawn)
self.call_later(500, self.spawn_wave, wave, boss=True)
```

Extra arguments are stored with the timer and passed to the callback.

Pending timers are discarded when the scene is popped or suspended under a
`push`, because the drawables they would touch are gone. Use timers for
occasional events — menus, respawn delays, wave timers — not every tick.

## Back button and idle timeout

Every scene handles both by default. Set these class attributes to change
that:

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

Next: [budgets and real hardware](budgets.md).
