# VS2 Behaviors, Actions and the Scene Editor

Status: draft for review
Baseline: `vs2` revision 2 as shipped (`apps/micropython/vs2/__init__.py`)

Five layers on top of revision 2, plus the editor that owns them.

- **Actions** — small, parameterised, allocation-free operations on a sprite.
  An Action never decides.
- **Behaviors** — named, parameterised per-subject state machines written in
  the vocabulary of Actions. A Behavior never touches the renderer directly.
- **State machines** — a declared form for multi-state entities, including
  timed transitions.
- **Variables** — per-instance on a pool, per-type rows over them (`kinds`),
  families addressing several pools as one, plus scene, project and saved
  state.
- **Layer cameras and projection curves** — a layer moves its contents
  together, and its projection is a parameterised curve rather than one
  hardcoded tunnel.

Above all five, the editor owns the generated MicroPython — `build()` and
`update()` alike. There are two ways to build a game and both are complete:

- **From the editor, writing no MicroPython.** A whole project — several
  scenes, a menu, a game-over, transitions, scoring — authored in blocks and
  emitted as MicroPython. This is a hard requirement.
- **By hand, in MicroPython.** The same API, written directly.

`Detach` is the seam: a generated file is regenerated freely until the author
takes ownership of it, and after that it is ordinary MicroPython forever.
Nothing else transfers ownership and there is no round-trip back.

## Design rules

1. **A Behavior is the unit a designer thinks in.** "Pilotable by joystick 2",
   "takes three hits", "chases the player".
2. **Nothing on the board costs more than the code it replaces.** Game logic
   takes a Step every 30 ms on an ESP32 running MicroPython.
3. **Nothing in a Step allocates.** Parameters, per-instance state, instance
   variables, families and every cross-reference resolve during `build()`; the
   tick writes only fields that already exist.
4. **One declaration, four consumers.** A parameter is declared once with type,
   range, label and unit. Runtime, reference docs, property panel and Blockly
   field all read that declaration.
5. **Nothing on the board knows the editor exists.** The editor emits
   MicroPython, compiled by mpy-cross, packaged in an ordinary `.vs2`.
6. **The standard behaviors are forkable.** Composed behaviors ship as block
   programs. If the catalog needs something the palette cannot express, the
   palette is wrong.
7. **A whole game is authorable without writing MicroPython** — a project with
   several scenes, a menu, a game-over, and a score that survives a transition.

Short enough to enforce in review:

> **An Action never decides. A Behavior never draws. The editor owns the
> generated code; `Detach` is the only way out.**

### Naming

**Actions are verbs. Behaviors describe what a thing is or does.** `Move` /
`Moving`. `Animate` / `Animated`. `Steer` / `Pilotable`. `Collide` /
`Damageable`.

Within Behaviors: **`-ing` when the subject acts, `-able` when something else
acts on it.** `Moving`, `Chasing`, `Orbiting`, `Patrolling`, `Blinking`,
`Scrolling`, `Aiming` are things a sprite does. `Pilotable` and `Damageable`
are done *to* it, and are the only two `-able` entries in the catalog.

## Projects, scenes and ownership

The editor's unit is a **project**, which owns:

- an ordered list of **scenes**, one workspace each, and which one is the entry;
- **project variables** that outlive a transition;
- the **asset pack** — `images/`, `sounds/`, `menu.png`;
- `meta.json`.

Scene flow is authored, not implied: `push`, `pop` and `switch` are system
blocks and the editor draws the scene list as the graph they form. The runtime
already supports this unchanged.

Every file the editor emits is generated **until detached**, including
`update()`. A fully editor-authored project has no hand-written file:

```
games/alecu/vixeous/
  meta.json              GENERATED. Scene list, entry scene, launcher metadata.
  code/
    vixeous_scene.py     GENERATED. Layers, pools, vars, behaviors, params.
                         Carries the editor workspace as a trailing blob.
    vixeous.py           GENERATED. update(), event handlers, scene flow.
                         Detach to take ownership; then it is yours forever.
    behaviors/
      chasing.py         GENERATED from blocks. One file per custom behavior.
  images/  sounds/  menu.png
```

```python
# vixeous_scene.py  -- generated, do not edit. body-sha: 8f3a1c02
import vs2
from vs2.behaviors import Damageable, Moving, Patrolling, Projectile, Transient


class VixeousScene(vs2.Scene):
    def build(self):
        self.world = self.layer("world", projection=vs2.VS1_TUNNEL)
        self.hud = self.layer("hud", projection=vs2.HUD)

        self.explosions = self.world.sprite_pool(
            "explosion.png", 5, on_empty=vs2.RECYCLE)
        self.explosions.behave(Transient(animate=True, ticks=3, sound="boom"))

        self.enemies = self.world.sprite_pool("enemy.png", 6)
        self.enemies.var("kind", 0, min=0, max=2)
        self.enemies.behave(Moving(speed_y=-1))
        self.enemies.behave(Patrolling(field="x", amplitude=64, period=128))
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

# blocks: eJyNVMtu2zAQ/BWCpxaQ...
```

Each file is wholly generated or wholly yours; `Detach` moves it across, one
file at a time. A project may keep its scene generated while the game file
becomes hand-written.

`on_build()` serves that part-detached case: a hook where a hand-written
subclass does post-construction work needing the graph. Because drawables
created there are invisible to the editor's model but still consume the sprite
budget and take a place in draw order, the generator emits **numbered hook
points in draw order** rather than one hook at the end. The editor recovers the
true scene by running `build()` in the wasm emulator and reading
`vs2.export_scene_payload()`.

When the editor wires `on_death=` to a handler that does not exist, it creates
the event hat. On a detached file it offers a Python stub instead, on creation
only, never on regeneration.

**No runtime change is needed for any of this.** `build()` and `update()` stay
the hooks they are today; the editor generates into them.

## Layers

### Cameras

`layer.camera_x` and `layer.camera_y` are a render-time translation of
everything the layer draws. Sprite and tilemap `x`/`y` are **world**
coordinates; no game computes a screen position.

```python
self.world.camera_x = self.camera_theta      # once per tick, for everything
```

- **X is angular and wraps**, at no cost: the renderer's
  `wrap_column_delta(render_column - sprite_x)` is already modular, so the
  camera is one addend inside it.
- **Y follows the layer's projection** — LEDs on `HUD`, depth on a tunnel.
- **A tilemap larger than the view still scrolls with `view_x`/`view_y`.** The
  camera moves the map; the viewport chooses which part is loaded.
- **Parallax falls out.** Layers hold their own cameras, so a background at
  `camera_x = theta // 2` is one line.

Cost is **O(1) in the Step** and one extra add per sprite per column in Paint.

### Projection curves

A projection is a 256-entry table mapping depth to LED row.

```python
vs2.HUD                    # Y is an LED index, 0..display.height-1
vs2.VS1_TUNNEL             # the historical curve: tunnel(gamma=0.28)
vs2.FULLSCREEN             # radial extent
vs2.TUNNEL                 # alias for VS1_TUNNEL

vs2.tunnel(gamma=0.28, near=0, far=53)
```

| | Effect |
|---|---|
| `gamma` | Curvature. `0.28` is V1. Lower crowds more of the world into the outer LEDs — a deeper, more foreshortened tunnel. `1.0` spreads depth evenly along the bar: a flat plane seen edge-on |
| `near` / `far` | Which LED rows the depth range lands on. `near=0, far=26` occupies the inner half of the bar; `near=53, far=0` inverts it, so depth travels outward |

That covers a shallow bowl, a dome, a well, a tunnel that stops halfway, and an
inverted tunnel. `TUNNEL` keeps working and keeps meaning what it meant, so a
revision-2 game runs unmodified; `VS1_TUNNEL` is the name for new code.

`FULLSCREEN` stays a mode rather than a curve — it scales a sprite's height to
a radial extent rather than placing rows — but reads the layer's curve for that
extent.

**One curve per layer, statically allocated.** A curve is `uint8_t[256]`, so
**2 kB covers every curve a scene can hold** at eight layers. For scale, one
64x30 single-frame image strip is 1920 bytes. At that price there is no pool,
no sharing and no `limits.curves`; each layer owns its table outright, which
also lets a layer's curve be rewritten at runtime — a tunnel that opens out as
a level progresses.

Curves are plain globals, so they sit in `.bss` and therefore internal SRAM.
Building one calls `pow()` 256 times, a `build()` cost.

The wire format needs nothing: a layer record in `export_scene_payload()` is
eight bytes of which five are reserved zeros, and camera X, camera Y and a
curve index fit in exactly those five. Zero already means "no camera, default
curve", so old and new readers interoperate in both directions.

### Geometry helpers

Per layer, because the curve is per layer:

```python
layer.to_depth(led_row)      # screen row  -> world depth
layer.to_row(depth)          # world depth -> screen row
layer.polar(x, y)            # cartesian   -> (angle, depth)
```

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
        live = sprites._live
        index = 0
        count = len(live)
        while index < count:
            sprite = live[index]
            sprite.dx += dx
            sprite.dy += dy
            index += 1

    def run_one(self, sprite):
        """Apply to one sprite, for a Behavior that branches per sprite."""
        sprite.dx += self.speed_x
        sprite.dy += self.speed_y
```

Two call forms, because Behaviors need both and they cost differently. The base
class defines `run()` as a loop over `run_one()`, so an Action overrides
`run()` only when hoisting saves something.

**Results.** `run_one()` returns `None` when nothing notable happened,
`vs2.DONE` when a durative Action finished (`MoveTo` arrived, `Animate`
completed a `once` cycle, `Wait` elapsed), or an object when it found one
(`Collide` returns the sprite hit, `Spawn` the new sprite or `None`). All are
existing objects; nothing allocates.

**Traversal is indexed, in both tiers.** `SpritePool.__iter__()` creates an
iterator object, which is fine for handwritten gameplay and not acceptable in a
zero-allocation pass. Bulk Actions get direct access to the pool's sealed live
array and use an indexed loop. **This applies to the per-sprite tier too** — a
Behavior's decision loop is an indexed `while` over `sprites._live`, not a
`for`, and it walks downward so `despawn()` (which fills the hole by swapping in
the tail) is safe. Handwritten gameplay outside a Behavior may keep using
`for sprite in pool`; the generator never emits it inside one.

**Movement Actions accumulate; the framework commits.** A movement Action writes
into a per-sprite `dx`/`dy` accumulator, and one commit pass per pool per tick
applies it to `sprite.x`/`sprite.y`. Composition is defined rather than
order-dependent, `Moving` + `Patrolling` on one pool is legal, and writes
through the `Sprite` facade drop from one per Action per sprite to one per
sprite.

**An Action declares which field it writes.** `Move` writes position, `Animate`
writes `frame`, `Oscillate` writes whatever it is pointed at. Every Action
writing a scalar takes `field=`, defaulting to the obvious one and accepting an
instance variable:

```python
Oscillate(field="boom_radius", amplitude=6, period=22)
```

The panel renders `field` as a dropdown over the pool's real fields and declared
instance variables, which is also what makes the Blockly socket typed.

### The vocabulary

| Action | Result |
|---|---|
| `Move(speed_x, speed_y, accel_x, accel_y)` | — |
| `MoveTo(x, y, speed_x, speed_y)` | `DONE` on arrival |
| `Tween(x, y, ticks, ease)` | `DONE` when elapsed |
| `Steer(heading, speed, turn_rate)` | — |
| `Oscillate(field, amplitude, period, wave)` | — |
| `Animate(first, last, ticks, mode)` | `DONE` at cycle end |
| `SetFrame(frame)` / `Flip(x, y)` | — |
| `Blink(on_ticks, off_ticks)` | — |
| `Spawn(pool, offset_x, offset_y, frame)` | new sprite or `None` |
| `Despawn()` / `Show()` / `Hide()` | — |
| `Collide(targets)` | sprite hit or `None` |
| `TileUnder(tilemap)` | tile index or `None` |
| `PlaySound(name)` | — |
| `Wait(ticks)` | `DONE` when elapsed |

`TileUnder` needs a new public method:

```python
Tilemap.cell_at(x, y)    # -> (column, row) or None
```

accounting for the map's `x`/`y`, its `view_x`/`view_y`, the tile size and the
circular X wrap.

### Collision

`Collide` tests in **world space, always**, and only ever compares sprites on
the same layer. Attaching one whose target lives elsewhere is a build-time error
naming both.

Both rules are the same rule. Sprites on different layers are in different
coordinate systems — the same numeric `y` is a different physical distance under
a different curve, the same `x` a different angle under a different camera — so
a cross-layer box test is meaningless, and making it meaningful would cost more
than the test. With one layer there is exactly one curve; every curve in the
family is monotonic, so un-projecting is well-defined, and on a `HUD` layer the
curve is the identity, under which a box comparison is provably unchanged. World
and screen space are the same test on HUD. So there is no conditional default:
`world` is correct on every layer.

`space="screen"` survives as an explicit escape hatch. On a tunnel it is the
bug: the curve is many-to-one after rounding, so a screen-space test loses depth
resolution near the centre and a hitbox silently changes size as it travels.

`Collide` also takes `radius=` for a circular test, and a damage window is a
`Frames` parameter naming which frames are live.

### Sprites against tilemaps

`Tilemap.cell_at()` and the `TileUnder` Action stay distinct from `Collide`:

| | `Collide(targets)` | `TileUnder(tilemap)` |
|---|---|---|
| Cost | O(N x M) pairwise | O(N) — a divide per sprite |
| Answer | the sprite hit, or `None` | the tile index under the point, or `None` |
| Question | "did two things touch" | "what am I standing on" |

Both are Actions returning a value or `None`, so both drop into the same `if`
socket in the block editor and a game can ask both in one tick.

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
        live = sprites._live                    # per-sprite: decisions only
        index = len(live) - 1
        while index >= 0:                       # downward: despawn-safe
            sprite = live[index]
            sprite.shot_flown += self.speed_y
            if sprite.shot_flown > limit:
                sprite.despawn()
            else:
                other = self.hit.run_one(sprite)
                if other is not None:
                    self.boom.run_one(sprite)
                    self.bang.run_one(sprite)
                    hurt(other, self.damage)
                    sprite.despawn()
            index -= 1
```

**`attached()` is where composition happens.** It runs once at build time and
may allocate. `self.action(...)` registers the Action so the panel and block
editor can find it, and so the same object is reused every tick.

**The loop is split deliberately.** Everything uniform is hoisted into
`action.run(sprites)`; the per-sprite loop carries only branching.

**Cross-behavior wiring resolves at build where it can.** Behaviors attach at
the pool level, so a single target pool has exactly one `Damageable` and
`attached()` holds a direct reference. When the target is a family whose members
carry different `Damageable`s, the lookup happens at hit time through the
sprite's owning pool — a dict lookup, no allocation.

**Each hook takes exactly one callback.** Fan-out would need a subscriber list
built per fire, which is the per-tick allocation the sealed-scene rule exists to
prevent. A game needing fan-out writes it inside its one callback.

### Attaching

`behave()` is a structural call, legal only inside `build()`, returning the
Behavior. Behaviors are named, defaulting to the class name in snake case; a
second of the same class on one subject needs an explicit `name=`. Names are the
path the panel, block editor and control protocol address a parameter by
(`enemies.patrolling.amplitude`), so a collision is a build-time error naming
both. Read them back with `subject.behaviors`,
`subject.behavior("patrolling")` or `subject.behavior(Damageable)`.

`scene` is reserved as the subject name for scene-subject Behaviors, so
`scene.spawner.every` is addressable. A layer, pool or family called `scene` is
a build-time error.

### Subjects

`Sprite`, `SpritePool`, `Family` and `Scene` are all legal subjects, and are not
normalised to a temporary one-element list — that would either fail or allocate
every tick. The run list records the subject kind while the scene is sealed:

- A **pool** invokes `Behavior.step(pool)`, permitting column-wise
  `Action.run(pool)` work followed by a per-sprite loop.
- A **single sprite** invokes `Behavior.step_one(sprite)`, using
  `Action.run_one(sprite)` exclusively.
- A **family** stores its members as a sealed tuple, dispatching each pool to
  `step(pool)` and each singleton to `step_one(sprite)` in declared member
  order, without flattening or creating an iterator in the tick.
- A **scene** invokes `Behavior.step_scene(scene)`. Some conduct has no sprite
  behind it: wave spawning decides *when* something is born, not what an
  existing sprite does. A scene-subject Behavior may not use `run(sprites)` —
  there is no pool to sweep — so it is per-tick work of fixed, tiny size.

Standard behaviors implement every form their subject allows, sharing private
helpers where that does not introduce allocation. A custom behavior may
implement only the form its declared subject needs; attaching it to an
unsupported subject is a build-time error.

### Parameters are the schema

Parameter objects are non-data descriptors holding a default plus metadata.
`__init__` walks the declarations once at construction and writes plain instance
attributes, so `self.speed_y` in the tick is an ordinary attribute read.
Validation happens at construction, inside `build()`:

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
| `Callback(default)` | read-only, shows the bound handler | dropdown over the workspace's event hats |

`Angle` earns its own type because X is angular everywhere in VS2 and "the
bottom of the disc" is not recoverable from the number `0`. The asset-backed
types populate from the game's own ROM and sound folder, which
`web/rom-builder-core.js` already parses.

`Callback` names an **event hat in the workspace**, not a method: a fully
generated project has no hand-written class to pick a method from, and the
generator emits the method from the hat. On a detached file it renders as the
bound method — the same parameter from the other side of `Detach`.

**Durations are ticks in the API and seconds in the editor.** Integer ticks are
the right storage; the editor shows "13 ticks (0.4 s)" beside the slider,
because it knows the 30 ms period. Authoring in seconds and storing ticks would
silently change behaviour whenever the period moved.

### A parameter may be bound to an instance variable

A Behavior attaches at pool level and holds **one** parameter set for every
member, which is what makes column-wise dispatch possible. A parameter may
instead name an instance variable:

```python
self.enemies.var("speed_y", 1.0)
self.enemies.behave(Moving(speed_y=Var("speed_y")))
self.baddies.behave(PathFollowing(points=Var("path")))
```

The binding resolves at build and decides which dispatch tier the Action lands
in:

- a **literal** parameter is hoisted once per tick, runs column-wise, and is
  offloadable to a native kernel;
- a **`Var`-bound** parameter is read per sprite, forces that Action into the
  per-sprite tier, and is not offloadable.

The panel shows one toggle per parameter and marks a var-bound parameter as
per-sprite, so the tier it selects is not hidden.

### Per-instance state

A Behavior needing per-sprite state declares it (`state = ("shot_flown",)`). At
attach time the framework primes every named field to `0` on **every** sprite of
the subject, free ones included:

```text
first assignment of a name, 40 sprites : 1312 bytes  (~33 bytes each)
overwriting a primed name, 40 sprites  :    0 bytes
```

Priming during `build()` is what makes `sprite.shot_flown += ...` in the tick
allocation-free. State names are flat, so access is a plain attribute read —
measured faster than a parallel array indexed by slot (6.2 ms vs 8.9 ms for
2000 ticks x 40 sprites), because MicroPython's `range()` plus subscript costs
more than an attribute lookup.

Flat names mean collisions are possible, so the primer rejects them at build:
two Behaviors on one subject declaring the same name, or a name shadowing a
`Sprite` property or an instance variable, is a `StateConflictError` naming both
sides. The framework reserves `dx`, `dy` (the movement accumulator),
`fsm_state`, `fsm_hold`, `fsm_then` (the state machine and its timed transition)
and `enabled`.

## Variables

### Instance variables

Declared on the pool, with the same parameter types:

```python
self.enemies.var("kind", 0, min=0, max=2)
self.enemies.var("hp", 1, min=0, max=99)
self.enemies.var("angry", False)
```

- Primed on every sprite at build, exactly like behavior state.
- **Reset to their declared defaults by `spawn()`**, so a recycled explosion
  does not inherit the previous one's counter. Behavior state resets the same
  way.
- Editable in the panel as a table on the pool.
- Readable from blocks as a value block, writable as a set block.

`spawn()` gaining a reset loop is the only behavioural change to existing API in
this proposal, and it only affects pools that declared variables.

### Scene and project variables

```python
self.var("score", 0, min=0, max=999999)          # scene: reset every build()
vs2.project.var("high_score", 0, persist=True)   # project: survives a switch()
```

- **Scene variables** are primed on the scene at `build()` and reset there.
- **Project variables** live above the scene stack, so a score survives
  `push`/`pop` and a menu. `persist=True` additionally saves them.

Both appear in the panel as tables, are readable as value blocks and writable as
set blocks, and are addressable over the live-tune protocol alongside behavior
parameters.

### `vs2.store`

A small JSON-able document per game, saved when the game says so.

```python
vs2.store["hiscore"] = max(vs2.store.get("hiscore", 0), self.score)
vs2.store["song"] = self.sonidito.to_dict()
vs2.store.save()
```

`vs2.store` is a dict. It loads on first access and does nothing until then, so
a game that never saves never pays. `save()` is explicit, and returns without
touching flash when the store is clean.

**It is a file, deliberately not NVS.** The NVS partition is 16 kB total and
already holds the POV calibration, the OTA updater's partition-hash state,
retro-go's settings and MicroPython's own keys. A full NVS fails for whatever
writes next, which is as likely to be the calibration as the game: a lost high
score is a shrug, a lost POV calibration is a console that draws crooked.
Critical state and disposable state should not share a 16 kB partition, and the
disposable one is the one with no size bound. The `vfs` partition is 8.75 MB.

**Saves live outside the game directory**, because installing a game removes the
old one first, so anything written inside `/games/<group>/<name>/` is destroyed
the next time that game updates:

```
/saves/<group>.<name>.json
```

named from the app slug, so two games cannot collide, and untouched by both
installer and updater. OTA is per-file against a manifest, so a path the
manifest does not name is never read, written or deleted.

**Failure is always survivable.** A missing directory, a corrupt file, a full
partition: the store falls back to an in-memory dict and the game keeps running.
The store is allowed to fail. That is why it does not share a partition with the
things that are not.

The size cap exists only to catch a game writing per-tick by mistake. The
desktop emulator and browser use the same `/saves/` path against their own
filesystems, so a save works in the editor's preview and the format is identical
everywhere.

`vs2.project.var(..., persist=True)` is sugar over this — read from the store at
project start, written back on `save()`.

### Kinds: per-type defaults as a table

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
`spawn(kind=...)` applies one. The row resolves to an index at build, so
spawning costs the same loop that already resets defaults. In the panel it is a
spreadsheet, one row per enemy type.

## Families

```python
self.hostiles = self.family(self.enemies, self.boss)
self.shots.behave(Projectile(hits=self.hostiles, ...))
```

A `Family` is a build-time object holding an ordered tuple of pools and sprites.
It can be the target of `Collide` and `PoolRef`, and a Behavior can attach to
the family itself, in which case one Behavior instance with one parameter set
covers every member and state is primed across all of them.

**A family is not iterable, deliberately.** Its main job is being the target of
`Collide`, which runs inside a per-sprite loop; one iterator per sprite per tick
would be O(N) allocations for the one construct whose purpose is the O(N x M)
case. It exposes its members as a sealed tuple instead, and traversal is a
two-level indexed walk. That is also what a native `Collide` kernel wants handed
to it.

Families are build-time only and allocate nothing at runtime.

## State machines

```python
class Enemy(StateMachine):
    speed_x = Number(1.25, min=0, max=8, step=0.25)
    speed_y = Number(0.6, min=0, max=8, step=0.25)

    states  = ("descending", "orbiting", "chasing", "exploding")
    initial = "descending"

    def descending(self, sprite):
        sprite.dy -= self.speed_y
        if sprite.y <= GROUND:
            return "exploding"

    def enter_orbiting(self, sprite):
        self.hold(sprite, 128, then="descending")

    def orbiting(self, sprite):
        sprite.dx += self.speed_x * sprite.facing
```

- **States are named**, and the name is what the protocol, the panel and a
  traceback report. `enemies.enemy.state` is readable from the panel while the
  game runs, which is most of a debugger for free.
- **A step method returns the next state, or `None` to stay.**
- **`enter_<state>` and `exit_<state>` are optional hooks**, matched by name.
- **`hold(sprite, ticks, then=...)`** is the timed transition. A temporary
  status — invulnerable, powered up, reversed, slowed — is a state with a hold
  on it.
- **State lives in one primed byte** (`sprite.fsm_state`), and dispatch is a
  tuple of bound methods indexed by that byte: one index and one call, no string
  comparison.

## Named palette colours

Recolouring an index recolours every pixel drawn with it, everywhere, for free,
on a machine with no blending. Revision 2 exposes `vs2.display.palettes` as a
mutable buffer plus `apply_palettes()`; what is missing is naming.

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

Declared beside the art, resolved to an index once at build, and rendered in the
panel as a colour swatch with a picker. A named colour is a parameter type like
any other, so a behavior can take one (`Damageable(flash_color="hurt")`), and
`Flashing(color, ticks)` and `Cycling(colors, ticks)` join the attributes tier.

## The three timings

Three separate timings, each protecting a different visible property.

| Name | What it measures | What it protects | A miss looks like |
|---|---|---|---|
| **Handoff** | On the output-serving core, the time to have a column's colour-corrected LED bytes ready for SPI transfer. Its budget is the time until the next column. | A steady, unbroken image. | An overrun or no remaining slack: the output cannot be served in time. |
| **Paint** | The scene-to-colour-corrected-LED work: projecting and composing sprite data, per column and per rotation. | Visible frame rate and visual complexity. | Paint consumes too much rotation time, reducing the rate at which complete images are produced. |
| **Step** | Game logic, including `scene.update()` and the Behavior pass. Has both a cost and a fixed target cadence. | Fluid, deterministic gameplay. | A late or skipped Step makes motion uneven even if the image is steady. |

**Handoff is the hard deadline** — a per-column deadline that must never be
missed. **Paint** is related but not interchangeable: a buffered Paint
measurement may exceed one Handoff interval without causing an output miss.
**Step** is a scheduling contract: target 33 Hz, then report elapsed time,
achieved rate and missed Steps separately.

Names to use in reviews, profiles and dashboards: `handoff_budget_us`,
`handoff_time_us`, `handoff_slack_us`; `paint_time_us`, `paint_frame_time_us`,
`paint_frames_per_second`; `step_time_us`, `step_rate_hz`, `missed_steps`.

## The Step

1. `scene.update()` — game code, unchanged.
2. If no transition is pending, the Behavior pass, in attach order across the
   whole scene.
3. Back button, idle timeout, timers, transition commit — unchanged.

Behaviors run **after** `update()`, deliberately: a scene with no Behaviors
Steps exactly as today; a sprite spawned in `update()` moves and is
range-checked in the same Step, and at 33 Hz a one-Step lag on a bullet is
visible; and `update()` stays the place where the game overrides a parameter,
taking effect immediately.

*Game code decides, then Behaviors carry it out, in the order they were
attached.* `scene.behaviors` lists them in run order, and so does the panel.

A queued `pop()` or `switch()` is a hard boundary: `scene_step()` skips the
whole pass if `update()` queued one, and stops the pass immediately if a
Behavior queues one.

### What the dispatch shape costs

Measured on MicroPython 1.25, unix port, 600 ticks x 60 live sprites:

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

1. **Uniform work goes column-wise.** `action.run(sprites)` is *faster* than the
   loop it replaces, because hoisting the parameter read is natural in that
   shape and easy to forget by hand.
2. **The Action indirection costs ~42% when dispatched per sprite.** That is the
   price of making the mechanics introspectable, editable and expressible as
   blocks, and it is paid only where a Behavior genuinely branches.
3. **So a Behavior hoists everything uniform and keeps the per-sprite loop for
   decisions.** That hybrid lands within 7% of fully inlined hand-written code
   with every knob visible. It is the shape `Projectile.step()` is written in,
   the shape the catalog is written in, and the shape the block editor makes
   structurally unavoidable.

## The catalog

### Despawn is the off switch

**Despawning is the only way to take a sprite out of a behavior's reach.** A
per-sprite `enabled` check would defeat the entire column-wise tier: a pool
behavior whose first act is a per-sprite branch cannot be hoisted, cannot be a
native kernel, and costs the per-sprite dispatch price for every sprite whether
or not any is disabled — the 65 us/tick row, on work that was 35.

The catalog is arranged so despawn suffices: `Damageable`'s death despawns,
`Transient` and `Lifetime` despawn on expiry, `DespawnBeyond` despawns on exit.
A sprite that must stay visible while inert — a wreck, a stunned enemy — is a
`StateMachine` with an inert state, which pays the branch once, in the one place
that was always going to branch.

This changes how games are written: bookkeeping that keeps dead entities in a
list to decide when a wave is finished has to move to a counter.

### Attributes — built in, tiny, attached from the panel, never forked

| |
|---|
| `Transient(animate, ticks, sound, on_end)` |
| `Animated(first, last, ticks, mode, bank, bank_size, images, frames, duration)` |
| `DespawnBeyond(y_min, y_max, x_min, x_max, on_leave)` |
| `Recycling(x_range, y_range)` |
| `Lifetime(ticks, on_expire)` |
| `Blinking(on_ticks, off_ticks, duration, on_end)` |
| `Pinned(to, offset_x, offset_y)` |
| `Carried(on_board, released_by)` |
| `Shaking(amplitude_x, amplitude_y, ticks)` |
| `Flashing(color, ticks)` |
| `Cycling(colors, ticks)` |

These get attached forty times a project; none is more than a few lines. All
ship in the first release except `Carried`, `Flashing` and `Cycling`, which wait
on named palette colours.

`Animated` carries more than a frame range, because a range does not cover what
games need:

- **`bank` / `bank_size`** — a second frame bank per direction, for art that is
  not mirror-symmetric and where `flip_x` would be wrong.
- **`frames=(...)`** — an explicit sequence, for flickers no
  `first`/`last`/`pingpong` combination produces. `first`/`last` becomes the
  convenience case rather than the model.
- **`duration=`** — the same parameter as `ticks=` seen from the other end, with
  a fractional frame index so speed is continuous rather than an integer divisor
  of the tick. The editor offers both and stores one.
- **`images=(...)`** — an image list resolved once at build, so animating by
  swapping strips cannot build a string on the heap every tick.

`Carried` is a runtime relationship where `Pinned` is a build-time one: it holds
a carrier reference in primed state, so attaching and detaching are reference
writes that allocate nothing.

### Movements — composable, because they accumulate

Movement Actions add into `dx`/`dy` and the framework commits once, so `Moving`
plus `Patrolling` is unremarkable. The exceptions set an absolute position
rather than a velocity: `PathFollowing`, `Laned` and `Pilotable` with `bounds`
each own the field they write, and attaching two of those to one subject is a
build-time error naming both.

| |
|---|
| `Moving(speed_x, speed_y, accel_x, accel_y)` |
| `Patrolling(field, amplitude, period, wave, drift_x, drift_y)` |
| `PathFollowing(points, paths, relative, speed_x, speed_y, loop, then, on_finish)` |
| `Pilotable(player, scheme, speed_x, speed_y, inertia, damping, follow_lag, bounds, fires, fire_button, fire_sound)` |
| `Aiming(player, speed, bounds, fires, fire_button, fire_sound)` |
| `Chasing(target, speed_x, speed_y, turn_rate, give_up_range, on_reach)` |
| `Orbiting(centre_y, speed)` |
| `Laned(centres, speed, on_change)` |

**`Pilotable` is one behavior, not four.** Rim, turn-with-camera-follow-lag,
momentum-with-damping and free eight-way collapse into one parameter set where
zero means "not that one": `inertia=0` is direct control, `follow_lag=0` a fixed
camera. One panel, four presets, and a designer can find the feel *between*
them, which four separate behaviors would make impossible.

**`Aiming` does not collapse into it.** A cartesian stick position clamped to
the unit disc, converted to an angle and depth through `atan2`, `sqrt` and the
inverse projection, is a *crosshair* — you point at a place on the disc rather
than steering a thing around it. It needs the per-layer `to_depth` and `polar`
helpers, which is a second reason it sits beside `Pilotable` rather than inside
it.

### Composed — ship as block programs, meant to be forked

| |
|---|
| `Projectile(speed_x, speed_y, range, damage, hits, burst, sound)` |
| `Damageable(hp, invulnerable_ticks, blink, explosion, score, sound, on_damage, on_death)` |
| `FiringAt(target, projectile, every, jitter, lead, sound, on_fire)` |
| `Spawner(pool, every, count, pattern, schedule, on_spawn)` — subject is the **scene** |
| `Collectible(score, sound, on_pickup)` — second wave |

`Projectile` and `Damageable` ship first, as the two flagship block programs —
the proof that the palette can express what the catalog needs. `Damageable`
exposes `hurt(sprite, amount)` for other behaviors to call.

`Spawner`'s `schedule` is a table: `(duration_seconds, amount, bag)` per wave,
spawns spread evenly across the duration, with a floor that extends a wave if
the count cannot otherwise fit. Types come from a `ShuffleBag` — a Fisher-Yates
bag that reshuffles on exhaustion, so the distribution is controlled rather than
merely random. `ShuffleBag` ships in `vs2` beside the behaviors.

Every Behavior that fires an event takes a `sound=` parameter rather than there
being a sound behavior. `sound=` accepts a tuple as well as a name, picked from
at random, so repetition does not wear through.

### Second wave

`Avoiding(threats, radius, strength)`; `TileBound(tilemap, solid, on_block,
slide)` with `Tilemap.cell_at()` and the `TileUnder` Action; and
`Scrolling(speed_x, speed_y, wrap)`, whose subject is a **`Layer`** — it drives
that layer's camera. It is the smallest Behavior in the catalog, two
accumulations onto two layer fields, and it is the whole of parallax scrolling.

`TileBound`'s `solid` parameter is a `Frames`: the tileset's real tiles drawn as
a strip with checkboxes.

### Deliberately not in the catalog

- **Gravity and a physics solver.** Nothing in the tree integrates a velocity
  under acceleration; a jump arc is a `Tween`, not physics.
- **Pathfinding and line of sight.** No meaningful nav space on a disc.
- **Fade.** The renderer has no alpha. Palette animation is scene-level.
- **Effects.** Shaderless hardware.
- **Behaviors that create drawables.** A Behavior may spawn from an existing
  pool; it may never grow the display graph.
- **`CameraBound`.** A layer camera does it as a layer field, O(1) in the Step,
  rather than an O(N) Python pass writing a derived `x` onto every sprite.

### Budgets

```text
ResourceLimitError: behavior 33/32 in Vixeous (shots: 1, enemies: 4,
  targets: 2, explosions: 1, boss: 2, player: 3); reduce the behavior budget
```

`vs2.limits.behaviors = 32` per scene. Actions are not capped separately — they
are an implementation detail of the Behavior that owns them, reported per
Behavior in the profiling command. Per-instance state and instance variables are
reported, not capped: the cost is `fields x pool count x ~33 bytes`, which for a
full game is under 3 kB and never the thing that runs the board out of memory.

## The block editor

### The palette has five tiers

An Action never decides, so a palette of Actions alone cannot express a game.

1. **Events and conditions** — `when <condition>`, input, collision, timer,
   comparison, "on scene start". This is the tier the no-MicroPython
   requirement rests on.
2. **Expressions** — arithmetic, comparison, `random`, `display.width`, and
   reads of any variable in scope, typed against the parameter system so a
   socket refuses a bad value rather than generating code that fails on the
   board.
3. **Variables** — instance, scene and project, as value and set blocks.
4. **System actions** — scene transitions, label output, music and sound,
   timers, named palette colours.
5. **Actions** — the sprite-mechanics catalog.

Only tier 5 is generated from parameter declarations; the other four are
hand-authored blocks over API that already exists. Each Action is one block, its
parameters are the block's fields rendered from the same declarations the panel
uses, so a new Action appears in palette, panel, protocol and reference docs at
once.

Blockly vendors as `web/vendor/blockly`, lazily loaded the way Monaco is.

### The block tier prevents errors; the Python tier reports them

In blocks, **the error is unreachable**: fields are dropdowns populated from the
live scene and the real asset pack, numeric fields clamp to the declared range,
sockets are typed, and a `PoolRef` cannot name a pool that does not exist. In
MicroPython, the same declarations raise at `build()` with the message naming
the fix. One declaration, two enforcement strategies.

Where prevention cannot reach — a `Points` path that leaves the disc, a spawn
schedule that outruns its pool — the editor warns in place, against the block,
before the project runs.

### The tick skeleton makes the fast shape unavoidable

The top-level block structure has two fixed zones:

```
when ‹Projectile› ticks
├─ apply to all ▸    [ Move      speed_y (8) ]          → action.run(sprites)
└─ for each sprite ▸ [ if  ‹Collide with (hostiles)› ]  → the per-sprite loop
                     [   do  ‹Spawn (explosions)›   ]
                     [       ‹Play sound ("hit")›   ]
                     [       ‹Despawn›              ]
```

Uniform work physically cannot land inside the per-sprite loop, so generated
code is right by construction and the author never learns the rule.

A `StateMachine` gets the same skeleton with one hat block per state:

```
‹Enemy›  initial state: descending
├─ when in ‹descending› ▸ [ Move  speed_y (-0.6) ]
│                         [ if ‹y ≤ (GROUND)› → go to ‹exploding› ]
├─ on enter ‹orbiting›  ▸ [ hold (128) then go to ‹descending› ]
└─ when in ‹orbiting›   ▸ [ Move  speed_x (1.25) x facing ]
```

Each hat generates one method; `go to` generates the return value; `hold`
generates the timed transition.

### Round-trip: one embedded blob and one one-way door

- **Embed the workspace** as a base64+zlib blob in a trailing comment of the
  generated file, so source cannot get separated from output and it survives
  copy, `git mv` and packaging.
- **Banner and body checksum** at the top. If the body no longer matches, the
  editor reports the file as hand-edited and refuses to overwrite silently.
- **Detach** strips the blob; the file becomes ordinary Python forever.
  Explicit, one-way, so nobody is trapped in blocks.

### Debugging generated code

The generator emits block IDs as trailing comments and keeps a line map beside
the workspace blob, so the editor highlights the offending block when a
traceback names a generated line. The director already surfaces scene tracebacks
over comms. This is much harder to retrofit than to build alongside the
generator.

### Two backends: readable by default, fast on request

Generated code is idiomatic MicroPython, so `Detach` is an on-ramp rather than a
trapdoor. A project also carries a **compile for speed** switch whose backend
hoists, inlines and constant-folds the same program.

The invariant that keeps this from doubling the semantics: **the fast backend is
a mechanical transform of the readable one** — hoisting, inlining and constant
folding only, never reordering or restructuring. Equivalence is then structural
rather than something a corpus test has to discover.

### Generator invariants, enforced by tests

- Every generated file compiles with mpy-cross (`tests/run_tests.py:109-126`
  already sweeps every MicroPython source).
- Generating every standard behavior and running 1000 ticks allocates zero
  bytes. In particular the generator never emits `for sprite in pool` inside a
  Behavior.
- Generated code obeys the MicroPython restrictions in `AGENTS.md`.
- Regenerating an unchanged workspace produces a byte-identical file.
- The readable and fast backends produce identical gameplay over the parity
  corpus, and the fast one differs only by the three permitted transforms.

## The live-tune loop

Introspection rides the existing in-band command channel, in the same shape as
`povcal`, `povperf` and `hallfilter`:

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

1. Drag a slider in the panel → `vs2beh set` → the running game changes on the
   next tick, with no restart.
2. The editor marks the value as differing from what is saved.
3. On commit, the editor updates its model and regenerates the scene file.
4. The next full restart runs the committed value.

The panel talks to *a running game*, so the same panel tunes the desktop
emulator, the browser, or the physical spinning console over USB serial — the
only place some of these numbers can honestly be judged, because the disc's
legibility and persistence do not survive a screenshot.

`list` allocates and is called on demand, never per tick. `set` writes one
attribute. Scene and project variables ride the same protocol.

On a detached file the loop still works up to step 2: the panel tunes the
running game and the author copies the number across.

## Ported examples

**Nothing in `games/` is edited by this proposal.** The jam games are historical
artifacts and keep working because revision 2 keeps working, which is an
acceptance check below.

Selected games are **copied and the copies ported**, as `games/alecu/vyruss_vs2`
was ported from `games/alecu/vyruss` and now sits beside it. A port is a worked
example and a proving case: it is where "shorter, and plays identically" is
tested, and where the catalog gets to fail honestly against a real game.

Ports live in **`games/vs2_examples/`**, a group of their own. `games/demos/`
would be cheaper — the launcher folds it into Tech Demos with no tile of its own
— but these are the reference implementations of the API, and someone holding
the console should be able to find them, play them, then read the source that
produced what they just played.

Groups are discovered from the folder tree, so the folder is most of the work.
The rest:

- a group icon spec in `system/menu/images/src/make_menu_icons.py` — the naming
  rule is the folder name with hyphens as underscores, so `vs2_examples.png`;
- one line in the group-to-icon map in `system/launcher/code/__init__.py:63-65`;
- a slug per ported game in `games/registry.py`.

A port replaces hand-written conduct with declarations. A hand-rolled per-sprite
list of movement objects becomes one `PathFollowing` attached to the pool, with
per-instance variation carried by `Var`-bound parameters:

```python
self.baddies.var("path", 0)
self.baddies.var("slot_x", 0)
self.baddies.var("slot_y", 0)
self.baddies.behave(PathFollowing(
    points=Var("path"),
    paths=(((0, -85), (112, 0), (0, -34), (-96, 0), (0, 45)),
           ((0, -85), (-112, 0), (0, -34), (96, 0), (0, 45))),
    relative=True, speed_x=X_SPEED, speed_y=Y_SPEED,
    then=MoveTo(x=Var("slot_x"), y=Var("slot_y")),
    on_finish=self.join_formation))
```

A hand-written kill routine — hide, remove from lists, spawn an explosion, reset
its counter, add score, update the scoreboard, play a sound — becomes:

```python
self.baddies.behave(Damageable(hp=1, explosion=self.explosions,
                               score=15, sound="explosion2",
                               on_death=self.baddie_died))
self.laser.behave(Projectile(speed_y=6, range=LASER_FAR_Y,
                             hits=self.baddies, burst=self.explosions))
```

And a scrolling-world update loop becomes attachments plus one camera write:

```python
self.enemies.var("kind", 0, min=0, max=2)
self.enemies.behave(Moving(speed_y=-ENEMY_SPEED))
self.enemies.behave(Patrolling(field="x", amplitude=64, period=128,
                               wave="triangle"))
self.enemies.behave(Animated(first=0, last=1, ticks=8,
                             bank=Var("kind"), bank_size=2))
self.enemies.behave(DespawnBeyond(y_min=0))

def update(self):
    self.world.camera_x = self.camera_theta   # once, for the whole layer
```

## What has to change under the hood

- **`vs2/params.py`**, new: the parameter types and their introspection.
- **`vs2/actions.py`**, new: `Action` and the vocabulary.
- **`vs2/behaviors.py`**, new: `Behavior`, `StateMachine` and the built-in
  catalog. All must compile with mpy-cross and stay import-cheap — a game that
  never calls `behave()` must not pay for them, so catalogs are lazy-imported
  per class.
- **`vs2/store.py`**, new: the per-game dict over `/saves/<slug>.json`, its
  dirty flag, and its never-raise contract.
- **`vs2/projection.py`**, new: the curve family, `tunnel()`, `VS1_TUNNEL`.
  Pure maths, so the desktop and browser renderers import it too.
- **`vs2/__init__.py`**: `behave()`/`behaviors`/`behavior()` on `Sprite`,
  `SpritePool`, `Family`, `Scene` and (second wave) `Tilemap`;
  `SpritePool.var()`, `SpritePool.kinds()`, the `spawn()` reset and `kind=`
  argument; `Scene.var()` and `vs2.project.var()`; `Scene.family()`;
  `Sprite.despawn()`; the `dx`/`dy` accumulator and its commit pass;
  `Layer.camera_x`/`camera_y`, `Layer.projection` accepting a curve, and
  `Layer.to_depth`/`to_row`/`polar`; the subject-kind-tagged run list built
  during `_seal_drawables()`; the guarded Behavior pass in `scene_step()`;
  `limits.behaviors`; `vs2.DONE`; `Tilemap.cell_at()`. The five reserved bytes
  in the layer payload record carry the camera and curve index, so the wire
  format does not grow.
- **`hardware/rotor/modules/povdisplay/`**: `vs2_layer_t` gains a camera pair
  and a 256-byte curve (2 kB across eight layers); the three
  `mode == 1 ? vs2_project_depth(y) : ...` sites in `gpu.c` become a per-layer
  table lookup; `vs2_native.c` gains the setters. `emulator/` and
  `web/scene-shader-core.js` follow, with the render parity suite as the check.
- **`ventilastation/director.py`**: one `elif cmd == "vs2beh"` next to
  `hallfilter`, delegating to `ventilastation/behavior_control.py`.
- **`web/vendor/blockly`**: vendored, lazily loaded.
- **`web/`**: the block editor pane, the five palette tiers, the custom fields,
  both generator backends, the project and scene editor, the inspector and the
  `vs2beh` client.
- **`tools/`**: a headless generator so CI can regenerate every in-tree
  generated file and assert it is byte-identical.
- **`docs/vs2/`**: tutorial chapters; `reference/behaviors.md` and
  `reference/actions.md` generated from the parameter declarations.
- **`tests/`**: allocation regression, the dispatch benchmark as a guard against
  reintroducing per-sprite dispatch for uniform work, generator determinism,
  backend equivalence, and parity between ported examples and their originals.

## Native Actions

The Action layer is the right boundary for pushing work into C. "An Action never
decides" is the precondition for a kernel running over many sprites at once, and
the two call forms already mark which side of the line each use is on:

- `run(sprites)` — uniform, column-wise, no branching, no callbacks. Can become
  a C kernel.
- `run_one(sprite)` — invoked from inside a per-sprite branch, in the middle of
  Python control flow. Cannot.

A `Var`-bound parameter disqualifies an Action for the same reason.

### The layout has to change first

`vs2_sprite_t` holds `layer`, `image_strip`, `frame`, `mode`, `flags` and 8.8
fixed-point `x`/`y`. But `vs2_native.c` declares

```c
static const vs2_sprite_t* vs2_sprite_records[VS2_MAX_SPRITES];
```

— an array of **pointers** into individually GC-allocated objects, `const`
besides. A kernel would chase pointers rather than stride, and could not write
through them without casting the qualifier away. And C does not know which
sprites are live: liveness exists only in Python's `SpritePool._live`.

Flattening to a real `vs2_sprite_t vs2_records[VS2_MAX_SPRITES]` with objects
carrying an index makes every later kernel possible. `spawn`/`despawn` already
keep `_live` prefix-compact by swapping in the tail, and a pool's sprites already
occupy a contiguous slot range, so a pool can hand C a base slot and a live
count — but that has to become an invariant rather than an accident.

The record still lacks per-sprite behavior state — animation clocks, oscillation
phases, life counters, the `dx`/`dy` accumulator. Note the inversion: the
parallel-array layout measured *slower* than primed Python attributes (8.9 ms vs
6.2 ms), because MicroPython's `range()` plus subscript is expensive. In C it is
the fast layout.

### Surrendering the shadows is the mechanism

`vs2.Sprite` keeps `self._x`/`self._y` as Python shadows and writes through to
the record. If C mutates the record those shadows go stale, so a pool driven by
native Actions drops its shadows and `sprite.x` reads through instead (which
needs getters — only setters exist today).

This is not a wart, it is the part that does the work. The four dispatch shapes
land within ~19% of each other on hardware because they share a floor: `sprite.x`
is a Python property whose setter calls `_fixed_8_8()`, itself a Python
function, then a native method. Moving an Action's arithmetic into C while
leaving that facade in place moves almost nothing.

So the offload unit is **a pool that has surrendered its Python shadows**, and
Actions are how such a pool is addressed. Two consequences to state plainly:
`sprite.x` acquires two cost profiles depending on how its pool was configured;
and a shadow-less pool returns *quantised* 8.8 values where a shadowed one
returns exact floats, which is a game-logic difference.

### Batching: the offload unit is the prologue

Crossing the Python/C boundary has a fixed cost, so the unit that moves is the
**whole run of consecutive column-wise Actions** — the uniform prologue a
Behavior hoists before its per-sprite loop — compiled into one native call per
pool per tick. A Behavior written the other way round has nothing to offload.

### Start with `Collide`

If only one kernel is ever written it should be this one. It is the only O(N x M)
entry in the catalog; everything else is O(N). It **mutates nothing**, so the
shadow problem does not apply and no writeback is needed — sealed ranges in, hit
pairs out. And world-space collision belongs there anyway, since the
un-projection table is already in C.

### Parity across three targets

1. **Native is an optimization, never a semantic.** Every native Action keeps
   its Python `run()` as the reference implementation, and the Python path runs
   wherever no kernel exists.
2. **The reference implementation must do fixed-point arithmetic, not float.** A
   shadow-less pool reads back quantised 8.8 values, and a float reference would
   diverge from the kernel on the second tick of any fractional speed — in game
   logic, not just pixels. Bit-for-bit parity is only achievable if both sides
   round the same way, so the Action layer's arithmetic is 8.8 throughout.
3. **Count the targets: there are three, and only two are compile targets.**
   `color_pipeline.c` and `hall_filter.c` compile into the ESP32 firmware and
   into `libvs2render.so` for the desktop emulator. The browser compiles
   neither — `web/scene-shader-core.js` is a hand-written JS reimplementation
   kept honest by `web/render-parity-test.js`. So a kernel is one C source, one
   JS port and one parity suite. That is the reason to write two kernels that
   matter rather than fifteen that might.
4. **An Action declares its kernel by name** (`native = "move"`), meaning it
   touches only its declared parameters and native record fields. Anything that
   spawns, plays a sound, or calls back into Python is disqualified by
   construction — the same list as "anything that decides".

## Gate: prove the numbers on hardware first

Every desktop measurement above is expected to survive the move to the board
only in its *ratios*. The ratios are the argument: if a column-wise Action pass
is not at least as fast as the loop it replaces, Actions are pure overhead; if
per-sprite dispatch does not cost meaningfully more than inlined arithmetic, the
two-tier split has no performance justification and the two-zone tick skeleton
solves a problem that does not exist; if priming attributes at build does not
make tick writes free, the instance-variable design changes shape.

### The rig

The workbench simulates the hall pulse train, so nothing has to physically spin
and a fixed RPM makes runs comparable. Profiling goes over the workbench's
serial port as in-band text, never through `mpremote` on the DUT — a raw-REPL
entry interrupts the running Python and parks it at a prompt. Normalise to the
same screen before every capture and confirm the `layers`/`sprites` census
matches between runs.

`povperf` supplies the Handoff and Paint sides: treat `deadline_us`,
`avg_total_us`, `max_total_us`, `overruns` and `worst_slack_us` as the Handoff
report; `avg_render_us`/`max_render_us` as per-column Paint; and
`avg_frame_render_us`/`max_frame_render_us`, `frame_deadline_us` and
`frame_overruns` as Paint over a rotation. A rotation deadline is not a Handoff
deadline.

The gate fixture's `avg_us`, `max_us` and `samples` are measured inside
`update()` around the dispatch loop only, so they are **behavior-pass** figures,
not whole-Step figures. The eventual `vs2beh profile` must report the whole Step
too, plus `step_rate_hz` and `missed_steps`, with the behavior pass separately
attributable within it.

### Baseline

Ten distinct behavior kernels on 60 sprites; 30 carry a second behavior, for 90
active behavior slots. Five-second runs at both speeds, across the four dispatch
shapes. Every run had zero Handoff overruns.

| RPM | Handoff budget / worst slack | Paint, average per column | Paint, average per rotation | Behavior pass, average | Observed Step cadence |
|---|---:|---:|---:|---:|---:|
| 600 | 390 us / 142 us | 125–138 us | 32.3–35.4 ms | 16.1–18.7 ms | 34.6–34.8 Hz |
| 700 | 334 us / 83 us | 123–137 us | 31.5–35.4 ms | 15.7–18.3 ms | 34.6–34.8 Hz |

Individual Paint samples reached 598 us at 700 RPM while Handoff still had 87 us
of worst slack and no overruns — expected for a buffered pipeline, and exactly
why Paint and Handoff need separate names and counters. The measured cadence is
an observation of this harness, not an enforced fixed-Step scheduler; the later
game loop must make the 33 Hz contract explicit and count misses.

### How to read it

**The ratios passed.** Column-wise stays at or under hand-written inline, and
per-sprite dispatch is measurably worse.

**The absolutes did not.** Those ten kernels do the cheapest thing a behavior
can do — two adds and a modulo per sprite — and consume **55 to 62% of the 30 ms
Step budget**. Nothing else has run: not `scene.update()`, not the generated
event sheet, not `Collide`, the only O(N x M) entry and absent from this
workload. Per slot that is roughly 180 us to perform two coordinate writes,
far too slow to be arithmetic on a 240 MHz core.

Two observations narrow where the time goes.

**It is not core contention with rendering.** MicroPython is pinned to core 1
and the GPU task and SPI ISR to core 0, since the shipping build does not set
`CONFIG_FREERTOS_UNICORE`. The Step is not waiting behind a rotation.

**It is probably not the dispatch shape either**, since all four shapes cluster
within ~19%. That floor is the `Sprite` facade, and the remaining suspect is the
shared octal-PSRAM bus, with core 1's heap contending against core 0 streaming
the framebuffer. That is cheap to test, and if it is the answer the fix is
memory placement and no kernel needs writing.

### What to measure, at 600 and 700 RPM

| Measurement | Passes if |
|---|---|
| **The same workload with the GPU task idle** | Tells us what fraction of the 16-18 ms is memory contention rather than compute. If Step collapses, the lever is placement — sprite records and behavior working set in internal SRAM |
| **A flattened record table plus `pool.move_all(dx, dy)` as one native call** | Moves 60 sprites for meaningfully less than the 90-slot Python pass costs. Needs no `Action` or `Behavior` code to try |
| The three dispatch shapes, ported as a microbench | Column-wise ≤ hand-written inline; per-sprite dispatch measurably worse — **confirmed at both RPMs** |
| A realistic scene — ten or more behaviors, 60-100 sprites, half carrying a second | Step fits its 30 ms budget with margin and holds cadence; Handoff has no overruns and positive slack; Paint stays within its per-rotation budget — **not yet met** |
| The same scene with a representative generated event sheet in `update()` | Still fits. Not modelled today, and now half of what runs in a Step |
| `Collide` over 20 shots against 40 hostiles, in Python | Establishes the O(N x M) cost the catalog's most expensive entry carries |
| `heap_delta` across 1000+ Steps with the full catalog attached | Zero |
| State-machine dispatch through a tuple of bound methods | Within the per-sprite branch budget |
| `vs2beh set` round trip while the game runs | Visible within one Step, no Handoff misses |
| One Python/C boundary crossing, timed in isolation | Cheap enough that a per-pool prologue call is worth it |

### If it fails

Native Actions first: moving `run()` into C keeps the Action layer, the palette
and the editor intact, and `Collide` alone may close the gap.

Only if that is not enough does the design retreat, in this order: drop
`run_one()` and make every Action column-wise only, pushing state machines back
into hand-written Python; then drop the Action layer entirely and keep Behaviors
as monolithic classes with declared parameters — which preserves the editor, the
protocol and the variable work, and loses only the Blockly palette. The parameter
system, variables, `kinds()`, families, layers and the scene editor do not depend
on the dispatch model and survive either way.

## Rollout

0. **The hardware gate.** A narrow standalone harness: four benchmark kernels
   plus a `scene_step()` timer exposed through `povperf`, with no `Behavior`,
   Action, Blockly or `vs2beh` dependency. **Done, and the ratios passed** — but
   see *How to read it*. Two experiments now belong here because either can
   change everything below: the GPU-idle comparison, and a flattened record
   table with `pool.move_all()` as a single native call.
1. `vs2/params.py` and `vs2/actions.py` with four Actions (`Move`, `MoveTo`,
   `Animate`, `Collide`), including `Var` binding and the `dx`/`dy` accumulator.
2. `Behavior`, `behave()`, the run list, the tick pass, `limits.behaviors`.
   `Projectile` as the worked example, hand-written.
3. Instance variables, `kinds()`, the `spawn()` reset, families, scene and
   project variables, and `vs2.store`.
3b. **Layer cameras and projection curves.** Independent of everything else and
   useful to hand-written games on its own. Camera first — three lines of
   `gpu.c` — then curves, with a Paint measurement before the curve table lands.
4. `StateMachine`, with `hold()`. Port a ten-state hand-rolled machine to it as
   the proving case — if the declared form is not clearly better, stop and
   rethink.
5. The eleven attributes and the eight movements.
6. `vs2beh list` / `set` / `reset` and the director hook. Tune from a serial
   console before any UI exists — if it is not useful at that level, the panel
   will not save it.
7. The inspector panel: generic widgets, the two-level tree, the `kinds` table
   editor, the live-tune loop against a hand-written game.
8. The scene editor and the `build()` generator. Round-trip, checksum, Detach.
   Port a copy of one small game (`mapdemo`) into `games/vs2_examples/`.
9. **The event sheet**: the events, expressions, variables and system tiers, and
   the `update()` generator. This is what the no-MicroPython requirement rests
   on, and none of it depends on the Action work. Prove it by authoring one
   complete small game, with a title screen and a game-over, writing no Python.
10. Blockly for behaviors: the Action palette, tick skeleton, state hats, line
    map, and the fast backend. Re-author `Projectile` and `Damageable` as block
    programs and ship the generated output as the catalog.
11. Port copies of `vyruss_vs2` and `vixeous` into `games/vs2_examples/`. The
    real acceptance test — the originals stay where they are, running unmodified
    beside the ports.
12. Second wave, `Tilemap.cell_at()`, `Angle` and `Points` fields.

Steps 1-7 stand alone and are worth having even if the editor never ships;
nothing before step 8 depends on the editor existing. Step 4 is the one to
reorder if something has to give. Step 9 is the one *not* to defer: it is the
difference between a tuning tool for people who already write MicroPython and an
editor someone can make a game in.

## Acceptance checks

- A scene with the full catalog attached to 100 sprites allocates zero bytes
  across 1000 Steps — verified on the board via `heap_delta`, not only on
  desktop.
- A Behavior's uniform work stays at or under the hand-written loop it replaces;
  its per-sprite branch stays within 50% of inlined arithmetic.
- The ported copies of `vixeous` and `vyruss_vs2` are shorter than their
  originals and play identically at 600 RPM on hardware, compared side by side
  against the untouched originals.
- **No file under `games/` is modified.** A diff touching one is a bug in the
  plan, not a migration.
- Every standard composed behavior is expressible in blocks, and the shipped
  `.py` is the generator's output — not a hand-written file the blocks
  approximate.
- Opening a standard behavior in the editor, duplicating it and changing one
  block produces a working forked behavior without touching `vs2/`.
- Regenerating an unchanged workspace is a no-op diff, and the fast backend
  differs from the readable one only by hoisting, inlining and folding.
- A parameter changed from the panel is visible on the disc within one tick,
  over serial, on the physical console.
- A game hand-written against revision 2 runs unmodified.
- **A complete small game — title screen, one playable scene, game-over, a score
  that survives the transition — is authored end to end with no MicroPython
  written, and runs on the physical console.**
- **`Detach` on that game yields MicroPython its author can read**, and editing
  it by hand and re-running works.
- Every error in the Python tier names the scene, the subject, the Behavior and
  the fix, and is raised during `build()`. Every equivalent error in the block
  tier is unreachable.

## Open for review

- **Should states be a separate `StateMachine` class, or should every Behavior
  be able to declare states?** Making every Behavior a potential state machine
  is fewer concepts; keeping them separate keeps the common stateless Behavior
  cheap to read and explain. This proposal splits them, weakly.
- **Does a `Var`-bound parameter belong in the panel, or only in blocks?** It
  means the panel's "speed" row sometimes shows a number and sometimes the name
  of a column in a different table. The `kinds()` spreadsheet may be the better
  place to surface it.
- **Do Actions need their own segment in the protocol path?**
  `enemies.damageable.blink.on_ticks` is four deep; flattening loses the tree
  the panel and block editor both want.
- **Should instance variables be typed beyond the parameter types?** `Angle` and
  `Frames` are tempting here and may be over-fitting.
- **Should the catalogs ship frozen** in the runtime bundle, or as normal
  importable modules? Frozen imports faster and costs flash for games that never
  use it.
- **What clears `vs2.store`?** Whether uninstalling a game deletes its save,
  whether the settings app offers "clear game data", and whether anything
  garbage-collects saves for games no longer present. An orphan costs a few
  hundred bytes on an 8.75 MB partition, so doing nothing is defensible.
- **When does `Collide` go native?** The Python version ships first and a kernel
  arrives when a real game's profile asks for it. Its shipped semantics must be
  kernel-reproducible from day one — same-layer only, explicit `space`, explicit
  box-or-radius, first-hit rather than all-hits.
