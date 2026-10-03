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
vs2.audio.sound("boom")
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

Trench Run needs a few finishing touches: a way to lose, enemies that arrive on
a timer, screens before and after the game, and a best score that is kept.

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

Timers die with the scene, so when the game ends nothing is left spawning. If the
pool is full, `spawn()` returns `None` and this skips that enemy, which is all the
handling it needs.

**Game over, with a sound.** Copy `boom.mp3` from
`games/demos/tutorial_game/sounds/` into your game's `sounds/` folder. When an
enemy touches the ship, play it and switch to a new scene, handing the score over
through its constructor. {py:meth}`~vs2.Sprite.overlaps` tests two sprites, and
`move_enemies()` is already looping over every live enemy, so it can make the
check and report a hit by returning `True`:

```python
def update(self):
    # ... as before, up to the enemies ...
    if self.move_enemies():
        vs2.audio.sound("boom")
        return self.switch(GameOver(self.score))

def move_enemies(self):
    """Advance the enemies. Returns True if one touched the ship."""
    for enemy in self.enemies:
        enemy.y -= ENEMY_SPEED
        enemy.frame = (self.ticks // 6) % enemy.image.frames
        if enemy.overlaps(self.ship):
            return True
        if enemy.y < -enemy.image.height:
            self.enemies.despawn(enemy)      # flew past the ship
            self.score += POINTS
            self.show_score()
    return False
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
        centred_label(hud, "TRENCH RUN", y=1)
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
        score = hud.label("numerals.png", columns=5, x=246, y=11)
        score.set_number(self.score, width=5, pad="0")
        centred_label(hud, "PRESS A", y=20)

    def update(self):
        if joy1.just_pressed(A):
            self.switch(Game())


def main():
    return Title()
```

`__init__` runs once, so `GameOver` keeps the score it was given, while
`build()` creates its drawables. `main()` now returns the title, so the game
starts there. The title and game-over screens are labels at the bottom of the
disc, all at low Y, near the rim, where text is crisp; text placed near the centre
gets squeezed, as chapter 7 shows.

**Getting busier.** The game never changes pace, so a good player can last
indefinitely. Make the interval between enemies shrink as the score rises, by
asking a method for the delay instead of using the constant:

```python
MIN_SPAWN_MS = 650   # the shortest the interval gets

def spawn_delay(self):
    """One millisecond less for every point, down to MIN_SPAWN_MS."""
    return max(MIN_SPAWN_MS, SPAWN_MS - self.score)

def spawn_enemy(self):
    self.enemies.spawn(x=randrange(vs2.display.width), y=ENEMY_START)
    self.call_later(self.spawn_delay(), self.spawn_enemy)
```

Use `self.spawn_delay()` in `build()` too, for the first call. A timer can be
re-armed with any delay, so this is all it takes to change the pace while the
game runs. The floor is 650 ms because that is as fast as the pool can keep up: an
enemy takes about ten seconds to come down, and 16 of them in ten seconds is one
every 650 ms. Spawn faster and `spawn()` would only return `None` more often.
Past that point the pool is the ceiling on how hard the game gets.

**Remembering the best score.** `vs2.saves` keeps named values between
runs, in a small file for your game. Load the record when a screen is built, show
it, and save it only when it is beaten: flash writes are slow, so never save every
tick. `GameOver` does it once, when the game ends, and says so when the record
falls; the title shows what is saved:

```python
BEST = "best"        # the name the best score is saved under


class Title(vs2.Scene):
    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "TRENCH RUN", y=1)
        best = vs2.saves.load(BEST, 0)               # 0 until something is saved
        if best:
            centred_label(hud, "BEST %05d" % best, y=11)
        centred_label(hud, "PRESS A", y=20)

    # ... update() as before ...


class GameOver(vs2.Scene):
    def __init__(self, score):
        vs2.Scene.__init__(self)
        self.score = score
        self.best = vs2.saves.load(BEST, 0)
        self.new_best = score > self.best
        if self.new_best:
            self.best = score
            vs2.saves.save(BEST, score)

    def build(self):
        hud = self.layer("hud", projection=vs2.HUD)
        centred_label(hud, "NEW BEST!" if self.new_best else "GAME OVER", y=1)
        score = hud.label("numerals.png", columns=5, x=246, y=11)
        score.set_number(self.score, width=5, pad="0")
        centred_label(hud, "PRESS A", y=20)

    # ... update() as before ...
```

Try it: play, lose, quit the emulator and run it again, and the title shows the
score you left.

```{figure} ../images/game-title.png
:alt: The title screen: TRENCH RUN in coloured letters, with PRESS A below it, on the bottom of the disc
:width: 60%
:align: center

The title screen, before any score has been saved.
```

```{figure} ../images/game-over.png
:alt: The game-over screen: GAME OVER along the rim, the score 00130 above it, and PRESS A nearer the centre
:width: 60%
:align: center

The game-over screen, here after 13 enemies dodged (130 points) short of a saved
best of 250. Beating it would replace GAME OVER with NEW BEST!.
```

## The whole game

This is the finished file, exactly as it is in
`games/demos/tutorial_game/code/tutorial_game.py`. The complete file at the end
of each earlier chapter is in `docs/vs2/tutorial/steps/`, so you can compare
yours with a working one at every stage.

```{literalinclude} ../../../games/demos/tutorial_game/code/tutorial_game.py
:language: python
```

Next: [budgets and real hardware](budgets.md).
