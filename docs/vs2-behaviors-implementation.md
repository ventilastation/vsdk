# VS2 Behaviors: implementation plan

Companion to `docs/vs2-behaviors-proposal.md`, which is the specification. This
document is the work breakdown: what to build, in what order, by how many
people or agents at once, and how each piece proves it is done.

The proposal says *what*. This says *who can start now, and what breaks if two
of them start at once*.

## How to use this

- **One task per agent.** Each task below owns a named set of files. Two agents
  must never own the same file in the same wave; where that is unavoidable the
  task is marked **SERIALIZING** and nothing else in its wave runs concurrently.
- **Work in a worktree, branch per task.** Branch name is the task id, e.g.
  `vs2/T4-actions-core`.
- **Read the spec section named in the task**, not the whole proposal.
- **A task is done when its acceptance list passes**, not when the code looks
  right. Every task lands with tests.
- **Do not widen scope.** If a task needs something another task owns, stop and
  say so — that is a dependency the plan got wrong, and it is cheaper to fix
  here than to merge two half-done branches.

## The file that serializes everything

`apps/micropython/vs2/__init__.py` is 1900 lines and nearly every task wants to
touch it. Left alone, that single file turns a parallel plan into a queue of
merge conflicts.

So it is edited **once**, early, by one task (**T3**), which adds every new
attachment point at the same time with minimal or stubbed bodies: `behave()`,
`var()`, `kinds()`, `family()`, the camera and curve properties, the run list,
the Step hook, the new limits. After T3 lands, tasks add their own modules and
touch `__init__.py` only where their card says they may.

Everything in Wave 3 and later depends on T3 for that reason, not for its
behaviour.

## Shared conventions

Every task follows these; they are not repeated on the cards.

**MicroPython.** Code under `apps/micropython/` must compile with mpy-cross —
`tests/run_tests.py` sweeps `apps/micropython/vs2/` automatically, so a new
module there is checked with no registration. No bytearray slice deletion.
Module `__getattr__` works. Descriptors work (the ESP32 build is at
`EXTRA_FEATURES`).

**Zero allocation in a Step.** The rule that catches people: never
`for sprite in pool` inside a Behavior or Action — `SpritePool.__iter__` creates
a `_PoolIterator`. Use an indexed `while` over `pool._live`, walking downward
when the loop can despawn. Handwritten gameplay outside the Behavior pass may
still use `for`.

**Tests register in two places.** Add CPython tests to `CPYTHON_TESTS` in
`tests/run_tests.py`; add a MicroPython-runnable test to `MICROPYTHON_TESTS`.
Follow the header pattern in `tests/test_vs2_api.py` for the `uos`/`utime`
shims.

**Allocation tests are the real check.** The pattern:

```python
gc.collect()
before = gc.mem_free()
for _ in range(1000):
    scene.scene_step()
gc.collect()
assert gc.mem_free() >= before - ALLOWANCE
```

**English everywhere** outside `games/`. Commit per concern, message explains
why.

**Never edit anything under `games/`.** Ports are copies into
`games/vs2_examples/`. A diff touching a jam game fails review.

## Dependency graph

```
W0  T0 gate experiments  ────────────────┐  (blocking: decides T13/T14 scope)
                                         │
W1  T1 params ─┬─ T2a store              │
               │  T2b projection curves  │
               ▼                         │
W2  T3 __init__ surface  SERIALIZING     │
               │                         │
     ┌─────────┼─────────┬───────────┐   │
W3   ▼         ▼         ▼           ▼   │
    T4        T5        T6          T7   │
   actions  variables  layers-C   families
     │         │         │
     └────┬────┴─────────┘
W4        ▼
        T8 behaviors core
          │
     ┌────┼────┬─────────┐
W5   ▼    ▼    ▼         ▼
    T9   T10  T11       T12
   catalog fsm  vs2beh  panel
                                         │
W6  T13 native Collide  ◄────────────────┘
    T14 record flattening
                    (scope set by T0)
W7  T15 scene editor ─ T16 event sheet ─ T17 blockly ─ T18 ports
```

Waves are dependency layers, not calendar. Everything inside a wave runs
concurrently.

---

## Wave 0 — the gate

### T0 · Gate experiments (hardware, blocking)

**Spec:** *Gate: prove the numbers on hardware first*.
**Owns:** `system/vs2_behavior_gate/`, `tools/vs2_behaviors_gate.py`,
`apps/micropython/ventilastation/pov_profiling.py`.
**Needs hardware:** rotor + workbench.

The existing gate confirmed the *ratios*. It did not confirm the absolutes: ten
trivial kernels over 90 behavior slots consume 55–62% of the 30 ms Step budget.
Two experiments decide whether the offload work in Wave 6 is a rescue or an
optimisation.

1. **GPU-idle comparison.** Run the identical gate workload with the GPU task
   idle. Report behavior-pass `avg_us` alongside the existing figure.
2. **Flattened-record probe.** A throwaway native function that walks a
   contiguous `vs2_sprite_t` array adding two fixed-point deltas, called once
   per pool per tick, timed against the 90-slot Python pass. It does not need
   `Action`, `Behavior`, or a real API — it needs a number.

**Acceptance**
- Both figures recorded at 600 and 700 RPM, in the run report JSON.
- A written verdict added to the proposal's *How to read it*: memory placement,
  offload, or both.
- Zero Handoff overruns in every run.

**Verify:** `python3 tools/vs2_behaviors_gate.py --rpms 600 700`

> Nothing in Wave 6 is scoped until this lands. Waves 1–5 do not depend on it
> and start immediately.

---

## Wave 1 — standalone foundations

Three tasks, no shared files, no dependencies. Start all three at once.

### T1 · `vs2/params.py` — the parameter system

**Spec:** *Parameters are the schema*, *A parameter may be bound to an instance
variable*.
**Owns:** `apps/micropython/vs2/params.py`, `tests/test_vs2_params.py`.

The schema every other task reads. Get the contract right; the rest of the plan
assumes it.

- Parameter classes: `Number`, `Angle`, `Flag`, `Choice`, `Frames`, `Sound`,
  `Image`, `PoolRef`, `Points`, `Callback`. Each holds default plus metadata
  (`min`, `max`, `step`, `label`, `unit`, `options`).
- Non-data descriptors. A host class's `__init__` walks declarations once via
  `dir()` and writes plain instance attributes, so a tick read is an ordinary
  attribute load with no descriptor cost.
- `Var("name")` as a binding marker: a parameter value that resolves at build
  to a per-sprite read rather than a literal.
- Validation at construction, with the message naming valid alternatives:
  `TypeError: Damageable has no parameter 'health'; valid: hp, ...`
- Introspection: given a class, yield `(name, type, default, metadata)` — this
  is what the panel, the protocol and the reference docs all consume.

**Acceptance**
- `dir()`-based declaration walking verified on MicroPython, not only CPython.
- Constructing 1000 parameterised objects and reading each attribute 1000 times
  allocates zero bytes after warm-up.
- Reading a declared parameter in a loop is measurably no slower than a plain
  attribute (prove the descriptor is shadowed).
- Every invalid-parameter and out-of-range message names the offender and the
  valid set.
- Registered in both `CPYTHON_TESTS` and `MICROPYTHON_TESTS`.

### T2a · `vs2/store.py` — saved state

**Spec:** *`vs2.store`*.
**Owns:** `apps/micropython/vs2/store.py`, `tests/test_vs2_store.py`.

- Dict-like, lazy-loading on first access, backed by `/saves/<group>.<name>.json`.
- Slug from `api_guard.current_app()`; never a game-chosen filename.
- `save()` is explicit, no-ops when the dirty flag is clear.
- **Never raises.** Missing dir, corrupt JSON, full partition, no filesystem:
  fall back to an in-memory dict and keep going.
- Size cap as a tripwire against per-tick writes; raises only from `save()`.
- Same path on desktop and browser against their own filesystems.

**Acceptance**
- A game that never touches the store performs no filesystem access at all.
- Corrupt file, missing directory and read-only filesystem each leave a working
  in-memory store and a running game.
- `save()` twice with no change writes once.
- Round-trips a nested document (dicts, lists, ints, strings), not just a scalar.
- Writes nothing inside `/games/`.

### T2b · `vs2/projection.py` — projection curves

**Spec:** *Projection curves*.
**Owns:** `apps/micropython/vs2/projection.py`, `tests/test_vs2_projection.py`.

Pure maths, no hardware state, so the desktop and browser renderers import it
too.

- `tunnel(gamma=0.28, near=0, far=53)` builds a 256-entry `bytes` LUT.
- `VS1_TUNNEL` is exactly `tunnel(gamma=0.28)` and must equal the current
  `vs2_deepspace` table **byte for byte**.
- `HUD` is the identity curve; `FULLSCREEN` stays a mode, not a curve.
- Inverse: `to_depth(row)` against a curve, for world-space collision.

**Acceptance**
- `VS1_TUNNEL` byte-identical to `calculate_deepspace()`'s `vs2_deepspace`.
  This is the check that keeps every existing game pixel-identical.
- Every curve in the family is monotonic (the un-projection depends on it).
- `near > far` inverts correctly.
- A curve is 256 bytes.

---

## Wave 2 — the surface

### T3 · `vs2/__init__.py` attachment points — **SERIALIZING**

**Spec:** *What has to change under the hood*.
**Owns:** `apps/micropython/vs2/__init__.py`, `tests/test_vs2_api.py`.
**Depends on:** T1, T2a, T2b.

One task, one commit, every new public surface at once, with minimal bodies.
Nothing else may edit this file during this wave.

- `Sprite.despawn()`; `Sprite` `dx`/`dy` accumulator fields and the commit pass.
- `SpritePool.var()`, `.kinds()`, `spawn()` reset loop and `kind=` argument,
  sealed slot range and live count.
- `Scene.var()`, `Scene.family()`, `vs2.project.var()`, `vs2.store` export.
- `Layer.camera_x`/`camera_y`; `Layer.projection` accepting a curve;
  `Layer.to_depth`/`to_row`/`polar`.
- `behave()` / `behaviors` / `behavior()` on `Sprite`, `SpritePool`, `Family`,
  `Scene`.
- Subject-kind-tagged run list built in `_seal_drawables()`.
- The guarded Behavior pass in `scene_step()`, between `update()` and
  `_run_defaults()`, skipped when a transition is queued.
- `limits.behaviors = 32`; `vs2.DONE`; `Tilemap.cell_at()`.
- Layer payload record: camera X, camera Y, curve index into the five reserved
  bytes.

Bodies may be stubs where a later task fills them (`behave()` may register and
do nothing). Signatures and semantics may not.

**Acceptance**
- Every existing test still passes unchanged — this is the "revision 2 runs
  unmodified" guarantee and it is checked here, not at the end.
- A scene using none of the new API allocates exactly what it did before.
- `export_scene_payload()` output is byte-identical for a scene with no camera
  and a default curve.
- `vs2.limits` census still names layers correctly in `ResourceLimitError`.
- `python3 tests/run_tests.py` clean apart from known-failing hardware tests.

---

## Wave 3 — parallel build-out

Four tasks, disjoint files. T3 must have landed.

### T4 · `vs2/actions.py` — Action base and first four

**Spec:** *Actions*.
**Owns:** `apps/micropython/vs2/actions.py`, `tests/test_vs2_actions.py`.

- `Action` base: `run(sprites)` defaulting to a loop over `run_one(sprite)`.
- `Move`, `MoveTo`, `Animate`, `Collide`.
- `field=` output binding, defaulting per Action, accepting an instance variable.
- Movement Actions write `dx`/`dy`, never `x`/`y` directly.
- `Var`-bound parameters force the per-sprite path.
- `vs2.DONE` results.

**Acceptance**
- `Move.run(pool)` over 60 sprites for 1000 ticks allocates zero bytes.
- Column-wise `run()` is at or under a hand-written inline loop doing the same
  work — the benchmark, kept as a regression guard, is the whole justification
  for the Action layer.
- Per-sprite `run_one()` dispatch is measurably slower than inline, in the same
  direction as desktop. If it is not, say so loudly: it invalidates the two-tier
  split.
- `Collide` is same-layer only; a cross-layer target is a build-time error
  naming both.
- `Collide` tests in world space through the layer's curve, and box-versus-box
  on a HUD layer matches the old `overlaps()` exactly.

### T5 · Variables, kinds, scene and project scopes

**Spec:** *Variables*.
**Owns:** `tests/test_vs2_variables.py`; fills the T3 stubs for `var()`,
`kinds()`, `spawn()` reset.

- Priming at build across every sprite including free ones.
- `spawn()` resets declared variables and behavior state to defaults.
- `kinds()` rows resolved to an index at build; `spawn(kind=...)` applies one.
- Scene and project variables; `persist=True` wired to T2a's store.
- Name-collision detection: `StateConflictError` naming both sides, including
  the reserved names `dx`, `dy`, `fsm_state`, `fsm_hold`, `fsm_then`, `enabled`.

**Acceptance**
- Writing a primed variable in a tick allocates zero bytes; the ~33-bytes-per-
  name cost is paid at build and reported.
- A recycled sprite never inherits the previous occupant's values.
- A `kinds()` row with the wrong arity, or naming an undeclared variable, is a
  build-time error naming both.
- Reserved-name shadowing is rejected.

### T6 · Layer cameras and curves in C

**Spec:** *Layers*.
**Owns:** `hardware/rotor/modules/povdisplay/gpu.c`, `gpu.h`, `vs2_native.c`;
`emulator/native/`; `web/scene-shader-core.js`; `tests/native/`,
`tests/test_emulator_vs2_render.py`, `web/render-parity-test.js`.

The only task in this wave that is mostly C. Independent of the Python work
above and useful on its own.

- `vs2_layer_t` gains camera X, camera Y and a 256-byte curve.
- The three `mode == 1 ? vs2_project_depth(y) : ...` sites become a per-layer
  table lookup.
- Camera folds into `get_source_column()`'s already-modular column arithmetic
  for X, and into the row range for Y.
- `vs2_native.c` setters; the JS renderer follows; parity suite is the check.

**Acceptance**
- A scene with no camera and the default curve renders **byte-identical** to
  today, on all three renderers.
- Paint per column, measured on hardware, is unchanged within noise. If the
  extra indirection costs, that is a finding and it belongs in the proposal.
- Camera X wraps correctly across column 0.
- Existing render parity suites pass unchanged.
- Curves live in `.bss`, not PSRAM.

### T7 · Families

**Spec:** *Families*.
**Owns:** `tests/test_vs2_families.py`; fills the T3 `family()` stub.

- Build-time object over a sealed tuple of pools and sprites.
- **Not iterable.** Two-level indexed traversal instead.
- Legal as a `Collide` target and a `PoolRef` value.
- Behavior attachment to a family primes state across all members.

**Acceptance**
- `Collide` against a family inside a per-sprite loop allocates zero bytes —
  this is the whole reason a family is not iterable.
- Member order is preserved and deterministic.
- A family spanning layers is a build-time error (same-layer collision rule).

---

## Wave 4 — behaviors

### T8 · `vs2/behaviors.py` core

**Spec:** *Behaviors*, *The Step*.
**Owns:** `apps/micropython/vs2/behaviors.py`, `tests/test_vs2_behaviors.py`.
**Depends on:** T4, T5, T7.

- `Behavior` base; `attached()` running once at build and allowed to allocate.
- `step(pool)`, `step_one(sprite)`, `step_scene(scene)`, dispatched by the
  subject kind recorded at seal.
- `self.action(...)` registration.
- Named attachment, `name=` disambiguation, `scene` reserved as a subject name.
- `state = (...)` priming.
- Cross-behavior wiring resolved at build where possible, dict lookup at hit
  time for heterogeneous families.
- `Projectile` as the worked example, hand-written, in the exact hybrid shape
  the spec prescribes.

**Acceptance**
- A scene with the full catalog attached to 100 sprites allocates zero bytes
  across 1000 Steps.
- Hybrid dispatch lands within 25% of fully inlined hand-written code.
- Attaching a behavior to an unsupported subject kind is a build-time error.
- Exceeding `limits.behaviors` raises with the per-subject census.
- A queued `pop()`/`switch()` in `update()` skips the pass; one queued inside a
  Behavior stops it immediately.
- A behavior name collision is a build-time error naming both.

---

## Wave 5 — catalog, machines, tooling

Four tasks, disjoint. All depend on T8.

### T9 · The catalog

**Spec:** *The catalog*.
**Owns:** `apps/micropython/vs2/behaviors.py` catalog section (coordinate with
T10 if both are live), `tests/test_vs2_catalog.py`.

Eleven attributes and eight movements. Split into two agents if wanted:
**T9a** attributes, **T9b** movements — they share no code.

- `Animated` carries `bank`/`bank_size`, `frames=`, `duration=` and `images=`.
- `Pilotable` is one behavior with `inertia`, `damping`, `follow_lag`; `Aiming`
  is separate and uses the layer's `to_depth`/`polar`.
- Movement Actions accumulate; `PathFollowing`, `Laned` and bounded `Pilotable`
  own their field and conflict at build.
- `ShuffleBag` ships beside the behaviors.
- `sound=` accepts a tuple, chosen at random.

**Acceptance**
- Every entry has a test proving it allocates nothing per tick.
- `Animated` reproduces an explicit `frames=` flicker sequence exactly.
- Two absolute-position movements on one subject is a build-time error.
- Attaching thirty attributes across a scene stays inside the Step budget.

### T10 · `StateMachine`

**Spec:** *State machines*.
**Owns:** the `StateMachine` section of `vs2/behaviors.py`,
`tests/test_vs2_statemachine.py`.

- `states`, `initial`, `enter_<state>`/`exit_<state>`, return-next-state.
- `hold(sprite, ticks, then=...)`.
- One primed byte plus a tuple of bound methods indexed by it.
- Proving case: port a ten-state hand-rolled machine.

**Acceptance**
- Dispatch is within the per-sprite branch budget, not worse.
- No string comparison in the tick.
- The ten-state port is legible and shorter than what it replaces. **If it is
  not clearly better, stop and report** — the spec says rethink rather than
  ship.

### T11 · `vs2beh` protocol

**Spec:** *The live-tune loop*.
**Owns:** `apps/micropython/ventilastation/behavior_control.py`, one `elif` in
`director.py`, `tests/test_vs2beh.py`.

- `list`, `set`, `reset`, in the `handle_command(parts, send, scene)` shape
  `povcal`/`povperf`/`hallfilter` already use.
- Scene and project variables alongside behavior parameters.
- Reading and forcing a sprite's state machine state.

**Acceptance**
- `list` allocates only when called; `set` writes one attribute.
- A `set` is visible on the next tick with no restart.
- Works over serial against the physical console, not just headless.
- An unknown path returns an error naming the closest valid one.

### T12 · Inspector panel

**Spec:** *Parameters are the schema*.
**Owns:** `web/` panel files, `?v=` bump.

Generic widgets driven entirely by T1's introspection. Two-level tree, `kinds`
table editor, live-tune against a hand-written game.

**Acceptance**
- No parameter type is special-cased in the panel; adding one to `params.py`
  makes it appear with no panel edit.
- Dragging a slider changes the running game over serial.
- The `kinds` editor round-trips a table without reordering rows.

---

## Wave 6 — offload (scope decided by T0)

Do not start these until T0 reports. If the GPU-idle experiment shows memory
contention dominates, **T14 comes first and T13 may not be needed at all.**

### T13 · Native `Collide`
**Owns:** the kernel source, its JS port, a parity corpus.
Highest-value kernel: only O(N×M) entry, mutates nothing, needs no writeback.
Python reference must do 8.8 fixed-point so parity is bit-exact.

### T14 · Flat record table and shadow-less pools
**Owns:** `vs2_native.c` record layout, `Sprite` getters, per-pool shadow flag.
Flatten `vs2_sprite_records` from pointers to a real array; give `SpritePool` a
sealed slot range and mirrored live count; `pool.move_all()`.

**Acceptance for both**
- Kernel and Python reference agree bit-for-bit over a randomised corpus.
- A game behaves identically in browser, desktop emulator and board.
- Games using no native Actions are unchanged in behaviour and cost.

---

## Wave 7 — the editor

### T15 · Scene editor and `build()` generator
Round-trip blob, body checksum, `Detach`, numbered `on_build` hooks. Port
`mapdemo` into `games/vs2_examples/` end to end.

### T16 · The event sheet — **do not defer this**
Events/conditions, expressions, variables, system actions, and the `update()`
generator. This is what the no-MicroPython requirement rests on and it depends
on none of the Action work.
**Acceptance:** one complete small game — title screen, playable scene,
game-over, a score surviving the transition — authored with **no Python
written**, running on the physical console.

### T17 · Blockly for behaviors
Action palette, two-zone tick skeleton, state hats, line map, fast backend.
Re-author `Projectile` and `Damageable` as block programs; the shipped `.py` is
the generator's output.

### T18 · Ports
Copies of `vyruss_vs2` and `vixeous` into `games/vs2_examples/`, plus the group
icon, the launcher icon-map line, and `games/registry.py` slugs.
**Acceptance:** shorter than the originals, play identically at 600 RPM,
compared side by side against untouched originals. No file under `games/`
outside `vs2_examples/` is modified.

---

## What to escalate rather than solve

- **A benchmark that contradicts the spec.** If column-wise is not at least as
  fast as inline, or per-sprite dispatch is not measurably worse, the two-tier
  design loses its justification. Report it; do not tune the benchmark until it
  agrees.
- **A catalog entry that cannot be expressed in blocks.** The spec says that
  means the palette is wrong, not the entry.
- **Needing to edit a file another task owns.** A dependency the plan missed.
- **Wanting to touch a jam game.** Always a copy into `games/vs2_examples/`.
