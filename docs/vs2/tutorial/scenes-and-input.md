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
        self.label = self.hud.label("numerals.png", columns=5)   # rebuilt
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

## In the game

Tunnel Shooter needs three finishing touches: sound, enemies that arrive on a
timer, and screens before and after the game.

**Sound.** Copy `shoot.mp3` and `boom.mp3` from
`games/demos/tutorial_game/sounds/` into your game's `sounds/` folder, then play
them by name:

```python
def fire(self):
    # Centre the 6-column shot on the 18-column ship.
    shot = self.shots.spawn(x=self.ship.x + 6, y=self.ship.y + 4)
    if shot is not None:
        vs2.audio.sound("shoot")      # only when a shot was really fired
```

and `vs2.audio.sound("boom")` after the score changes in `move_shots()`.

**A timer for the enemies.** Replace the five enemies from chapter 4 with one
that re-arms itself. Start it at the end of `build()`:

```python
from urandom import randrange

SPAWN_MS = 900       # time between enemies

def build(self):
    # ... everything from before, without the `for i in range(5)` loop ...
    self.call_later(SPAWN_MS, self.spawn_enemy)

def spawn_enemy(self):
    self.enemies.spawn(x=randrange(vs2.display.width), y=ENEMY_START)
    self.call_later(SPAWN_MS, self.spawn_enemy)
```

Timers die with the scene, so when the game ends nothing is left spawning.

**Game over.** `move_enemies()` has been returning `True` when an enemy touches
the ship. Use it to switch to a new scene, handing the score over through its
constructor:

```python
def update(self):
    # ... as before, up to the shots ...
    self.move_shots()
    if self.move_enemies():
        return self.switch(GameOver(self.score))
    self.animate_booms()
```

**A title and a game-over screen.** Both are small scenes. The text is a
{term}`label` using `steel8x8.png`, a full CP437 font, so it can write any
letter. The helper centres a label on the bottom of the disc, where text reads
upright, so it needs no flips:

```python
def centred_label(layer, text, y):
    """A label for ``text``, centred on the bottom of the disc, where it reads
    upright. steel8x8.png is a full CP437 font, 8 columns per character."""
    label = layer.label("steel8x8.png", columns=len(text), x=0, y=y, text=text)
    label.x = -(len(text) * label.image.width) // 2
    return label


class Title(vs2.Scene):
    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "TUNNEL SHOOTER", y=1)
        centred_label(hud, "PRESS A", y=20)

    def update(self):
        if joy1.just_pressed(A):
            self.switch(Game())


class GameOver(vs2.Scene):
    def __init__(self, score):
        vs2.Scene.__init__(self)
        self.score = score

    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "GAME OVER", y=1)
        score = hud.label("numerals.png", columns=5, x=246, y=20)
        score.set_number(self.score, width=5, pad="0")
        centred_label(hud, "PRESS A", y=28)

    def update(self):
        if joy1.just_pressed(A):
            self.switch(Game())


def main():
    return Title()
```

`__init__` runs once, so `GameOver` keeps the score it was given, while
`build()` creates its drawables. `main()` now returns the title, so the game
starts there:

```{figure} ../images/game-title.png
:alt: The title screen: TUNNEL SHOOTER in coloured letters, with PRESS A below it, on the bottom of the disc
:width: 60%
:align: center

The title screen. Both lines are labels at the bottom of the disc.
```

and the game-over screen, with the score handed over by the scene that ended
the game:

```{figure} ../images/game-over.png
:alt: The game-over screen: GAME OVER in coloured letters along the rim, a score of 00130 above it, and PRESS A nearer the centre
:width: 60%
:align: center

The game-over screen, here after 13 kills (130 points).
```

All the text sits at low Y, near the rim, where it is crisp. Text placed near the
centre gets squeezed, as chapter 7 shows.

Next: [budgets and real hardware](budgets.md).
