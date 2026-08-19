# VS2 Behaviors, Actions and the Scene Editor

Status: draft for review
Baseline: `vs2` revision 2 as shipped (`apps/micropython/vs2/__init__.py`)
Prior art: Construct 3; `docs/vs2-api-rework-proposal.md`

This proposes three layers on top of revision 2, plus the editor that owns
them.

- **Actions** — small, parameterised, allocation-free operations on a sprite.
  `MoveTo`, `Animate`, `Collide`, `Spawn`, `PlaySound`. An Action never
  decides. The Action catalog is also the **Blockly palette**.
- **Behaviors** — named, parameterised per-sprite state machines written in
  the vocabulary of Actions. `Moving`, `Damageable`, `Pilotable`,
  `PathFollowing`. A Behavior never touches the renderer directly. Simple ones
  ship built in; composed ones ship as **block programs the author can fork**.
- **Instance variables and families** — game-owned per-instance data declared
  on a pool, and groups of pools addressed as one. Both are Construct
  primitives that every game in the tree currently fakes.

And above all three: **the editor owns `build()`**. Scene structure — layers,
pools, tilemaps, instance variables, behavior attachments and their parameters
— is authored in the editor and emitted as generated MicroPython. The game
keeps `update()` and its callbacks.

## Why this exists

Revision 2 gave games a sealed display graph, pools, labels and tilemaps. It
did not give them anywhere to put *conduct*, and it gave the editor nothing to
edit. So every game writes conduct again, at the lowest possible level, in
Python only.

Two shipping VS2 games and eight V1 jam games were read for this proposal. The
duplication is not in the arithmetic, it is in whole concepts:

| The concept every game re-implements | Where |
|---|---|
| Constant velocity, then leave the play field | `vixeous.py:314-331`, `vyruss_vs2.py:414-431`, `dome_defander/misil.py:31-38` |
| Show, animate once, disappear | `vixeous.py:344-350`, `vyruss_vs2.py:432-437`, `dome_defander/misil.py:77-86` |
| Per-instance data bolted on at spawn | `vixeous.py:216-220` (`theta`, `kind`, `phase`, `hp`), `vyruss_vs2.py:206-210` (`base_frame`, `frame_clock`, `dead`, `finished`, `movements`) |
| A thing the player flies | `vyruss_vs2.py:34-44` + `:331-348`, `vixeous.py:257-289` |
| A thing that takes damage, flashes, dies with a score and a sound | `vyruss_vs2.py:360-403`, `vixeous.py:220` + `:352-360` + `:396-403` + `:456-461` |
| A projectile that travels, expires, and hurts what it touches | `vixeous.py:314-323` + `:390-434`, `vyruss_vs2.py:414-431` |
| A scripted path, then join a formation | `vyruss_vs2.py:72-115` + `:209-220` |
| Sweep back and forth while animating | `vixeous.py:324-332`, `:333-343` |
| The same test run against three different pools | `vixeous.py:390-414` — shots vs boss, then vs enemies, then bombs vs targets |

`vyruss_vs2.py` is the clearest case: it already invented Actions and stopped
one level short. `TravelTo`/`TravelX`/`TravelCloser`/`TravelAway` (`:72-115`)
each have `step(sprite)`, `finished(sprite)` and instance parameters, and every
baddie carries an ordered list of them (`:209-220`). That list *is* a
`PathFollowing` behavior, hand-assembled per sprite, scoped to one game, with
no way to edit its numbers except editing Python and restarting.

## Design goals, in priority order

1. **A Behavior is the unit a designer thinks in.** "Pilotable by joystick 2",
   "takes three hits", "chases the player". If the panel's top level reads
   like a physics library, the layer is at the wrong altitude.
2. **Nothing that runs on the board may cost more than the code it
   replaces.** Games tick every 30 ms (`director.py:680`) on an ESP32 running
   MicroPython. The measured budget below decides the dispatch shape, and it
   decides the shape of the block program too.
3. **Nothing in the tick allocates.** The sealed-scene rule extends unchanged:
   parameters, per-instance state, instance variables, families and every
   cross-pool reference resolve during `build()`; the tick writes only fields
   that already exist.
4. **One declaration, four consumers.** A parameter is declared once, with
   type, range, label and unit. The runtime, the reference docs, the property
   panel and the Blockly field all read that declaration. A separate schema
   that can drift is not acceptable.
5. **Nothing on the board knows the editor exists.** The editor emits
   MicroPython. The console runs ordinary code, compiled by mpy-cross,
   packaged in an ordinary `.vs2`. No graph interpreter, no runtime loader, no
   editor-only code path to keep working.
6. **The standard behaviors are forkable.** Composed behaviors ship as block
   programs, not black boxes. If the catalog needs something the palette
   cannot express, the palette is wrong.
7. **The catalog is grounded in the tree.** Every entry replaces something at
   least two games in `games/` write by hand.

## The three lines

Short enough to enforce in review:

> **An Action never decides. A Behavior never draws. The editor owns
> structure; the game owns consequences.**

An Action, given parameters and a sprite, does exactly one thing — no
conditions, no state machine, no callbacks that change its course. Pure enough
to unit-test in isolation, small enough to be one Blockly block.

A Behavior reads input, timers, its own state and the world, then picks which
Actions run. It writes only its declared state; everything reaching the
renderer goes through an Action.

The editor decides what exists — layers, pools, counts, variables,
attachments, parameters. The game decides what happens when something occurs —
`update()`, and the callbacks behaviors fire.

### A naming rule that makes the layers legible

**Actions are verbs. Behaviors are adjectives or role-nouns.**

`Move` / `Moving`. `Animate` / `Animated`. `Steer` / `Pilotable`. `Spawn` /
`Spawner`. `Collide` / `Damageable`. In the palette you are picking verbs; in
the property panel you are describing what a thing *is*. It costs nothing and
it makes a screenshot self-explanatory.

## Ownership: who writes which file

The generated/hand split runs along file boundaries, never inside a file.
Mixed-ownership files are the round-trip trap and this design does not have
any.

```
games/alecu/vixeous/
  meta.json
  code/
    vixeous_scene.py     GENERATED. Layers, pools, vars, behaviors, params.
                         Carries the editor workspace as a trailing blob.
    vixeous.py           YOURS. update(), callbacks, game state.
    behaviors/
      chasing.py         GENERATED from blocks. One file per custom behavior.
  images/  sounds/  menu.png
```

```python
# vixeous_scene.py  -- generated, do not edit
# Ventilastation scene editor. Edit in the editor, or Detach to take
# ownership of this file. body-sha: 8f3a1c02
import vs2
from vs2.behaviors import Damageable, Moving, Patrolling, Projectile, Transient


class VixeousScene(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)

        self.explosions = self.world.sprite_pool(
            "explosion.png", 5, on_empty=vs2.RECYCLE)
        self.explosions.behave(Transient(animate=True, ticks=3, sound="boom"))

        self.enemies = self.world.sprite_pool("enemy.png", 6)
        self.enemies.var("kind", 0, min=0, max=2)
        self.enemies.behave(Moving(speed_y=-1))
        self.enemies.behave(Patrolling(axis="x", amplitude=2, period=128))
        self.enemies.behave(Animated(first=0, last=1, ticks=8))
        self.enemies.behave(Damageable(hp=1, explosion=self.explosions,
                                       score=40, on_death=self.enemy_died))

        self.boss = self.world.sprite("boss.png", visible=False)
        self.boss.behave(Damageable(hp=18, explosion=self.explosions,
                                    score=500, on_death=self.area_clear))

        self.hostiles = self.family(self.enemies, self.boss)

        self.shots = self.world.sprite_pool("shots.png", 4)
        self.shots.behave(Projectile(speed_y=8, range=179,
                                     hits=self.hostiles,
                                     burst=self.explosions, sound="hit"))
        self.on_build()

    def on_build(self):
        """Hook for the game subclass. Generated empty."""

# blocks: eJyNVMtu2zAQ/BWCpxaQ...
```

```python
# vixeous.py  -- yours
from .vixeous_scene import VixeousScene


class Vixeous(VixeousScene):
    def update(self):
        ...

    def enemy_died(self, sprite):
        self.score += 40
```

The generated file is 100% generated; yours is 100% yours. `on_build()` is
the seam: post-construction work that needs the graph goes there without
touching generated code. When the editor wires `on_death=self.enemy_died` and
no such method exists, it offers to create a stub in your file — on creation
only, never on regeneration.

**No runtime change is needed for any of this.** `build()` stays exactly the
hook it is today; the editor simply generates into it. That is deliberate: a
game hand-written against revision 2 keeps working, and a generated game is
indistinguishable from a hand-written one at runtime.

## Actions

```python
from vs2.actions import Action
from vs2.params import Angle, Number

class Move(Action):
    """Constant velocity, with optional acceleration."""

    speed_x = Angle(0, min=-32, max=32, step=0.25,
                    label="Angular speed", unit="col/tick")
    speed_y = Number(0, min=-32, max=32, step=0.25,
                     label="Radial speed", unit="led/tick")

    def run(self, sprites):
        """Apply to every sprite. Hoist parameter reads here."""
        dx, dy = self.speed_x, self.speed_y
        for sprite in sprites:
            sprite.x += dx
            sprite.y += dy

    def run_one(self, sprite):
        """Apply to one sprite, for a Behavior that branches per sprite."""
        sprite.x += self.speed_x
        sprite.y += self.speed_y
```

Two call forms, because Behaviors need both and they cost differently
(measured below). The base class defines `run()` as a loop over `run_one()`,
so an Action overrides `run()` only when hoisting saves something.

**Results.** `run_one()` returns `None` when nothing notable happened,
`vs2.DONE` when a durative Action finished (`MoveTo` arrived, `Animate`
completed a `once` cycle, `Wait` elapsed), or an object when it found one
(`Collide` returns the sprite hit, `Spawn` returns the new sprite or `None`).
All three are existing objects; nothing allocates.

### The vocabulary — which is the block palette

| Action | Result | Replaces |
|---|---|---|
| `Move(speed_x, speed_y, accel_x, accel_y)` | — | `vixeous.py:315-323`, `vyruss_vs2.py:415` |
| `MoveTo(x, y, speed_x, speed_y)` | `DONE` on arrival | `vyruss_vs2.py:47-83` — 37 lines of shortest-arc arithmetic |
| `Steer(heading, speed, turn_rate)` | — | `vyruss_vs2.py:53-62` |
| `Oscillate(axis, amplitude, period, wave)` | — | `vixeous.py:325-326`, `:334-338` |
| `Animate(first, last, ticks, mode)` | `DONE` at cycle end | every game in the tree |
| `SetFrame(frame)` / `Flip(x, y)` | — | |
| `Blink(on_ticks, off_ticks)` | — | `vixeous.py:456-461` |
| `Spawn(pool, offset_x, offset_y, frame)` | new sprite or `None` | `dome_defander/misil.py:49-56`, `vyruss_vs2.py:322-329` |
| `Despawn()` / `Show()` / `Hide()` | — | |
| `Collide(targets)` | sprite hit or `None` | `vixeous.py:405-414`, `vyruss_vs2.py:419-427` |
| `TileUnder(tilemap)` | tile index or `None` | `mapdemo.py:52-58`, `vixeous.py:77-101` |
| `PlaySound(name)` | — | `vixeous.py:197`, `:298`, `:303`, `:358` |
| `Wait(ticks)` | `DONE` when elapsed | `vyruss_vs2.py:258-261` |

`TileUnder` needs a new public method first — there is no way to ask a tilemap
what is under a point today, which is why `mapdemo` hand-rolls it and
`vixeous` sidesteps it by re-deriving terrain from the generator function
instead of reading the map:

```python
Tilemap.cell_at(x, y)    # -> (column, row) or None
```

The mapping accounts for the map's `x`/`y`, its `view_x`/`view_y`, the tile
size and the circular X wrap — the same single-place-for-the-inversion rule
`Label` already owns for reversed cell order.

## Behaviors

```python
class Projectile(Behavior):
    """Travels, expires at its range, and damages the first thing it hits."""

    speed_x = Angle(0, min=-32, max=32, step=0.25)
    speed_y = Number(8, min=-32, max=32, step=0.25)
    range   = Number(180, min=1, max=255, step=1, unit="led")
    damage  = Number(1, min=0, max=99, step=1)
    hits    = PoolRef(None, label="Hits what")
    burst   = PoolRef(None, label="Explosion pool")
    sound   = Sound(None, label="Impact sound")

    state = ("shot_flown",)

    def attached(self, subject):
        self.move = self.action(Move(speed_x=self.speed_x,
                                     speed_y=self.speed_y))
        self.hit  = self.action(Collide(self.hits))
        self.boom = self.action(Spawn(self.burst))
        self.bang = self.action(PlaySound(self.sound))

    def step(self, sprites):
        self.move.run(sprites)                  # uniform: hoisted, column-wise
        limit = self.range
        for sprite in sprites:                  # per-sprite: decisions only
            sprite.shot_flown += self.speed_y
            if sprite.shot_flown > limit:
                sprite.despawn()
                continue
            other = self.hit.run_one(sprite)
            if other is not None:
                self.boom.run_one(sprite)
                self.bang.run_one(sprite)
                hurt(other, self.damage)
                sprite.despawn()
```

Three things there are load-bearing.

**`attached()` is where composition happens.** It runs once, at build time,
and may allocate. `self.action(...)` registers the Action so the panel and the
block editor can find it and so the same object is reused every tick.

**The loop is split deliberately.** Everything uniform is hoisted into
`action.run(sprites)`; the per-sprite loop carries only branching. That shape
is measured below, and the block editor's skeleton makes it structural.

**Cross-behavior wiring resolves at build where it can.** Because Behaviors
attach at the *pool* level — Construct's object-type level — a single target
pool has exactly one `Damageable`, so `attached()` can hold a direct reference
to it. When the target is a family whose members carry different
`Damageable`s, the lookup happens at hit time through the sprite's owning
pool. Hits are rare; the fast path covers the common case and the slow path is
still a dict lookup with no allocation.

### Attaching

`behave()` is a structural call, legal only inside `build()`, returning the
Behavior — the same shape as every other VS2 factory. Behaviors are named,
defaulting to the class name in snake case; a second of the same class on one
subject needs an explicit `name=`. Names are the path the panel, the block
editor and the control protocol address a parameter by
(`enemies.patrolling.amplitude`), so a collision is a build-time error naming
both. Read them back with `subject.behaviors`, `subject.behavior("patrolling")`
or `subject.behavior(Damageable)`.

### Parameters are the schema

Parameter objects are non-data descriptors holding a default plus metadata.
`__init__` walks the declarations once at construction and writes plain
instance attributes, so `self.speed_y` in the tick is an ordinary attribute
read with no descriptor cost. (`dir()` on a class, including inherited
attributes, works on MicroPython 1.25 — verified on the unix port — so no
metaclass is needed.) Validation happens at construction, inside `build()`, so
a bad parameter surfaces the first time the scene is entered:

```text
TypeError: Damageable has no parameter 'health'; valid: hp,
  invulnerable_ticks, blink, explosion, sound, score, on_death
ValueError: Projectile.range must be in 1..255
```

One declaration, four renderings:

| Type | Property panel | Blockly field |
|---|---|---|
| `Number(default, min, max, step, unit)` | slider + entry | number field, clamped |
| `Angle(...)` | dial marked 0 / 64 / 128 / 192 | the same dial, as a custom field |
| `Flag(default)` | checkbox | checkbox field |
| `Choice(default, options)` | dropdown | dropdown field |
| `Frames(default)` | strip of the image's real frames | image-strip field |
| `Sound(default)` | dropdown + preview button | dropdown, populated from `sounds/` |
| `Image(default)` | dropdown over the asset pack | dropdown |
| `PoolRef(default)` | dropdown over pools and families | dropdown, from the live scene |
| `Points(default)` | table + overlay on the LED preview | overlay editor, opened from the block |
| `Callback(default)` | read-only, shows the bound method | dropdown over the game class's methods |

`Angle` earns its own type because X is angular everywhere in VS2 and "the
bottom of the disc" is not a fact anyone recovers from the number `0`. The
asset-backed types are what make both surfaces worth using rather than boxes
of numbers: they populate from the game's own ROM and sound folder, which
`web/rom-builder-core.js` already parses. `PoolRef` and `Callback` populate
from the scene the editor is already holding.

### Per-instance state

A Behavior that needs per-sprite state declares it (`state = ("shot_flown",)`
above). At attach time the framework primes every named field to `0` on
**every** sprite of the subject — the free ones too. That is not tidiness, it
is the whole allocation argument:

```text
first assignment of a name, 40 sprites : 1312 bytes  (~33 bytes each)
overwriting a primed name, 40 sprites  :    0 bytes
```

Priming during `build()` is what makes `sprite.shot_flown += ...` in the tick
allocation-free, and it spends the cost visibly where a pool spends its sprite
budget. State names are flat, so access is a plain attribute read — measured
faster than a parallel array indexed by slot (6.2 ms vs 8.9 ms for 2000 ticks
× 40 sprites), because MicroPython's `range()` plus subscript costs more than
an attribute lookup. Flat names mean collisions are possible, so the primer
rejects them at build: two Behaviors on one subject declaring the same name,
or a name shadowing a `Sprite` property or an instance variable, is a
`StateConflictError` naming both sides.

## Instance variables

Construct's most-copied primitive, and the one thing every VS2 game fakes.
`vixeous` bolts `theta`, `kind`, `phase` and `hp` onto enemies at spawn
(`:216-220`); `vyruss_vs2` bolts on `base_frame`, `frame_clock`, `dead`,
`finished` and `movements` (`:206-208`). Both pay the ~33-bytes-per-name heap
growth at the first spawn rather than at build, and neither surfaces the cost
anywhere.

Declared on the pool, in the editor, with the same parameter types:

```python
self.enemies.var("kind", 0, min=0, max=2)
self.enemies.var("hp", 1, min=0, max=99)
self.enemies.var("angry", False)
```

- Primed on every sprite at build, exactly like behavior state, so writes in
  the tick allocate nothing.
- **Reset to their declared defaults by `spawn()`.** A recycled explosion must
  not inherit the previous one's counter. Today every game writes
  `boom.age = 0` by hand after every spawn (`vyruss_vs2.py:373-374`,
  `vixeous.py:196`, `:206-207`) and the bug when they forget is invisible.
  Behavior state resets the same way.
- Editable in the panel as a table on the pool, which is exactly Construct's
  instance-variable editor.
- Readable from blocks as a value block, writable as a set block.

`spawn()` gaining a reset loop is the only behavioural change to existing API
in this proposal, and it only affects pools that declared variables.

## Families

`vixeous.py:390-434` runs the same test three times: shots against the boss,
shots against enemies, bombs against targets. A family is Construct's answer
and it collapses that to one attachment:

```python
self.hostiles = self.family(self.enemies, self.boss)
self.shots.behave(Projectile(hits=self.hostiles, ...))
```

A `Family` is a build-time object holding an ordered tuple of pools and
sprites. Iterating yields the live sprites of every member, in member order.
It can be the target of `Collide` and `PoolRef`, and a Behavior can attach to
the family itself, in which case one Behavior instance with one parameter set
covers every member and state is primed across all of them — Construct's
family-behavior semantics exactly.

Families are build-time only and allocate nothing at runtime.

## The tick

### Ordering

1. `scene.update()` — game code, unchanged.
2. the Behavior pass, in attach order across the whole scene.
3. back button, idle timeout, timers, transition commit — unchanged.

Behaviors run **after** `update()`, the opposite of Construct 3, deliberately:
a scene with no Behaviors ticks exactly as today; a sprite spawned in
`update()` moves and is range-checked on the same tick, and at 33 Hz a
one-tick lag on a bullet is visible; and `update()` stays the place where the
game overrides a parameter, taking effect immediately.

One sentence: *game code decides, then Behaviors carry it out, in the order
they were attached.* `scene.behaviors` lists them in run order, and so does
the panel.

### What the dispatch shape costs

Measured on MicroPython 1.25, unix port, 600 ticks × 60 live sprites:

```text
  Action applied column-wise, action.run(sprites)          23.3 ms   39 us/tick
  Behavior state machine calling action.run_one(sprite)    27.3 ms   45 us/tick
  same state machine, arithmetic inlined, no Actions       19.2 ms   32 us/tick
  hybrid: uniform hoisted + per-sprite loop for decisions  20.4 ms   34 us/tick
```

And for a uniform pool:

```text
  hand-written inline loop (today's style)                 23.4 ms   39 us/tick
  one column-wise pass per Action                          21.2 ms   35 us/tick
  per-sprite dispatch across an action list                38.7 ms   65 us/tick
```

Three rules follow:

1. **Uniform work goes column-wise.** `action.run(sprites)` is *faster* than
   the loop it replaces, because hoisting the parameter read is natural in
   that shape and easy to forget by hand.
2. **The Action indirection costs ~42% when dispatched per sprite** (27.3 vs
   19.2 ms). That is the price of making the mechanics introspectable,
   editable and expressible as blocks, and it is paid only where a Behavior
   genuinely branches.
3. **So a Behavior hoists everything uniform and keeps the per-sprite loop for
   decisions.** That hybrid lands within 7% of fully inlined hand-written code
   with every knob visible. It is the shape `Projectile.step()` is written in,
   the shape the catalog is written in, and — critically — the shape the block
   editor makes structurally unavoidable.

## The catalog

Weighted the way Construct's usage actually distributes: the high-frequency
tier is tiny attribute-like behaviors, not composed state machines. Construct
projects attach `Solid`, `Destroy outside layout`, `Fade`, `Flash` and `Timer`
dozens of times and `Platform` exactly once.

### Attributes — built in, tiny, attached from the panel, never forked

| | Replaces |
|---|---|
| `Transient(animate, ticks, sound, on_end)` | `vixeous.py:344-350`, `vyruss_vs2.py:432-437`, `dome_defander/misil.py:77-86` |
| `Animated(first, last, ticks, mode)` | every game in the tree |
| `DespawnBeyond(y_min, y_max, x_min, x_max)` | `vixeous.py:308-309`, `:327-329`, `vyruss_vs2.py:417-418`, `:430-431` |
| `Lifetime(ticks, on_expire)` | the `age` counters in both games |
| `Blinking(on_ticks, off_ticks, duration, on_end)` | `vixeous.py:456-461` |
| `Pinned(to, offset_x, offset_y)` | `vyruss_vs2.py:384-391` |

These are the ones that get attached forty times a project. All six ship in
the first release; none is more than a few lines.

### Movements — one per subject

| | Replaces |
|---|---|
| `Moving(speed_x, speed_y, accel_x, accel_y)` | `vixeous.py:315-323`, `vyruss_vs2.py:415`, `:429` |
| `Patrolling(axis, amplitude, period, wave, drift_x, drift_y)` | `vixeous.py:324-332`, `:333-343` |
| `PathFollowing(points, relative, speed_x, speed_y, loop, on_finish)` | `vyruss_vs2.py:72-115` + `:209-220` |
| `Pilotable(player, scheme, speed_x, speed_y, bounds, fires, fire_button, fire_sound)` | `vyruss_vs2.py:34-44` + `:331-348`, `vixeous.py:257-289` |
| `Chasing(target, speed_x, speed_y, turn_rate, give_up_range, on_reach)` | nothing — see below |
| `Orbiting(centre_y, speed)` | nothing — see below |

`Moving`, `Patrolling` and `PathFollowing` ship first. The two with no
precedent are worth having for opposite reasons. `Chasing` is absent
*because* doing it by hand needs the shortest-arc arithmetic only
`vyruss_vs2` ever wrote (`:47-69`); two jam games fake it with a straight
line. `Orbiting` is absent because nothing in the tree does it, but circular
motion at a fixed depth is the disc's most natural movement and costs a few
lines — a case of the hardware suggesting a primitive the games have not
reached for yet, which is worth flagging as speculative rather than
evidence-backed. `Pilotable`'s three schemes — `rim`, `turn`, `free` — are
still an open question (below).

### Composed — ship as block programs, meant to be forked

| | Replaces |
|---|---|
| `Projectile(speed_x, speed_y, range, damage, hits, burst, sound)` | the shot/bomb loops and hit tests in both games |
| `Damageable(hp, invulnerable_ticks, blink, explosion, score, sound, on_damage, on_death)` | `vyruss_vs2.py:360-403`, four scattered pieces of `vixeous` |
| `FiringAt(target, projectile, every, jitter, lead, sound, on_fire)` | `vyruss_vs2.py:322-329` |
| `Spawner(pool, every, count, pattern, on_spawn)` | `vixeous.py:209-243`, `vyruss_vs2.py:245-261` |
| `Collectible(score, sound, on_pickup)` | second wave |

`Projectile` and `Damageable` ship first, as the two flagship block programs —
they are the proof that the palette can express what the catalog needs.

`Damageable` exposes `hurt(sprite, amount)` for other behaviors to call. Note
that Construct has no equivalent: it keeps behaviors mechanical and puts game
rules in the event sheet. We can go further because Python *is* our event
sheet, and because a forkable block program is not the black box a compiled
Construct behavior is.

Every Behavior that fires an event takes a `sound=` parameter rather than
there being a sound behavior — every spawn and hit in both games is
immediately followed by `vs2.audio.sound(...)` (`vixeous.py:197`, `:298`,
`:303`, `:358`; `vyruss_vs2.py:319`, `:329`, `:377`, `:397`).

### Second wave

`Avoiding(threats, radius, strength)`; `TileBound(tilemap, solid, on_block,
slide)` with `Tilemap.cell_at()` and the `TileUnder` Action;
`Scrolling(speed_x, speed_y, wrap)` — the first Behavior whose subject is a
`Tilemap`, replacing `vixeous.py:180-181` and `mapdemo.py:57-65`; and
`CameraBound(camera)`, the one genuinely new capability — `vixeous` recomputes
`sprite.x = screen_x(theta, camera_theta, width)` in six places (`:311-312`,
`:320`, `:323`, `:331`, `:341-342`, `:349`) because VS2 has no camera concept,
so every scrolling game reinvents world-versus-screen space.

### Deliberately not in the catalog

- **Gravity and a physics solver.** No game in the tree uses one; the two that
  fake it use a counter, which `Moving(accel_y=...)` covers.
- **Pathfinding and line of sight.** No meaningful nav space on a disc.
- **Fade.** The renderer has no alpha. Palette animation is scene-level.
- **Effects.** Shaderless hardware.
- **Behaviors that create drawables.** A Behavior may spawn from an existing
  pool; it may never grow the display graph.

## Budgets and diagnostics

```text
ResourceLimitError: behavior 33/32 in Vixeous (shots: 1, enemies: 4,
  targets: 2, explosions: 1, boss: 2, player: 3); reduce the behavior budget
```

`vs2.limits.behaviors = 32` per scene, sized against a hand-count of the two
shipping games after migration: `vixeous` about 13, `vyruss_vs2` about 9.

Actions are not capped separately — they are an implementation detail of the
Behavior that owns them, reported per Behavior in the profiling command.
Per-instance state and instance variables are reported, not capped: the cost
is `fields × pool count × ~33 bytes`, which for all of `vixeous` is under 3 kB
and never the thing that runs the board out of memory.

## The block editor

### The palette is the Action catalog

Every Action is one block; its parameters are the block's fields, rendered
from the same declarations the property panel uses. Nothing is written twice,
and a new Action appears in the palette, the panel, the protocol and the
reference docs at once.

Blockly vendors as `web/vendor/blockly`, alongside monaco, piskel and
chipsynth, lazily loaded the way Monaco already is.

### The tick skeleton makes the fast shape unavoidable

A naive generator emits per-sprite dispatch — the 45 µs/tick shape instead of
34. That is not fixed with a style guide nobody reads; it is fixed with the
top-level block structure, which has two fixed zones:

```
when ‹Projectile› ticks
├─ apply to all ▸    [ Move      speed_y (8) ]          → action.run(sprites)
└─ for each sprite ▸ [ if  ‹Collide with (hostiles)› ]  → the per-sprite loop
                     [   do  ‹Spawn (explosions)›   ]
                     [       ‹Play sound ("hit")›   ]
                     [       ‹Despawn›              ]
```

Uniform work physically cannot land inside the per-sprite loop. Generated code
is right by construction, and the author never has to learn the rule.

### Round-trip: one embedded blob and one one-way door

The trap every codegen tool falls into is trying to re-parse hand-edited output
back into its model. This design refuses to.

- **Embed the workspace** as a base64+zlib blob in a trailing comment of the
  generated file. One file, so the source cannot get separated from its
  output; survives copy, `git mv` and packaging with no extra plumbing.
- **Banner and body checksum** at the top. If the body no longer matches, the
  editor reports the file as hand-edited and refuses to overwrite silently.
- **Detach** is the escape hatch: strip the blob, the file becomes ordinary
  Python forever. Explicit, one-way, and it means nobody is ever trapped in
  blocks.

### Debugging generated code

A traceback from the board names generated line numbers, which is useless on
its own. The generator emits block IDs as trailing comments and keeps a line
map beside the workspace blob, so the editor can highlight the offending
block. The director already surfaces scene tracebacks over comms, so there is
somewhere to hook it. This is much harder to retrofit than to build alongside
the generator.

### Generator invariants, enforced by tests

- Every generated file compiles with mpy-cross. Free: `tests/run_tests.py:109-126`
  already sweeps every MicroPython source.
- Generating every standard behavior and running 1000 ticks allocates zero
  bytes. A generator invariant is far stronger than a rule saying "don't emit
  f-strings in `step()`".
- Generated code obeys the MicroPython restrictions in `AGENTS.md` — no
  bytearray slice deletion, and so on.
- Regenerating an unchanged workspace produces a byte-identical file, so the
  editor never creates spurious diffs.

## The live-tune loop

Introspection rides the channel that already exists. The director dispatches
in-band text commands to feature modules — `povcal`, `povperf`, `hallfilter`
(`director.py:193-205`), each exposing `handle_command(parts, send, ...)`.
Behaviors add one more in exactly that shape, and the nesting falls out of the
layers:

```text
> vs2beh list
{"subjects":[
  {"name":"enemies","kind":"pool","count":6,
   "vars":[{"name":"kind","type":"number","value":0,"min":0,"max":2}],
   "behaviors":[
    {"name":"damageable","class":"Damageable","params":[
      {"name":"hp","type":"number","value":1,"min":1,"max":99,"step":1},
      {"name":"score","type":"number","value":40,"min":0,"max":9999},
      {"name":"explosion","type":"pool","value":"explosions"}],
     "actions":[
      {"name":"blink","class":"Blink","params":[
        {"name":"on_ticks","type":"number","value":2,"min":1,"max":60}]}]}]}]}

> vs2beh set enemies.damageable.hp 2
vs2beh_ok enemies.damageable.hp=2

> vs2beh set enemies.damageable.blink.on_ticks 4
vs2beh_ok enemies.damageable.blink.on_ticks=4
```

Which gives a four-step loop:

1. Drag a slider in the panel → `vs2beh set` → the running game changes on the
   next tick, with no restart.
2. The editor marks the value as differing from what is saved.
3. On commit, the editor updates its model and regenerates the scene file.
4. The next full restart runs the committed value.

That transport is why this is worth building: the panel talks to *a running
game*, so the same panel tunes the desktop emulator, the browser, or the
physical spinning console over USB serial — the only place some of these
numbers can honestly be judged, because the disc's legibility and persistence
do not survive a screenshot.

`list` allocates and is called on demand, never per tick. `set` writes one
attribute.

Because the editor owns `build()`, there is no source-patching problem here at
all — the previous revision of this proposal spent three phases on it. Step 3
is plain serialisation of a model the editor already holds.

## Migration examples

```python
# before -- vyruss_vs2.py:72-115 and :209-220
class TravelTo: ...           # 12 lines
class TravelBy: ...           #  8 lines
class TravelX(TravelBy): ...
class TravelCloser(TravelBy): ...
class TravelAway(TravelBy): ...
baddie.movements = [TravelCloser(85), TravelX(112), TravelCloser(34),
                    TravelX(-96), TravelAway(45), TravelTo(final_x, final_y)]

# after -- once, for the whole pool, drawn as a path on the disc preview
self.baddies.behave(PathFollowing(
    points=((0, -85), (112, 0), (0, -34), (-96, 0), (0, 45)),
    relative=True, speed_x=X_SPEED, speed_y=Y_SPEED,
    on_finish=self.join_formation))
```

```python
# before -- vyruss_vs2.py:360-377, one of two places with the same idea
def kill_baddie(self, baddie):
    if baddie.dead: return
    x = baddie.x + baddie.width // 2 - 16
    y = baddie.y + baddie.height // 2 - 16
    baddie.dead = True
    baddie.hide()
    if baddie in self.everyone: self.everyone.remove(baddie)
    if baddie in self.attacking:
        self.attacking.remove(baddie); self.max_attacking += 1
    boom = self.explosions.spawn(x, y)
    if boom is not None: boom.age = 0
    self.score += randrange(10, 19)
    self.update_scoreboard()
    vs2.audio.sound("explosion2")

# after
self.baddies.behave(Damageable(hp=1, explosion=self.explosions,
                               score=15, sound="explosion2",
                               on_death=self.baddie_died))
self.laser.behave(Projectile(speed_y=6, range=LASER_FAR_Y,
                             hits=self.baddies, burst=self.explosions))
```

```python
# before -- vixeous.py:324-332
for enemy in self.enemies:
    enemy.phase = (enemy.phase + 1) % 128
    enemy.theta = (enemy.theta + (2 if enemy.phase < 64 else -2)) % vs2.display.width
    enemy.y -= ENEMY_SPEED
    if enemy.y < 0:
        self.enemies.despawn(enemy)
    else:
        enemy.x = screen_x(enemy.theta, self.camera_theta, enemy.width)
        enemy.frame = enemy.kind * 2 + ((enemy.phase // 8) & 1)

# after -- nothing in update()
self.enemies.behave(Moving(speed_y=-ENEMY_SPEED))
self.enemies.behave(Patrolling(axis="theta", amplitude=2, period=128))
self.enemies.behave(Animated(first=0, last=1, ticks=8))
self.enemies.behave(DespawnBeyond(y_min=0))
self.enemies.behave(CameraBound(self.camera))
```

## What has to change under the hood

- **`vs2/params.py`**, new: the parameter types and their introspection.
- **`vs2/actions.py`**, new: `Action` and the vocabulary.
- **`vs2/behaviors.py`**, new: `Behavior` and the built-in catalog. All three
  must compile with mpy-cross and stay import-cheap — a game that never calls
  `behave()` must not pay for them, so catalogs are lazy-imported per class.
- **`vs2/__init__.py`**: `behave()`/`behaviors`/`behavior()` on `Sprite`,
  `SpritePool`, `Family` and (second wave) `Tilemap`; `SpritePool.var()` and
  the `spawn()` reset; `Scene.family()`; `Sprite.despawn()`; the scene run
  list built during `_seal_drawables()`; the Behavior pass in `scene_step()`
  between `update()` and `_run_defaults()`; `limits.behaviors`; `vs2.DONE`;
  `Tilemap.cell_at()`.
- **`ventilastation/director.py`**: one `elif cmd == "vs2beh"` next to
  `hallfilter`, delegating to `ventilastation/behavior_control.py` with the
  same `handle_command(parts, send, scene)` signature the other three use.
- **`web/vendor/blockly`**: vendored, lazily loaded.
- **`web/`**: the block editor pane, the custom fields (`Angle` dial, `Points`
  overlay, ROM-backed dropdowns), the MicroPython generator, the scene editor,
  the inspector block and the `vs2beh` client. Needs a `?v=` cache-bust.
- **`tools/`**: a headless generator so CI can regenerate every in-tree
  generated file and assert it is byte-identical.
- **`docs/vs2/`**: tutorial chapters on behaviors, on writing one in blocks,
  and on the scene editor; `reference/behaviors.md` and `reference/actions.md`
  generated from the parameter declarations.
- **`tests/`**: allocation regression, the dispatch benchmark as a guard
  against a refactor reintroducing per-sprite dispatch for uniform work,
  generator determinism, and parity of migrated `vixeous`/`vyruss_vs2`.

## Rollout, in dependency order

1. `vs2/params.py` and `vs2/actions.py` with four Actions (`Move`, `MoveTo`,
   `Animate`, `Collide`). Prove the allocation and dispatch numbers in tests.
2. `Behavior`, `behave()`, the run list, the tick pass, `limits.behaviors`.
   `Projectile` as the worked example, hand-written.
3. Instance variables, the `spawn()` reset, and families. These are small,
   independent of the editor, and immediately useful to hand-written games.
4. The six attributes and the three first-wave movements.
5. `vs2beh list` / `set` / `reset` and the director hook. Tune from a serial
   console before any UI exists — if it is not useful at that level, the panel
   will not save it.
6. The inspector panel: generic widgets, the two-level tree, the live-tune
   loop against a hand-written game.
7. The scene editor and the `build()` generator. Round-trip, checksum, Detach.
   Migrate one small game (`mapdemo`) end to end.
8. Blockly: palette, tick skeleton, generator, line map. Re-author
   `Projectile` and `Damageable` as block programs and ship the generated
   output as the catalog.
9. Migrate `vyruss_vs2` and `vixeous`. The real acceptance test.
10. Second wave, `Tilemap.cell_at()`, `Angle` and `Points` fields.

Steps 1-6 stand alone and are worth having even if the editor never ships.
That ordering is deliberate: nothing before step 7 depends on the editor
existing.

## Acceptance checks

- A scene with the full catalog attached to 100 sprites allocates zero bytes
  across 1000 ticks.
- A Behavior's uniform work stays at or under the hand-written loop it
  replaces; its per-sprite branch stays within 50% of inlined arithmetic.
- `vixeous` and `vyruss_vs2` after migration are shorter, and play identically
  at 600 RPM on hardware.
- Every standard composed behavior is expressible in blocks, and the shipped
  `.py` is the generator's output — not a hand-written file the blocks
  approximate.
- Opening a standard behavior in the editor, duplicating it and changing one
  block produces a working forked behavior without touching `vs2/`.
- Regenerating an unchanged workspace is a no-op diff.
- A parameter changed from the panel is visible on the disc within one tick,
  over serial, on the physical console.
- A game hand-written against revision 2 runs unmodified.
- Every error names the scene, the subject, the Behavior and the fix, and is
  raised during `build()`.

## Open for review

- **Which `Pilotable` schemes ship?** `rim` (`vyruss_vs2`) and `turn`
  (`vixeous`) both exist and are not the same thing. A third game would settle
  whether `free` is needed, or whether the two are one behavior with a
  `follow_lag` parameter.
- **Does the editor own `update()` too, eventually?** This proposal draws the
  line at structure. If blocks later author `update()`, the game file becomes
  generated as well and the hand-written tier disappears — which is a
  different product, and worth deciding on purpose rather than by drift.
- **Is `Spawner`'s subject the scene?** Wave spawning in both games is scene
  logic with no sprite behind it, which would make it the first Behavior
  attached to a `Scene` — a fourth subject kind after Sprite, SpritePool and
  Family.
- **Do Actions need their own segment in the protocol path?**
  `enemies.damageable.blink.on_ticks` is four deep; flattening loses the tree
  the panel and the block editor both want.
- **Should instance variables be typed beyond the parameter types?** Construct
  has number/text/boolean. `Angle` and `Frames` are tempting here and may be
  over-fitting.
- **Should the catalogs ship frozen** in the runtime bundle, or as normal
  importable modules? Frozen imports faster and costs flash for games that
  never use it.
