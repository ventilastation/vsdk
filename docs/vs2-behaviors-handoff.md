# VS2 Behaviors: handoff (2026-09-12)

Status snapshot for resuming orchestration of `docs/vs2-behaviors-implementation.md`
on a different machine. Read this before re-reading the plan itself — it tells
you what's already true on disk versus what the plan still describes as future
work.

## TL;DR for a fresh orchestrating session

Waves 1-5 are **done, merged, tested, and in PR #158**
(`design/vs2-behaviors ← vs2/wave5-integration`, not yet merged — check its
review status first). Wave 7 is in progress: **T15 is partially built** on
branch `vs2/T15-scene-editor` (generator pipeline solid; recovery tool, tests,
and the actual game port are the next concrete steps, all scoped in detail
below). Waves 0 and 6 are blocked on physical hardware this environment never
had. Everything is pushed to `origin` — no work exists only on a local disk.

## How this work was done, so you can keep doing it the same way

This entire effort was built by an orchestrating session dispatching parallel
background subagents (the `Agent` tool, `isolation: "worktree"`), one per task
card in `docs/vs2-behaviors-implementation.md`, each in its own git worktree
and branch (`vs2/T<N>-<slug>`). The orchestrator:

1. Reads the relevant spec section(s) in `docs/vs2-behaviors-proposal.md` and
   grounds itself in the *current* code (not just the plan's description of
   it, which can lag reality once earlier tasks land) before writing a task
   prompt.
2. Writes a long, self-contained prompt per task: the task card verbatim, the
   relevant spec excerpt, concrete grounding (exact function signatures, line
   numbers, existing patterns to match), explicit file-ownership boundaries,
   and an instruction to report back honestly including gaps and judgment
   calls — not just "done."
3. Launches independent tasks within a wave in parallel (single message,
   multiple `Agent` calls), waits for completion notifications, then merges
   each branch into a `vs2/wave<N>-integration` branch sequentially, resolving
   the inevitable `tests/run_tests.py` list-append conflicts by hand (always a
   trivial union of both sides' new lines).
4. Runs `python3 tests/run_tests.py` after every merge to catch integration
   issues immediately, not at the end.
5. Pushes every task branch and every wave-integration branch to `origin` as
   it goes (see "Every branch, and where it stands" below) — do this too, so
   work is never stranded on one machine.

**Real gotchas hit repeatedly, worth knowing up front:**

- **Session-wide rate limits interrupt subagents mid-task, often.** The
  failure surfaces as a task notification with
  `error type rate_limit, HTTP 429 ... resets <time>`. This is not a real
  failure — nothing is lost (worktree state and git history survive), and the
  fix is `SendMessage` to the same agent ID once the reset time has passed,
  asking it to continue from exactly where it left off. This happened to
  roughly half the tasks in this effort. Don't panic-restart from scratch;
  resume.
- **A stopped-machine sleep looks identical to a dead subagent from the
  orchestrator's side**: hours of wall-clock time pass with zero file
  activity and no notification. Check `find <worktree> -mmin -N` for recent
  file activity before assuming a stuck agent needs to be killed — but if you
  do kill and resume one, nothing is lost either way (worktree state persists
  independent of the killed process).
- **MicroPython does not preserve dict insertion order** (unlike CPython
  3.7+), and does not preserve `**kwargs` capture order at a call site either
  (confirmed directly: `def f(**kw): print(list(kw))` given `f(zebra=1,
  apple=2)` prints `apple` first). Multiple real bugs in this codebase came
  from code that implicitly assumed one or the other. Any new code walking a
  dict for anything user-visible (an ordered UI list, a wire-protocol
  response, ...) needs an explicit order-tracking list built at declaration
  time, or an explicit `sorted()`, never bare dict iteration.
- **Benchmark/timing-threshold tests can be genuinely flaky under CI-style
  load**, not just under real allocation bugs — one MicroPython
  attribute-shadowing benchmark in `tests/test_vs2_params.py` sits right at
  its 1.5x threshold and has flaked at least once in this session with no
  code change. If a benchmark test fails in isolation but the same code
  passed cleanly when it landed, re-run before treating it as a regression.
- **`mpy-cross` is sometimes on PATH, sometimes not**, depending on which
  worktree/session builds it — `tests/run_tests.py` skips that check
  gracefully either way, so don't be alarmed by "SKIP mpy-cross" in some runs
  and a real compile check in others.
- Two **pre-existing, unrelated test failures** show up in every single run
  in every worktree of this repo, present before any of this work started:
  `tests/test_native_exit_transition.py` (the `apps/retro-go` git submodule
  isn't checked out in any of these worktrees) and an intermittent
  `tests/test_vs2_hardware_test.py` "no workbench found" flake. Treat
  `python3 tests/run_tests.py` as clean when only these two appear.

## Every branch, and where it stands

All pushed to `origin` (`git@github.com:ventilastation/vsdk.git`). None of
these have been deleted or force-pushed; they're a clean linear history of
how each wave was built.

| Branch | What it is |
|---|---|
| `design/vs2-behaviors` | Base branch: the spec + plan docs, nothing else. This handoff doc lands here. |
| `vs2/T1-params` … `vs2/T12-inspector-panel` | Individual task branches, Waves 1-5. Landed, superseded by the wave-integration branches below — you shouldn't need these directly, they're kept for history/blame. |
| `vs2/wave1-integration` | T1+T2a+T2b merged. |
| `vs2/wave2-integration` | Wave 1 + T3 merged. |
| `vs2/wave3-integration` | Wave 2 + T4+T5+T6+T7 merged. |
| `vs2/wave4-integration` | Wave 3 + T8 merged. |
| `vs2/wave5-integration` | Wave 4 + T9a+T9b+T10+T11+T12 merged, plus one orchestrator-authored integration fix (see below). **This is the current head of all completed, tested work.** Open as **PR #158** against `design/vs2-behaviors` — check its review/merge status before doing anything else. |
| `vs2/T15-scene-editor` | Wave 7, T15, **in progress**, branched from `vs2/wave5-integration`. Two commits, working tree clean, not yet merged into any integration branch (Wave 7 has no wave-integration branch yet since T15 hasn't landed). See the T15 section below for exactly what's built and what isn't. |

If GitHub's branch list ever looks stale, `git ls-remote --heads origin` is
the ground truth.

## What's actually done (Waves 1-5, PR #158)

Read the PR description on GitHub for the full summary; the short version:

- `vs2/params.py`, `vs2/store.py`, `vs2/projection.py` (parameter schema,
  per-app save file, projection curves).
- Every new attachment point in `vs2/__init__.py`: `Sprite.despawn()`/`dx`/
  `dy`, `SpritePool.var()`/`.kinds()`/`spawn(kind=...)`, `Scene.var()`/
  `.family()`, `vs2.project`, `Layer.camera_x`/`camera_y`/curve-accepting
  `.projection`/`.to_depth`/`.to_row`/`.polar`, `behave()`/`behaviors`/
  `behavior()` on every subject, `Family` (fully implemented, not a stub),
  `Tilemap.cell_at()`.
- `vs2/actions.py` (`Action`, `Move`, `MoveTo`, `Animate`, `Collide`).
- Per-layer cameras and curves wired through `hardware/rotor/modules/
  povdisplay/gpu.c`/`gpu.h`/`vs2_native.c`, the desktop emulator, and
  `web/scene-shader-core.js`.
- `vs2/behaviors.py`: `Behavior` base class, `Projectile` worked example, the
  full catalog (`Transient`, `Animated`, `DespawnBeyond`, `Recycling`,
  `Blinking`, `Pinned`, `Shaking`, plus `Moving`, `Patrolling`,
  `PathFollowing`, `Pilotable`, `Aiming`, `Chasing`, `Orbiting`, `Laned`,
  `ShuffleBag`), and `StateMachine`.
- `apps/micropython/ventilastation/behavior_control.py`: the `vs2beh`
  live-tune serial protocol (`list`/`set`/`reset`), one `elif` in
  `director.py`.
- `web/vs2-widgets.js`, `web/vs2beh-client.js`, `web/vs2-behavior-panel.js`:
  the inspector panel, generic widget dispatch driven by `params.py`'s
  `introspect()`.

**Known, deliberately-open gaps carried forward from Waves 1-5** (not bugs —
documented, scoped follow-ups):

- `Carried`, `Flashing`, `Cycling` (three catalog attributes) are not built —
  the spec says they wait on "named palette colours"
  (`vs2.display.color()`/`__images__.yaml`), and **no task in the entire
  implementation plan builds that prerequisite**. This is a real plan gap,
  not an oversight in Wave 5.
- Behavior `state=` fields are primed once at attach time but not reset when
  a sprite is recycled through a `RECYCLE` pool (same characteristic
  `Projectile`'s own `shot_flown` field already has, per T8's own tests). A
  sprite retired and respawned via `RECYCLE` can carry stale state for one
  cycle. Found by T9a, not fixed (out of that task's file-ownership scope).
- The `vs2beh` protocol has no wire verb for *writing* a `kinds()` table edit
  back to a running game (`set`/`reset` only address scalar parameters), and
  the panel's `mountKindsEditor` (built by T12) is written and tested but not
  yet mounted into the live panel tree. The *read* side (`list` reporting a
  pool's `kinds()` table) was fixed at Wave-5 merge time by the orchestrator
  — see `apps/micropython/ventilastation/behavior_control.py`'s module
  docstring for the exact reasoning (MicroPython `**kwargs` order is not
  recoverable, so rows are sorted by name for determinism instead of
  authored order).
- Hardware-only verification remains outstanding for: true on-console
  paint-per-column timing for the camera/curve renderer changes (T6 measured
  host-only, honestly labeled as such), and physical USB-serial confirmation
  of the `vs2beh` protocol (T11 verified via `handle_command()`/
  `director._dispatch_control()` directly and under the real MicroPython
  unix binary, never over an actual serial link).

## Wave 0 / Wave 6 — blocked, not attempted

T0 (the hardware gate: GPU-idle comparison and a flattened-record probe on
physical rotor hardware) needs a physical ESP32-S3 rotor + workbench this
environment has never had access to. Per the plan's own text, Waves 1-5
explicitly don't depend on it and were correctly built without it. **Wave 6
(T13 native `Collide`, T14 flat sprite records) is explicitly gated by the
plan on T0's verdict** ("Do not start these until T0 reports") — do not start
Wave 6 until someone runs the actual hardware gate experiment
(`tools/vs2_behaviors_gate.py`) on real hardware and records a verdict in the
proposal's "How to read it" section, per the plan.

## Wave 7 — in progress, sequential (not parallel like Waves 1-5)

Unlike Waves 1-6, the dependency graph draws T15→T16→T17→T18 as a flat chain,
not a branching tree — and their cards are much terser than every earlier
task (no `Owns:`/acceptance list at all). Each genuinely depends on the
previous one's generator/file-format conventions, so **do not parallelize
these the way Waves 1-5 were parallelized.**

### Scope call already made, carry it forward

"Scene editor" in T15's name could imply a full interactive drag-and-drop
visual canvas. **That's out of scope, deliberately** — none of the concrete
nouns in the terse card (round-trip blob, checksum, `Detach`, `on_build`
hooks) need one, and it's a much larger, separate frontend effort the plan
doesn't actually specify. What's being built instead, matching
`docs/vs2-behaviors-proposal.md`'s `## Projects, scenes and ownership`
section: a **generator pipeline** — a JSON scene-model schema, in
`tools/vs2_scene_gen/`, that emits a `<Name>Scene.py` file with an embedded
base64+zlib blob, a body checksum, one-way `Detach`, and numbered
`on_build()` hooks. `build()` is provably a flat declarative sequence with no
control flow, so **this generator does not need Blockly at all** — that's
only needed later, for `update()`/tick-logic authoring (T16/T17). Carry this
scoping forward into T16/T17/T18 rather than re-litigating it.

### T15 (in progress) — exactly where it stands

Branch `vs2/T15-scene-editor`, based on `vs2/wave5-integration`, two commits,
clean tree, **pushed to origin**, not merged into anything yet.

The proving case was redirected mid-task, at the user's explicit request,
away from the plan's original suggestion (`mapdemo` — too small, no
Behaviors attached, not representative) to **`games/alecu/vixeous`** — the
spec's own literal worked example in `## Projects, scenes and ownership`,
already using the `vs2` API, substantial enough to actually exercise the
catalog. Two more real games are queued as separate follow-up ports once
T15's generator is proven reusable: **`games/alecu/vyruss_vs2`** (~477
lines, already `vs2` API) and **`games/vsjam-oct25/tincho_vrunner`**
(~732 lines across 5 files, legacy pre-`vs2` API, multi-level). The user also
specifically wants **`games/vsjam-may25/vasura_espacial`** used somewhere as
a demonstration of `StateMachine` against real game logic — it has a genuine
hand-rolled OOP state machine in `vasura_scripts/estado.py`/
`entities/enemigos/enemigo.py` (`on_enter`/`step`/`on_exit` per state class,
remarkably close to `StateMachine`'s own `enter_<state>`/step/`exit_<state>`
convention), a much better real-world proving case than the synthetic
ten-state example T10 wrote for its own tests. **Never edit anything under
`games/`** — every port is a fresh copy into `games/vs2_examples/`.

**Built and solid**, all under `tools/vs2_scene_gen/` (new CPython-only
package; nothing under `apps/micropython/` or `games/` touched):

- `model.py` — the JSON scene-model schema (layers → drawables →
  vars/kinds/behaviors) plus `validate_model()`. Read its module docstring
  first — it explains exactly what the format can't express and why
  (`camera_x`/`camera_y` are a runtime property, not a `build()` arg;
  `persist=` isn't on the real `Scene.var`/`SpritePool.var`), and shows the
  schema mirrors `apps/micropython/ventilastation/behavior_control.py`'s
  `_build_registry` (walks a *built* scene) as a deliberate inverse (this
  describes a scene *to build*).
- `values.py` — renders one model "value" (literal / `{"var": name}` /
  `{"ref": attr}` / `{"handler": name}` / an `{"expr": ...}` escape hatch)
  into Python source.
- `checksum.py` + `blob.py` — the exact generated-file shape: banner, body,
  blank line, trailing `# scene-model: <base64+zlib>` comment (a deliberately
  different comment prefix than a future Blockly `# blocks:` blob, so the
  two can't be confused). `body-sha` is `sha256(body)[:8]`, matching the
  spec's own `8f3a1c02`-style example exactly.
- `generator.py` — model → full file text; `write_scene_file()` returns
  `created`/`updated`/`unchanged`/`hand_edited`/`detached`, never raises for
  those cases. Emits one no-op `on_build_N()` hook method between each
  drawable block (N+1 hooks for N drawables), in layer-then-position order. A
  real `TypeError`-causing bug (emitting `frame=None`/`visible=None` for
  every field the model omitted, because the original code checked
  `dict.get(key) is None` instead of key presence) was found and fixed here
  during manual verification — worth grepping the diff for if anything looks
  subtly wrong later.
- `detach.py` — strips the banner and blob, one-way.
- `regenerate.py` — sweeps `*.vs2model.json` → paired `*.py`;
  `ensure_companion_stub()` implements "a Python stub on creation only,
  never on regeneration" for event-hook references the model names but
  doesn't define — the block-hat half of that same requirement is
  legitimately T17's job, not started.
- `payload.py` — a pure-Python, `PAYLOAD_VERSION`-3-pinned reader for
  `vs2.export_scene_payload()` bytes, ready for the recovery tool below to
  consume.

All of the above was **hand-verified manually** (byte-identical
regeneration, hand-edit detection leaving the file untouched, one-way
`Detach` surviving a subsequent sweep, and a working driver script that
loads a real game headlessly under the `micropython` unix binary and reads
back a parseable `export_scene_payload()`) — but **none of that verification
is committed as an automated test yet.**

**Not yet built — the concrete next steps, in order:**

1. **`tools/vs2_scene_gen/recover.py`** — package the manually-verified
   driver-script pattern (subprocess to `micropython`, `sys.path.insert` of
   `apps/micropython` and `.`, `configure_runtime("headless")`,
   `export_scene_payload()`, hex-encode over stdout) into an actual module/
   function. **Remember**: use `sorted()` over any stripe/asset dict, never
   raw iteration — confirmed directly that MicroPython's dict order is
   hash-based, not insertion-order, unlike CPython.
2. **Tests.** Nothing under `tests/` exists for this package yet. Write
   `tests/test_vs2_scene_gen_*.py` covering every invariant listed as
   "hand-verified" above, register in `CPYTHON_TESTS` in
   `tests/run_tests.py`.
3. **The `vixeous` port itself.** No `games/vs2_examples/` directory exists
   yet. Design work is done (see below) but nothing is written: no model
   JSON, no generated scene file, no companion `update()` file, no copied
   assets.
4. Re-run `python3 tests/run_tests.py`, confirm clean apart from the two
   known pre-existing failures.

**Vixeous port — the Behavior-mapping design decisions already made, with
reasoning, so you don't have to re-derive them:**

- `explosions` pool → `Transient(animate=True, ticks=18)` (frame formula
  verified to match `age//3` exactly). Keep the spawn-time
  `audio.sound("boom")` hand-written — `Transient`'s own `sound=`/`on_end=`
  fire at *expiry*, not spawn, so they're not the same event. Flag in the
  port's own notes: `Transient.state` isn't reset per-`spawn()`, a real risk
  under heavy fire on a `RECYCLE` pool (an upstream framework gap, not
  something to silently work around here).
- `enemies` pool → `var("kind", ...)` + `Moving(speed_y=-ENEMY_SPEED)` +
  `DespawnBeyond(y_min=0)`. **Do not** use `Patrolling` for the theta
  oscillation (vixeous's `phase<64: +2 else -2` is a unipolar ramp,
  `Patrolling`'s triangle wave is bipolar — same amplitude/period numbers,
  visibly different motion) or `Animated(bank=Var("kind"))` for frame
  banking (verified `Animated.bank`/`bank_size` are read as plain literals
  at `attached()` time — a `Var`-bound `bank` raises `TypeError` at build,
  despite the spec's own "Ported examples" section showing exactly this
  combination). Both are genuine spec-vs-shipped-catalog mismatches, not
  mistakes to silently paper over — mention them in the port's own PR/report
  the same way, honestly. Keep enemy theta motion and frame banking
  hand-written.
- `shots`/`bombs` pools → `Moving(speed_y=...)` + `DespawnBeyond(...)` only.
- **No `Damageable` Behavior exists in the shipped catalog at all** (it's
  only in the spec's aspirational illustration, never built by any Wave-5
  task) — hp/score/explosion-on-hit resolution stays hand-written.
  `Projectile` was evaluated and rejected for `shots` specifically: it
  despawns *both* sprites unconditionally on any overlap with no hit-hook,
  which would one-shot every enemy and the 18-hp boss — a real gameplay
  break, not a style preference.
- The `Layer.camera_x`-based rewrite of vixeous's manual `screen_x()`/
  `centered_x()` reprojection is a legitimate simplification the new camera
  API enables, but was deliberately **not** attempted — it needs verifying
  the renderer's exact camera sign convention in `gpu.c` first, which wasn't
  done. Good candidate for a deliberate follow-up, not an oversight.
- The boss stays fully hand-written (a unique one-off entity, not a pool of
  interchangeable sprites — not where the catalog's value is).
- Confirmed by direct inspection: `games/registry.py`'s `GAME_SLUGS` has no
  in-tree reader at all (not even existing ports like `vyruss_vs2`/`vixeous`
  are listed there) and the launcher's `catalog.discover_groups()` is pure
  folder-discovery — a new `games/vs2_examples/vixeous/code/` folder gets a
  tile automatically with zero launcher edits. Leave both alone; full
  registry/icon plumbing is T18's card, not T15's.

### T16, T17, T18 — not started

Read their cards in `docs/vs2-behaviors-implementation.md` fresh; they're
short enough that re-summarizing here would just be a lossy copy. Two things
worth knowing before starting T16 specifically:

- It depends on T15's generator/file-split conventions (`build()` vs.
  `update()` as separate generated-or-handwritten files) landing first,
  which is why it's sequential rather than parallel with T15.
- The user wants `vasura_espacial` used as a `StateMachine` demonstration —
  fold that in wherever it fits best once T16-T18's actual shape is clearer
  (most likely alongside T18's porting work, but T16's "one complete small
  game" acceptance criterion is also a plausible fit if a small
  StateMachine-driven example serves that requirement better than an
  arbitrary synthetic one).

## Suggested immediate next action

Finish T15 to a real done state (recover.py, tests, the vixeous port),
merge it into a new `vs2/wave6-integration`-style branch off
`vs2/wave5-integration` (or whatever `vs2/wave5-integration`'s successor is
once PR #158 merges), push, then proceed to T16.
