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
- **State machines** — a declared form for the multi-state entities that four
  of the nine surveyed games hand-rolled, including the timed transitions that
  every temporary status effect is really made of.
- **Instance variables, kinds and families** — game-owned per-instance data
  declared on a pool, per-type default rows over it, and groups of pools
  addressed as one. All three are things every game in the tree fakes.

And above all three: **the editor owns `build()`**. Scene structure — layers,
pools, tilemaps, instance variables, behavior attachments and their parameters
— is authored in the editor and emitted as generated MicroPython. The game
keeps `update()` and its callbacks.

## Why this exists

Revision 2 gave games a sealed display graph, pools, labels and tilemaps. It
did not give them anywhere to put *conduct*, and it gave the editor nothing to
edit. So every game writes conduct again, at the lowest possible level, in
Python only.

Two shipping VS2 games and seven V1 jam games were read in full for this
proposal: `vixeous`, `vyruss_vs2`, `dome_defander`, `vajon`,
`vasura_espacial`, `vs`, `2bam_sencom`, `tincho_vrunner` and
`fanphibious_danger`. The duplication is not in the arithmetic, it is in whole
concepts:

| The concept every game re-implements | Where |
|---|---|
| **An explicit state machine** | `vasura_espacial/estado.py` (10 states, `on_enter`/`step`/`on_exit`, transitions by return value), `fanphibious_danger.py:13-17` (four named states), `vyruss_vs2.py:209-220` (a sequential one), `vs.py:152-160` (three booleans doing the job) |
| Constant velocity, then leave the play field | `vixeous.py:314-331`, `vyruss_vs2.py:414-431`, `dome_defander/misil.py:31-38` |
| Show, animate once, disappear | `vixeous.py:344-350`, `vyruss_vs2.py:432-437`, `dome_defander/misil.py:77-86`, `vasura_espacial/estado.py:36-68`, `2bam_sencom.py:395-410` |
| Per-instance data bolted on at spawn | `vixeous.py:216-220`, `vyruss_vs2.py:206-210`, `vasura_espacial/entities/entidad.py:8-16` |
| **Per-type data tables indexed by a kind id** | `vs.py:53-67` (nine parallel arrays for items and nerds), `vasura_espacial/entities/enemigos/enemigo.py:61-99` (a subclass per enemy carrying its own constants) |
| A thing the player flies | `vyruss_vs2.py:34-44` + `:331-348`, `vixeous.py:257-289`, `vajon.py:293-337` (momentum and damping), `vasura_espacial/entities/nave.py:71-94` |
| A thing that takes damage, flashes, dies with a score and a sound | `vyruss_vs2.py:360-403`, `vixeous.py:220` + `:352-360` + `:396-403` + `:456-461`, `vasura_espacial/entities/nave.py:96-151` |
| **A temporary status that reverts on a timer** | `tincho_level.py:452-507` (four of them: power-up, invulnerable, reversed, slowed), `vasura_espacial/entities/nave.py:133-151` (60-frame invincibility), `vixeous.py:352-360` |
| A projectile that travels, expires, and hurts what it touches | `vixeous.py:314-323` + `:390-434`, `vyruss_vs2.py:414-431`, `2bam_sencom.py:277-300` |
| A scripted path, then join a formation | `vyruss_vs2.py:72-115` + `:209-220` |
| Sweep back and forth while animating | `vixeous.py:324-332`, `:333-343`, `vasura_espacial/estado.py:168-188` |
| **Facing, with a second frame bank per direction** | `vasura_espacial/entities/entidad.py:86-94`, `fanphibious_danger.py:20-21` |
| **A spawn schedule written as data** | `vs.py:45-51` (`(tick, kind, lane)` tuples per level), `2bam_sencom.py:688-703` |
| **Lane or grid placement** | `vs.py:33-34` (a 3x3 grid), `tincho_level.py:136-144` (columns with fixed centres), `mapdemo.py:52-58` |
| The same test run against three different pools | `vixeous.py:390-414` — shots vs boss, then vs enemies, then bombs vs targets |
| **Un-projecting screen position back to world depth before a hit test** | `2bam_sencom.py:1086` — a hand-transcribed 55-entry inverse of the TUNNEL curve, used at `:365` and `:987` |
| **Naming a palette colour and animating it** | `2bam_sencom.py:1302-1349` — re-parses the ROM header to find a colour by RGB, then recolours the core, cities, font and explosions per level |
| **Controlled randomness from a bag, not `choice()`** | `2bam_sencom.py:1185-1212` (a real Fisher-Yates shuffle bag, used for both enemy types and target cities) |
| **Sub-pixel position, hand-rolled** | `vasura_espacial/entities/entidad.py:55-72` (floats plus `floor`), `fanphibious_danger.py:92-115` (a 256x fixed-point shim) — both of which revision 2's 8.8 coordinates already solve |

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
| `Tween(x, y, ticks, ease)` | `DONE` when elapsed | `fanphibious_danger.py:145-146` — a hop that covers a fixed distance in a fixed number of frames |
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

### Collision happens in world space, not screen space

`Sprite.overlaps()` compares raw `x`/`y` boxes. On a `HUD` layer that is
correct. On a `TUNNEL` or `FULLSCREEN` layer it is not, and the error is not
subtle: Y is depth on a non-linear curve, so two sprites eight units apart are
physically close near the rim and far apart near the centre. A fixed hitbox
means a hitbox that silently changes size as things move inward.

`2bam_sencom` is the only game that confronted this, and it did so by
transcribing the inverse curve into the source as 55 magic numbers
(`:1086`) and converting every hit position through it before testing
(`:365`, `:987`). `vixeous` avoids the problem rather than solving it, by
keeping a parallel `theta` on every entity and comparing in world space
(`:390-434`). Nobody else noticed.

The runtime already owns this curve — it is what the native renderer applies
every frame — so a game hand-copying it is a defect in the API, not in the
game. Three additions close it:

```python
vs2.display.to_depth(led_row)      # screen row  -> world depth
vs2.display.to_row(depth)          # world depth -> screen row
vs2.display.polar(x, y)            # cartesian   -> (angle, depth)
```

`Collide` then gets a `space` parameter — `screen` (today's behaviour, right
for HUD) or `world` (un-project first, right for everything else) — and
`world` is the default on any layer whose projection is not `HUD`. The
cartesian helper is separate but comes from the same missing piece: the aim
code at `2bam_sencom.py:975-996` runs `atan2` and `sqrt` per tick to turn a
stick into a point on the disc, which is a conversion every crosshair game on
this hardware will need and none should write twice.

Radial hit tests belong here too. `2bam_sencom` does not test boxes at all: an
explosion has a `radius` that changes with its animation frame
(`BOOM_RADIUS`, `:127`) and only damages while that radius is non-zero
(`do_damage`, `:213`). So `Collide` also takes `radius=` for a circular
test, and a damage window is a `Frames` parameter naming which frames are
live.

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

**Durations are ticks in the API and seconds in the editor.** Every game in
the survey counts ticks, but `2bam_sencom.py:396` declares its animations in
`duration_secs` because that is how a person thinks about an explosion. Integer
ticks are the right storage — no rounding drift, no float in the tick — so the
API keeps them and the editor shows "13 ticks (0.4 s)" beside the slider,
which it can do because it knows the 30 ms period. Authoring in seconds and
storing ticks would silently change behaviour whenever the period moved.

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

### Kinds: per-type defaults as a table

The second survey turned up a pattern strong enough to deserve its own
primitive. `vs.py:53-67` carries nine parallel arrays — `item_hps`,
`item_atks`, `item_frame_amount`, `item_frame_rate`, `nerd_hps`,
`nerd_speeds` and friends — all indexed by a type id, so `activate_item(id)`
reads a column out of each. `vasura_espacial` does the same thing with
inheritance instead: `Driller`, `Chiller` and their siblings are subclasses
whose only content is constants (`velocidad_y = 0.52`, `largo_animacion = 7`,
`puntaje = 75`, at `enemigo.py:61-72`).

Both are one pool holding several *variants*. Construct would model it with a
family plus instance variables and leave the table to the author. We can do
better, because the panel is already a table editor:

```python
self.enemies.var("hp", 1)
self.enemies.var("score", 40)
self.enemies.var("speed_y", 1.0)
self.enemies.kinds(
    #        hp  score  speed_y
    driller=( 3,    75,    0.52),
    chiller=( 1,    40,    0.60),
)
...
self.enemies.spawn(x, y, kind="chiller")
```

`kinds()` declares named rows over the pool's own instance variables, and
`spawn(kind=...)` applies one. The row is resolved to an index at build, so
spawning costs the same loop that already resets defaults. In the panel it is
exactly what it looks like — a spreadsheet, one row per enemy type, which is
the artefact a designer actually wants to edit and the one thing in this whole
proposal that no amount of slider-dragging replaces.

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

## State machines

This is the largest gap in the previous revision, and the survey is
unambiguous: four of the nine games read invented one.

`vasura_espacial/estado.py` is a complete hierarchical state machine — ten
states with `on_enter`/`step`/`on_exit`, transitions expressed by returning
the next state class from `step()`, and inheritance used to share work
(`Vulnerable.step()` runs the collision checks every vulnerable state needs;
`Bajando`, `ChillerBajando` and `BajandoEnEspiral` layer movement on top of
it). It has timed transitions (`frames_left` counting down to a new state) and
probabilistic ones (`if randint(0, 100) < 25`). `fanphibious_danger.py:13-17`
declares four named states as module constants and branches on
`frog.state` throughout its main loop. `vyruss_vs2.py:209-220` builds a
sequential one out of a list. `vs.py:152-160` uses three booleans —
`is_active`, `is_reloading`, `is_waiting_to_deactivate` — because it had no
better vocabulary.

A Behavior is already a state machine; what is missing is a way to *declare*
one, so it becomes a shape the panel and the block editor can see instead of a
tangle of counters only the author understands.

```python
class Enemy(StateMachine):
    speed_x = Number(1.25, min=0, max=8, step=0.25)
    speed_y = Number(0.6, min=0, max=8, step=0.25)

    states  = ("descending", "orbiting", "chasing", "exploding")
    initial = "descending"

    def descending(self, sprite):
        sprite.y -= self.speed_y
        if sprite.y <= GROUND:
            return "exploding"

    def enter_orbiting(self, sprite):
        self.hold(sprite, 128, then="descending")

    def orbiting(self, sprite):
        sprite.x += self.speed_x * sprite.facing
```

- **States are named**, and the name is what the protocol, the panel and a
  traceback report. `enemies.enemy.state` is readable from the panel while the
  game runs, which is most of a debugger for free.
- **A step method returns the next state, or `None` to stay** — vasura's
  protocol, which is the one that reads best.
- **`enter_<state>` and `exit_<state>` are optional hooks**, matched by name.
- **`hold(sprite, ticks, then=...)`** is the timed transition, replacing the
  four hand-rolled `frames_left` countdowns in vasura and the four
  `call_later` status effects in `tincho_level.py:452-507`. A temporary status
  — invulnerable, powered up, reversed, slowed — is a state with a hold on it,
  which is why this subsumes the whole "temporary status that reverts" row of
  the evidence table.
- **State lives in one primed byte** (`sprite.fsm_state`), and dispatch is a
  tuple of bound methods indexed by that byte — one index and one call, no
  string comparison. It pays the per-sprite branch cost measured below and
  nothing more.

A state machine is also the single most natural thing to draw. Scratch and
Construct both make "when I am in this state" a top-level visual block, and it
is what the Blockly skeleton below is shaped around.

## Named palette colours

Construct's effects make no sense on shaderless hardware. Palette animation is
what we have instead, and it is more capable than it sounds: recolouring an
index recolours every pixel drawn with it, everywhere, for free, on a machine
with no blending at all.

Revision 2 exposes `vs2.display.palettes` as a mutable buffer plus
`apply_palettes()`, which is the right half of the feature. The missing half
is *naming*. `2bam_sencom` wanted per-level colour themes, a white font flash,
red alert on the last city, and randomised explosion colours — and to get
them it re-parses the ROM header with `struct.unpack` to locate the palette
block, then linearly searches that block for a hardcoded RGB triple to
discover which index to poke (`:1302-1349`). It caches four indices found this
way, and keeps a dirty flag so it only flushes once per tick.

The dirty flag is right and matches `apply_palettes()`. The rest is a game
reimplementing the asset pipeline because the pipeline does not tell it
anything:

```yaml
# __images__.yaml
palette:
  colors:
    core:  [0, 7, 250]
    city:  [147, 0, 255]
    font:  [0, 255, 0]
    boom:  [0, 255, 240]
```

```python
vs2.display.color("core", 255, 0, 0)   # by name, resolved at build
vs2.display.apply_palettes()
```

Declared beside the art, resolved to an index once at build, and — the part
that matters for this proposal — rendered in the panel as a **colour swatch**
with a picker. A named colour is a parameter type like any other, so a
behavior can take one (`Damageable(flash_color="hurt")`), and the two effects
that games actually want, a flash and a cycle, become `Flashing(color, ticks)`
and `Cycling(colors, ticks)` in the attributes tier.

This is the closest thing to Construct's effects that the hardware can
support, it costs nothing per frame, and one game has already built the ugly
version of it.

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
| `Transient(animate, ticks, sound, on_end)` | `vixeous.py:344-350`, `vyruss_vs2.py:432-437`, `dome_defander/misil.py:77-86`, `vasura_espacial/estado.py:36-68` |
| `Animated(first, last, ticks, mode, bank, bank_size, images)` | every game in the tree |
| `DespawnBeyond(y_min, y_max, x_min, x_max, on_leave)` | `vixeous.py:308-309`, `:327-329`, `vyruss_vs2.py:417-418`, `:430-431` |
| `Recycling(x_range, y_range)` | `vajon.py:119-124` — a rock that leaves the top is repositioned rather than despawned; Construct's `Wrap` |
| `Lifetime(ticks, on_expire)` | the `age` counters in both VS2 games, `2bam_sencom.py:183-216` |
| `Blinking(on_ticks, off_ticks, duration, on_end)` | `vixeous.py:456-461`, `vasura_espacial/entities/nave.py:116-151` (twice, two different ways, in one file) |
| `Pinned(to, offset_x, offset_y)` | `vyruss_vs2.py:384-391`, `vajon.py:246-247` |
| `Carried(on_board, released_by)` | `fanphibious_danger.py:59-90` — a frog rides a floating object, a ring drags everything on it |
| `Shaking(amplitude_x, amplitude_y, ticks)` | `vajon.py:240-241` — a per-tick `randrange` jitter |
| `Flashing(color, ticks)` | `2bam_sencom.py:728`, `:902` — a named palette colour driven white, or red on last-city alert |
| `Cycling(colors, ticks)` | `2bam_sencom.py:761`, `:824` — randomised font and explosion colours per wave |

These are the ones that get attached forty times a project; none is more than
a few lines. All ship in the first release except `Carried`, `Flashing` and
`Cycling`, which wait on named palette colours.

Three of them changed shape because of the second survey:

**`Animated` needs frame banks.** `vasura_espacial/entities/entidad.py:86-94`
picks `frame = phase` or `frame = phase + largo_animacion` depending on which
way the sprite faces, because the art is not mirror-symmetric and `flip_x`
would be wrong. `bank_size` plus a `bank` read from an instance variable
covers it, and it is the same idea `Label.write(frame_offset=...)` already
uses for a font strip's second colour.

**`Animated` needs an explicit frame sequence, not just a range.**
`2bam_sencom.py:126` animates an explosion as
`BOOM_FRAMES = [4, 3, 2, 3, 2, 3, 2, 3, 2, 1, 0]` — a flicker that no
`first`/`last`/`pingpong` combination produces. A `frames=(...)` tuple
covers it and makes `first`/`last` the convenience case rather than the
model.

**`Animated` should be able to take a duration instead of a rate.** Both
sencom animators derive their step from a wanted total time —
`fpst = len(BOOM_FRAMES) / ttl` at `:190` and
`_fracInc = SECONDS_PER_STEP * len(frames) / duration_secs` at `:402` — and
both advance a *fractional* frame index so the speed is continuous rather
than an integer divisor of the tick. `ticks=` and `duration=` are the same
parameter seen from two ends; the editor should offer both and store one.

**`Animated` also needs an image list.** `vajon.py:226` animates by swapping
strips — `stripes["pozo" + str(pi) + ".png"]` — which builds a string on the
heap every single tick, in the hot path, forever. `vs.py:247` does the same
with a lookup table. An `images=(...)` parameter resolved once at build makes
that impossible to write.

**`Carried` is a runtime relationship, not a build-time one.**
`Pinned(to=...)` is fixed at build; `fanphibious_danger` needs a frog to
board and leave a log while the game runs. `Carried` holds a carrier
reference in primed state, so attaching and detaching are reference writes
that allocate nothing.

### Movements — one per subject

| | Replaces |
|---|---|
| `Moving(speed_x, speed_y, accel_x, accel_y)` | `vixeous.py:315-323`, `vyruss_vs2.py:415`, `:429` |
| `Patrolling(axis, amplitude, period, wave, drift_x, drift_y)` | `vixeous.py:324-332`, `:333-343` |
| `PathFollowing(points, relative, speed_x, speed_y, loop, on_finish)` | `vyruss_vs2.py:72-115` + `:209-220` |
| `Pilotable(player, scheme, speed_x, speed_y, bounds, fires, fire_button, fire_sound)` | `vyruss_vs2.py:34-44` + `:331-348`, `vixeous.py:257-289` |
| `Chasing(target, speed_x, speed_y, turn_rate, give_up_range, on_reach)` | `vasura_espacial/estado.py:139-157` |
| `Orbiting(centre_y, speed)` | `vasura_espacial/estado.py:121-137` |
| `Laned(centres, speed, on_change)` | `vs.py:33-34`, `tincho_level.py:136-144` |

The previous revision claimed `Chasing` and `Orbiting` had no precedent in
the tree. That was wrong, and the correction matters because it moves both
out of the speculative column. `vasura_espacial` has `Persiguiendo`, which
normalises a vector to the player and steers along it — including the
shortest-arc wrap that `delta_x if abs(delta_x) < 128 else -delta_x` gets at —
and `Orbitando`, which holds a depth and advances the angle at a fixed rate.
Both are real, both are the kind of thing that is fiddly enough to get wrong
once per game, and both now ship in the first wave alongside `Moving`,
`Patrolling` and `PathFollowing`.

`Laned` is new from the second survey: `vs` snaps items to a 3x3 grid and
`tincho_vrunner` snaps the runner to fixed column centres, both accumulating
sub-cell movement until a boundary is crossed and then firing what is really
an event (`tincho_level.py:288-305` calls it `cambió_tile`). `on_change` is
that event, and `Tilemap.cell_at()` is the tilemap-flavoured version of the
same question.

`Pilotable` gained two schemes. `vajon.py:293-337` steers with momentum:
input accumulates into an `inertia` term capped at ±8 which decays back toward
zero every third tick — neither `rim` nor `turn`, and the one that feels best
on a disc that is already spinning. `2bam_sencom.py:975-996` is stranger and
more useful: the stick drives a cartesian `(ax, ay)` clamped to the unit disc,
which is converted to an angle and a depth through `atan2`, `sqrt` and the
inverse projection table. That is a *crosshair* — you point at a place on the
disc rather than steering a thing around it — and it is the model every
aiming game on this hardware will want. Which schemes ship is still open
(below), but the survey says at least five, and the last one needs the
display helpers from the collision-space section above.

### Composed — ship as block programs, meant to be forked

| | Replaces |
|---|---|
| `Projectile(speed_x, speed_y, range, damage, hits, burst, sound)` | the shot/bomb loops and hit tests in both games |
| `Damageable(hp, invulnerable_ticks, blink, explosion, score, sound, on_damage, on_death)` | `vyruss_vs2.py:360-403`, four scattered pieces of `vixeous` |
| `FiringAt(target, projectile, every, jitter, lead, sound, on_fire)` | `vyruss_vs2.py:322-329` |
| `Spawner(pool, every, count, pattern, schedule, on_spawn)` | `vixeous.py:209-243`, `vyruss_vs2.py:245-261`, `vs.py:45-51`, `2bam_sencom.py:688-703` |
| `Collectible(score, sound, on_pickup)` | second wave |

`Projectile` and `Damageable` ship first, as the two flagship block programs —
they are the proof that the palette can express what the catalog needs.

`Spawner`'s `schedule` parameter is worth its own note, because
`2bam_sencom.py:1112-1180` is the best-designed thing in the survey and the
strongest argument in it for a table editor. Its wave format is
`(duration_seconds, amount, [bag of enemy types])`, with the spawns spread
evenly across the duration and a floor that extends the wave if the count
could not otherwise fit (`:1225-1235`). The types come from a `ShuffleBag`
(`:1185-1212`) — a real Fisher-Yates bag that reshuffles on exhaustion, so
the distribution is controlled rather than merely random, which is the
difference between "mostly fair" and `choice()`. Controlled randomness is
common enough — sencom uses one bag for enemy types and another for target
cities — that `ShuffleBag` belongs in `vs2` next to the behaviors rather than
in each game.

And the author drew the column headings as an ASCII diagram in a comment:

```text
#  ,------------- Duration seconds (will extend to amount steps if too low)
# |     ,-------- Amount
# |     |   ,---- Enemy shuffle bag
( 3  ,  0, []          ),
(10  ,  5, [W_M0]      ),
```

Someone hand-drew a spreadsheet in source comments because there was nowhere
else to put one. That is the artefact the panel should be showing.

`Damageable` exposes `hurt(sprite, amount)` for other behaviors to call. Note
that Construct has no equivalent: it keeps behaviors mechanical and puts game
rules in the event sheet. We can go further because Python *is* our event
sheet, and because a forkable block program is not the black box a compiled
Construct behavior is.

Every Behavior that fires an event takes a `sound=` parameter rather than
there being a sound behavior — every spawn and hit in both games is
immediately followed by `vs2.audio.sound(...)` (`vixeous.py:197`, `:298`,
`:303`, `:358`; `vyruss_vs2.py:319`, `:329`, `:377`, `:397`). `sound=` accepts
a tuple as well as a name, picked from at random, because
`2bam_sencom.py:154-158` keeps three spawn chops and varies between them to
stop the repetition wearing through.

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

- **Gravity and a physics solver.** Nine games read in full, and not one
  integrates a velocity under acceleration. `fanphibious_danger` — a
  Frogger, the genre most likely to want a jump arc — implements its hop as a
  fixed number of frames covering a fixed distance
  (`fanphibious_danger.py:145-146`), which is a `Tween`, not physics. The one
  `self.vy` in the whole tree (`vyruss/vyruss.py:687`) is a constant. This is
  the clearest "no" in the proposal.
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

Two habits in `2bam_sencom` are worth citing as evidence that these budgets
are load-bearing rather than bureaucratic. It opens with a hand-written sprite
census in a comment block (`:58-72`) — "5 cities, 4 booms, 20 missiles … 41
total" — counted by hand because nothing counted it for them; that is exactly
what `vs2.limits` and the census in `ResourceLimitError` now produce. And it
schedules `gc.collect()` every sixty seconds (`:558-561`), which is an author
who knows the game allocates and would rather choose when the pause lands than
have it land on a visible frame. The sealed scene, primed state and pooled
spawning exist so that timer never needs to be written again.

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

A `StateMachine` gets the same skeleton with one hat block per state, which is
the shape Scratch and Construct both settled on and the reason the state
machine belongs in this proposal rather than in game code:

```
‹Enemy›  initial state: descending
├─ when in ‹descending› ▸ [ Move  speed_y (-0.6) ]
│                         [ if ‹y ≤ (GROUND)› → go to ‹exploding› ]
├─ on enter ‹orbiting›  ▸ [ hold (128) then go to ‹descending› ]
└─ when in ‹orbiting›   ▸ [ Move  speed_x (1.25) x facing ]
```

Each hat generates one method; `go to` generates the return value; `hold`
generates the timed transition. The ten states of
`vasura_espacial/estado.py` are ten hats, and the inheritance it used to share
the collision check becomes a shared state the others fall through to.

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
- **`vs2/behaviors.py`**, new: `Behavior`, `StateMachine` and the built-in
  catalog. All three must compile with mpy-cross and stay import-cheap — a
  game that never calls `behave()` must not pay for them, so catalogs are
  lazy-imported per class.
- **`vs2/__init__.py`**: `behave()`/`behaviors`/`behavior()` on `Sprite`,
  `SpritePool`, `Family` and (second wave) `Tilemap`; `SpritePool.var()`,
  `SpritePool.kinds()` and the `spawn()` reset and `kind=` argument;
  `Scene.family()`; `Sprite.despawn()`; the scene run list built during
  `_seal_drawables()`; the Behavior pass in `scene_step()` between `update()`
  and `_run_defaults()`; `limits.behaviors`; `vs2.DONE`;
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
3. Instance variables, `kinds()`, the `spawn()` reset, and families. Small,
   independent of the editor, and immediately useful to hand-written games.
4. `StateMachine`, with `hold()`. Port `vasura_espacial`'s ten states to it as
   the proving case — if the declared form is not clearly better than the
   hand-rolled one it replaces, stop here and rethink.
5. The nine attributes and the five first-wave movements.
6. `vs2beh list` / `set` / `reset` and the director hook, including reading
   and forcing a sprite's current state. Tune from a serial console before any
   UI exists — if it is not useful at that level, the panel will not save it.
7. The inspector panel: generic widgets, the two-level tree, the `kinds` table
   editor, the live-tune loop against a hand-written game.
8. The scene editor and the `build()` generator. Round-trip, checksum, Detach.
   Migrate one small game (`mapdemo`) end to end.
9. Blockly: palette, tick skeleton, state hats, generator, line map. Re-author
   `Projectile` and `Damageable` as block programs and ship the generated
   output as the catalog.
10. Migrate `vyruss_vs2` and `vixeous`. The real acceptance test.
11. Second wave, `Tilemap.cell_at()`, `Angle` and `Points` fields.

Steps 1-7 stand alone and are worth having even if the editor never ships.
That ordering is deliberate: nothing before step 8 depends on the editor
existing. Step 4 is the one to reorder if something has to give — the state
machine is the highest-value item in this proposal and the one most likely to
change shape once real games use it.

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

- **Which `Pilotable` schemes ship?** The survey found five distinct models,
  not two: `rim` (`vyruss_vs2`), `turn` with camera follow-lag (`vixeous`),
  `momentum` with damping (`vajon.py:293-337`), free eight-way
  (`vasura_espacial/entities/nave.py:71-94`), and a cartesian crosshair
  (`2bam_sencom.py:975-996`). The first four probably collapse into one
  behavior with `inertia` and `follow_lag` parameters where zero means
  neither. The crosshair does not — it is aiming rather than moving, and it
  wants the polar and inverse-projection helpers — so it is likely a separate
  `Aimable`.
- **Should states be a separate `StateMachine` class, or should every Behavior
  be able to declare states?** Making every Behavior a potential state machine
  is fewer concepts; keeping them separate keeps the common stateless Behavior
  cheap to read and cheap to explain. This proposal splits them, weakly.
- **Do behavior callbacks need more than one subscriber?**
  `vasura_espacial/common/evento.py` is a full publish/subscribe class, which
  suggests at least one author wanted fan-out. This proposal gives each hook
  one callback, because `Evento.disparar` builds a list on every fire — a list
  comprehension evaluated purely for its side effects — and that is exactly
  the per-tick allocation the sealed-scene rule exists to prevent. A game that
  genuinely needs fan-out can fan out inside its one callback.
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
- **Where do the display helpers live?** `to_depth`, `to_row` and `polar`
  are proposed on `vs2.display` because that is where geometry already lives,
  but they are the first things there that are pure maths rather than hardware
  state. The alternative is a `vs2.geometry` module, which is tidier and one
  more import for a game to know about.
- **Should `Collide`'s default space depend on the layer's projection?**
  Defaulting to `world` on TUNNEL and `screen` on HUD is what every game
  actually wants, but it makes one parameter's default depend on another
  object's state, which is the sort of implicitness the rest of this proposal
  avoids.
