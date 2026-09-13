# VS2 Behaviors: handoff (2026-09-13, updated)

Status snapshot for resuming orchestration of `docs/vs2-behaviors-implementation.md`
on a different machine. Read this before re-reading the plan itself — it tells
you what's already true on disk versus what the plan still describes as future
work.

**This doc was updated 2026-09-13** by a session that had real hardware access
(a workbench + a ventilastation rotor, both USB-attached) — the first time
anything in this whole effort was verified beyond CPython-shim tests and the
`micropython` unix binary. See "Hardware is now available" below before
assuming the earlier "no hardware in this environment" framing still holds.

## TL;DR for a fresh orchestrating session

Waves 1-5 are **done, merged (CI fixed and green), and in PR #158**
(`design/vs2-behaviors ← vs2/wave5-integration`) — it had two real,
previously-unflagged CI failures (a CPython-version-fragile allocation test,
and a missing `pyserial` dependency), both fixed and pushed; check current
review/merge status, it may already be mergeable or merged by the time you
read this. **T15 is done**, merged into `vs2/wave6-integration`. **T16 (a
deliberately minimal first pass, not the full five-tier palette) is done**,
merged into `vs2/wave7-integration`, and — unusually for this effort —
**verified on real physical hardware**, including a bug real hardware caught
that no CPython/unix-`micropython` test could (see "Gotchas" below).
**T17 (full scope, not a minimal pass this time — the user's goal is now
"implement all of the plan" in full) is done in two phases**, merged into
`vs2/wave7-integration` — Phase 1 (generic palette, tick skeleton,
`Projectile`) and Phase 2 (state hats, `StateMachine`, a new `Damageable`
Behavior, a `vasura_espacial`-shaped `StateMachine` proving game). Only
the debugger line-map and the fast backend remain, as an explicit,
undispatched Phase 3. T18 is not started. Two of Waves 1-5's outstanding
hardware-only gaps (T6 paint timing, T11's `vs2beh` over a real serial
link) were closed for real on 2026-09-13; T0's two new hardware
experiments were not (see below) — Wave 6 stays blocked until they are.
Also closed on 2026-09-13, as known Wave 1-5 gaps rather than Wave 7 work:
the RECYCLE state-reset bug (both the generic `state=` case and
`StateMachine`'s `fsm_state`/`fsm_hold`/`fsm_then`), a `vs2beh` write verb
for `kinds()` table cells, and mounting T12's `mountKindsEditor` into the
live panel (verified in a real browser). Everything is pushed to
`origin` — no work exists only on a local disk.

## How this work was done, so you can keep doing it the same way

This entire effort was built by an orchestrating session dispatching parallel
background subagents (the `Agent` tool, `isolation: "worktree"`), one per task
card in `docs/vs2-behaviors-implementation.md`, each in its own git worktree
and branch (`vs2/T<N>-<slug>`). **This held through T15** (whose two
remaining pieces — recover.py+tests and the vixeous port — ran as two
parallel sibling branches since their file scopes never overlapped). **The
user explicitly asked to stop running subagents in parallel starting with
T16**, citing machine load — check whether that constraint still applies on
whatever machine you're running on before parallelizing anything; if it
doesn't, parallel dispatch across genuinely disjoint file scopes (as T15's
two pieces were) is still the faster, previously-proven approach. The
orchestrator, in general:

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
  `tests/test_vs2_hardware_test.py` "no workbench found" flake (CI itself
  never installed `pyserial`, so until that's fixed on your branch this one
  reads as a hard `ModuleNotFoundError` instead — see the PR #158 fix).
  A third, environment-only one can also show up: `tests/test_vixeous_vs2.py`
  failing on `Image.get_flattened_data` if the local Pillow install predates
  the version that added that method (CI's `pip install pillow` always gets
  current, so this is a stale-local-environment artifact, not a real
  failure — confirm by checking `python3 -c "import PIL; print(PIL.__version__)"`
  and/or re-running in a fresh venv). Treat `python3 tests/run_tests.py` as
  clean when only failures from this list appear.
- **MicroPython's `super()` does not walk the runtime MRO the way CPython's
  does.** A zero-argument (and even explicit two-argument) `super().foo()`
  call inside a class declared with *no* base at all (`class Mixin:`) fails
  with `AttributeError: 'super' object has no attribute 'foo'` on real
  MicroPython, even though the exact same code works fine under CPython —
  MicroPython only looks at the class's own declared base(s), not
  `type(self).__mro__`. This bit T16's generated event-sheet mixins
  specifically (see `tools/vs2_event_gen/generator.py`'s module docstring
  for the full story and the reproduction), and will bite **any** future
  generator emitting a cooperative-inheritance mixin the same way T15/T16
  do (`class Foo(TitleSceneEvents, vs2.Scene): ...` composing a generated
  mixin with a hand-written base). **The fix**: give the generated mixin an
  explicit matching base (`class TitleSceneEvents(vs2.Scene):` instead of
  `class TitleSceneEvents:`) — a harmless diamond once combined with the
  hand-written subclass's own `(Mixin, vs2.Scene)` bases, and it makes
  MicroPython's simplified `super()` resolution work correctly on both
  interpreters. **The CPython-shim test suite cannot catch this bug at
  all** — CPython's real MRO-walking `super()` papers right over the exact
  case that breaks on-device. If you're reviewing or writing a generator
  that emits `super()` calls inside a class with no (or a different) base
  than its eventual real parent, check this on real MicroPython
  (`micropython` unix binary is enough, no board needed) before trusting a
  CPython-only test pass.

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
| `vs2/wave5-integration` | Wave 4 + T9a+T9b+T10+T11+T12 merged, plus one orchestrator-authored integration fix, plus (2026-09-13) two CI fixes (see below). Open as **PR #158** against `design/vs2-behaviors` — check its review/merge status before doing anything else. |
| `vs2/T15-scene-editor` | T15, **done**. Two sub-branches (`vs2/T15-recover-tests`, `vs2/T15-vixeous-port`) built in parallel off this one and merged back into it, then this merged into `vs2/wave6-integration`. Kept for history. |
| `vs2/wave6-integration` | `vs2/wave5-integration` + T15 merged. **Head of all completed, hardware-untested work before T16.** |
| `vs2/T16-event-sheet` | T16 (minimal first pass), **done**. Merged into `vs2/wave7-integration`, then a post-merge fix commit landed directly on `wave7-integration` for the `super()` bug real hardware caught (see Gotchas) — that fix was never backported onto this branch itself, `wave7-integration` is the one with the real fix. |
| `vs2/wave7-integration` | `vs2/wave6-integration` + T16 (+ its `super()` fix, the RECYCLE fix, the `vs2beh` kinds write verb, `mountKindsEditor` mounted, its own CSS cache-bust fix) + T17 Phases 1 and 2 (`vs2/T17-blockly-behaviors`, `vs2/T17-phase2-state-hats`, both merged and kept for history) merged. **This is the current head of all completed, tested, and (for T15/T16's proving cases) real-hardware-verified work.** Not yet opened as a PR — do that (against `design/vs2-behaviors`, or against `vs2/wave5-integration`'s PR #158 once that merges) once T18 lands, or sooner if a checkpoint is useful. |

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
  unix binary, never over an actual serial link). **Now that hardware is
  available (see below), both of these are actually doable** — neither was
  attempted in the 2026-09-13 session, which focused on T16, but both would
  be quick wins for a future session with hardware access.
- (2026-09-13) PR #158's CI was **failing**, undetected until a session with
  no other task actually looked: `tests/test_vs2_variables.py`'s zero-
  allocation test hard-coded a warm-up assumption that only holds on
  CPython 3.13+'s tier-2 JIT, and failed deterministically on CI's 3.12 —
  fixed by switching to an O(1)-vs-O(N) growth check (the same pattern
  the very next test in that file already used for an identical hazard).
  CI's "Install tools" step also never installed `pyserial`, so the
  hardware-test suite crashed with `ModuleNotFoundError` instead of
  exercising its intended graceful-failure path — fixed by adding it to
  the install line. Both fixes are small, already pushed to
  `vs2/wave5-integration`, and CI is green now — but it's a reminder to
  actually check CI status rather than trusting "should be fine," even on
  a PR nobody's actively touching.

## Hardware is now available (as of 2026-09-13) — read this before Wave 0/6

A prior version of this doc said Waves 0 and 6 were blocked because no
environment building this effort had ever had physical hardware. **That's no
longer true of at least one environment**: a session on 2026-09-13 had both
boards USB-attached (a `workbench` and a `ventilastation` rotor — both
registered, `python3 tools/find_board.py --list` finds them instantly) and
used them for real, including a full firmware rebuild. Concretely, useful
things a future session should know:

- **The board's firmware can be, and was found to be, stale relative to the
  filesystem.** `hardware/rotor/deploy_micropython_fs.py` only reflashes the
  VFS (filesystem) partition — it does *not* touch the compiled firmware
  (the native C modules, e.g. `vs2_native.c`/`gpu.c`). If the board was last
  firmware-flashed before some native-code wave landed (in this session's
  case, Wave 3b's per-layer camera support), the filesystem's Python source
  calls into a native method that doesn't exist on that firmware and
  crashes — in this exact case, `AttributeError: 'Layer' object has no
  attribute 'set_camera'`, crashing inside the *launcher's own menu code*,
  so badly that the board boot-crash-looped and couldn't reach any game at
  all, T16's or otherwise. **This is not specific to T16** — it would have
  happened with a `vs2/wave1-integration`-vintage filesystem too, since
  Wave 3b's camera work predates all of Waves 4-5/T15/T16. If you flash a
  filesystem and the board won't boot into the menu, suspect this first.
  **The fix**: a full firmware rebuild and flash, `make initial-flash
  PORT=...`, then re-run `deploy_micropython_fs.py` (`initial-flash` wipes
  the filesystem with an empty one). This needs the ESP-IDF v5.5.2
  toolchain (`source /path/to/esp-idf/esp-5.5.2/export.sh`) and the
  MicroPython source cloned at `hardware/rotor/micropython` — see
  `docs/internals/building.md`. **Two setup gotchas hit directly**:
  (1) the clone command in that doc has no version pin at all — clone the
  plain default branch, not the `v1.24.1` tag CI's `.github/workflows/ci.yml`
  uses for the *unix-port* test binary only (that tag's `ports/esp32/boards/`
  layout is missing files the current board config expects; this cost a
  wasted clone-and-rebuild cycle to discover). (2) `export.sh` activates
  its *own* Python virtualenv, which shadows any other venv (including one
  with `esptool`/`littlefs-python`/`pyserial` already installed) for every
  subprocess `make`/`idf.py` spawns afterward — install those three
  packages into ESP-IDF's own env directly
  (`/path/to/.espressif/python_env/idf<ver>_py<ver>_env/bin/python -m pip
  install esptool littlefs-python pyserial`) rather than assuming your
  existing venv is what `make` will actually use.
- **A workbench USB-serial capture gives real visual confirmation without
  Wi-Fi.** `0xD3 capture\n` over the *workbench's* serial port (not the
  rotor's own) returns a CRC32-checked raw APA102 frame snapshot of what
  the rotor is actually driving to its LEDs right now — see
  `docs/internals/vs2-hardware-acceptance.md` and
  `tools/pov_profile_report.py`'s `capture_workbench_frame()`/
  `send_workbench_command()`. Pair it with the `"launch <slug>\n"` in-band
  debug command (`director.py`'s `_dispatch_control`, forwarded transparently
  through the same workbench serial bridge) to boot straight into a specific
  game/scene by `app_loader` slug, and `"povperf status\n"` to read back a
  live `layers=/sprites=/tilemaps=` census of whatever's actually on screen
  — a much more precise way to confirm a scene's structure than eyeballing
  an LED snapshot. `tools/vs2_hardware_report.save_frame_screenshot()` turns
  a captured frame into a polar PNG. **A crash-looping or just-rebooted
  board makes captures look like meaningless random noise** (each capture
  catches a different point in an unstable boot cycle) — if two captures of
  what should be the same stable state differ by a large, similar-magnitude
  pixel count each time, suspect instability before suspecting the capture
  mechanism or the game.

### T0 — partially run (2026-09-13); the two new experiments still aren't

`tools/vs2_behaviors_gate.py --rpms 600 700` was actually run for real on
this hardware (the existing `system/vs2_behavior_gate/` app needs no new
code — it was already on the board's filesystem from the same
`deploy_micropython_fs.py` flash used for T16). Result: **the ratios still
pass**, exit 0, `failures: []` at both RPMs — `column` ≤ `inline`×1.10,
`hybrid` ≤ `inline`×1.25, `per_sprite` measurably slower than `column`,
heap deltas within the allowance, zero overruns, positive slack at both 600
and 700 RPM. Absolute `avg_us` figures were in the 14.5-17.2 ms range,
which is the same order of magnitude as the proposal's own recorded
baseline table (16.1-18.7 ms), not a red flag.

**What's still not done**: the two *new* experiments the plan actually asks
for (GPU-idle comparison, the flattened-record probe) — both need new code
(a way to idle the GPU/rendering task without hanging the display, and a
throwaway native C function), and both are genuine physical-hardware risk
territory (a botched FreeRTOS task-suspend on the wrong task, or bad
timing around the SPI/DMA path, can hang the board in a way that needs a
manual power cycle, not just a clean MicroPython traceback). **Do this as
its own dedicated, careful pass** — grep `hall_init`/the main POV task loop
in `hardware/rotor/modules/povdisplay/povdisplay.c` first to actually
understand whether the rotor's own column-phase computation free-runs off
elapsed time (it looks like it does, from `scaled_phase = (esp_timer_get_time()
- last_turn) * COLUMNS`) or genuinely halts when hall pulses stop, before
assuming the workbench's `rpm 0` ("freezes the column at 0") gives you a
safe, already-built GPU-idle switch for free — that freezing behavior is
documented for the *workbench's own simulated hall output*, not confirmed
here for what the rotor's task does in response. **Wave 6 (T13 native
`Collide`, T14 flat sprite records) remains explicitly gated by the plan on
T0's full verdict** ("Do not start these until T0 reports") — the ratios
passing again is encouraging but is not the written verdict the plan asks
for; don't start Wave 6 on the strength of this alone.

### T6 — real on-console paint timing, captured for the first time (2026-09-13)

T6 shipped "measured host-only, honestly labeled as such." That gap is now
partially closed: `povperf start`/`stop` (`apps/micropython/ventilastation/pov_profiling.py`,
`display.set_performance_profiling(True)`) is a real, already-existing,
zero-new-code native profiling toggle — no need to touch the GPU task or
write anything new to get a real number. Run against `demos.povstress`
("a fixed, reproducible heavy vs2 scene built for profiling") at 600 and
700 RPM: `avg_render_us` 227-228, `max_render_us` 732-735, zero skipped
columns, zero overruns, positive `worst_slack_us` at both RPMs, comfortably
inside the ~334-390us deadline. **This is real, and it's healthy** — but it
is *not* the exact "unchanged within noise" comparison T6's acceptance
line asks for, because there is no genuine pre-camera/pre-curve figure
measured *the same way, on this same hardware* to diff against — T6's own
host-only number is a different measurement context, and getting a valid
"before" would mean checking out a pre-T6 revision and doing a full
firmware+filesystem cycle just to measure it, not attempted here. Treat
this as "paint timing is real and healthy post-camera/curve," not as
"T6's acceptance bullet is now checked off."

### T11 — verified over an actual physical serial link (2026-09-13)

The other outstanding Wave-5 gap: `vs2beh` was "verified via `handle_command()`/
`director._dispatch_control()` directly and under the real MicroPython unix
binary, never over an actual serial link." Now it has been, for real,
against a live `vs2_examples.vixeous` on the physical rotor, over the
workbench's USB-serial bridge: `vs2beh list` (a real JSON census, including
the real `enemies.moving`/`Move` parameter tree), `vs2beh set
enemies.moving.speed_y -3` → `vs2beh_ok enemies.moving.speed_y=-3`, `vs2beh
reset enemies.moving.speed_y` → `vs2beh_ok enemies.moving.speed_y=0`, and a
deliberately bad path (`enemies.nope.bogus`) → `vs2beh_error unknown path
'enemies.nope.bogus'; did you mean 'project.score'?` — the fuzzy-match
suggestion genuinely works too. **T11's hardware gap is now closed**, no
caveats.

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

### T15 — done, merged into `vs2/wave6-integration`

Branch `vs2/T15-scene-editor`, based on `vs2/wave5-integration`. Finished by
splitting the remaining work (recover.py+tests, and the vixeous port) into
two sibling branches built in parallel (their file scopes never overlapped:
`tools/vs2_scene_gen/`+`tests/` vs. `games/vs2_examples/vixeous/`), merged
back into `vs2/T15-scene-editor`, then that into `vs2/wave6-integration`.
Verified: the full `python3 tests/run_tests.py` suite clean, plus the ported
Vixeous actually loaded and played correctly in the browser emulator (`cd
web && python3 -m http.server`, after `python3 tools/generate_roms.py` and
`python3 tools/generate_web_runtime_bundle.py` to pick up the new game) —
terrain, player, enemies, explosions all rendering and animating correctly.

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

All of the above is now **both hand-verified and covered by automated
tests**: `tools/vs2_scene_gen/recover.py` (real-MicroPython payload capture
+ model comparison, `tests/test_vs2_scene_gen_recover.py`), plus
`tests/test_vs2_scene_gen_model.py`/`test_vs2_scene_gen_generator.py`
covering the invariants above. `recover.py`'s image-identity check is a
documented heuristic (same declared image name -> same strip everywhere,
and vice versa) — it cannot prove a specific name, only internal
consistency; a single-occurrence swap of two same-shaped images is
provably invisible to it. Known, accepted, documented in the module's own
docstring, not a gap to silently fix.

**The vixeous port** landed at `games/vs2_examples/vixeous/`, built exactly
per the Behavior-mapping decisions below. A few things that came up while
actually writing it, worth knowing before porting the next game the same
way: **the model file suffix is `.vs2model.json`** (not `.model.json` as
an earlier draft of this doc and `model.py`'s own docstring example
suggested — `regenerate.py`'s actual `MODEL_SUFFIX` is the source of
truth, follow the code over any doc including this one); **`Scene._run_behaviors`
dispatches the whole scene's behaviors first, then does one global
`_commit_pool_motion()` pass** — so a `DespawnBeyond` paired with `Moving`
on the same pool checks a sprite's position *before* that same tick's
`Moving` commit lands, meaning a bound crossed on tick N only actually
despawns on tick N+1, not N (a real, deliberate one-tick-later semantics,
not a bug — write tests expecting it); and **not every pool needs `kinds()`
or per-type behaviors** — vixeous's `targets` pool, for instance, has a
per-tick movement rate that varies with the terrain-scroll cadence, which
no shipped Behavior (a constant-rate `Moving`) can express, so it stayed a
plain declarative pool with fully hand-written movement, same as the
original — don't force a Behavior onto every pool just because the schema
supports one.

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

### T16 — done (deliberately minimal first pass), merged into `vs2/wave7-integration`

The full T16 card describes a five-tier Blockly palette (events/conditions,
expressions, variables, system actions, sprite-Action blocks), a two-zone
tick skeleton, state hats, a debugger line-map, and two codegen backends —
genuinely the largest single task in the whole plan, and the proposal's own
text calls it out as "the one *not* to defer." Building all of that in one
pass was judged too large/risky for one shot, so **the user explicitly chose
a deliberately minimal first pass** instead: a small, bounded vocabulary (2
events, 2 conditions, 3 expressions, 3 system actions — see
`tools/vs2_event_gen/model.py`'s docstring for the exact list), a real (not
mocked) but minimal Blockly panel, and one small original 3-scene proving
game (`games/vs2_examples/event_sheet_demo/`: title screen, playable scene,
game-over, a project-level score surviving the transition — the proposal's
acceptance line, verbatim). Explicitly deferred and **not built**: the full
system-action/expression breadth, sprite/Behavior Action blocks and state
hats (both entirely T17's job), the debugger line-map, and the fast-backend
distinction (only the readable backend exists).

Built: `tools/vs2_event_gen/` (model schema, generator, its own `checksum.py`/
`detach.py` using the `# blocks:` comment prefix `blob.py`'s docstring
already reserved for this, reusing `tools/vs2_scene_gen.blob`'s
`encode_blob`/`decode_blob` directly since those are fully generic), a
vendored Blockly panel in `web/` (`web/vendor/blockly/`, `web/vs2-event-sheet.js`,
wired into `index.html`), and the proving game. Headless tests
(`tests/test_vs2_event_gen.py`, `tests/test_event_sheet_demo.py`) pass, and
the Blockly round-trip was verified for real in a browser (loaded a
hand-authored `.vs2events.json` into the actual panel, confirmed the blocks
it rendered, re-serialized, byte-identical diff).

**Real hardware caught a real bug the CPython-shim tests could not**: the
generated mixin's `super().on_enter()`/`super().update()` calls crashed on
real MicroPython (`AttributeError: 'super' object has no attribute
'on_enter'`) even though the identical code worked fine under CPython —
see the `super()` gotcha above for the full mechanism and the fix (give the
generated mixin an explicit `(vs2.Scene)` base). This was found, fixed,
verified against the real `micropython` unix binary, then verified a second
time on the actual physical rotor (a real `povperf status` census matched
exactly at every scene transition — Title `layers=1 sprites=0 tilemaps=1`,
Playing `layers=1 sprites=0 tilemaps=0`, Game Over `layers=1 sprites=0
tilemaps=2` — plus a workbench LED capture showing legible "PRESS A" and
"GAME OVER" text). The fix is a small, separate commit directly on
`vs2/wave7-integration`, on top of the merge — it was never backported onto
`vs2/T16-event-sheet` itself, so build from `wave7-integration`, not that
branch, if you need this fix.

**Judgment calls made along the way, not re-litigated:**

- `goto_scene`-generated code must copy `_vs_api_slug`/`_vs_declared_api`
  from the source scene onto the freshly-constructed target before
  `self.switch(...)` — `Director._enter_scene` re-establishes the
  "current app" context via `api_guard.begin_app(...)` on *every* scene
  entry including a `switch()`, and `vs2.project` variables are wiped the
  moment that context's slug changes (`_Project._ensure_current_app`). Skip
  this and the score — the entire point of the proving game — silently
  resets to 0 on every transition instead of surviving. Every existing
  game in this repo only ever pushes/switches within one app, so nothing
  hit this until a multi-scene VS2 game (this one) existed.
- `goto_scene`'s `import ... as _scene` line must be lazy (inside the
  method body, not module-level) — a 3-scene cycle (title -> playing ->
  game-over -> title) makes the hand-written scene modules import each
  other in a cycle too, one hop later, and a top-level import deadlocks on
  a partially-initialized module.
- No arithmetic in the expression grammar means no real "increment" —
  faked via successive `on_tick` entries at increasing `timer_elapsed`
  thresholds, each a plain literal `set_variable`, relying on later entries
  in the same generated `update()` overriding earlier ones on the same
  tick. A real, deliberate property of the generator (documented in
  `model.py`), not an oversight.
- Title's "press A to start" is a hand-written escape hatch in a thin
  subclass (`title_scene.py`) — the minimal condition vocabulary has no
  button-press/edge-trigger condition, exactly the kind of gap this
  minimal-pass scope explicitly pre-approved living with, the same spirit
  as T15's `on_build_N()` hooks.
- The user wants `vasura_espacial` used as a `StateMachine` demonstration —
  still not done, still fits best alongside T18's porting work or as an
  alternative to T16's synthetic proving game if a future session revisits
  scope; not forgotten, just not yet placed.

### T17 — done in two phases (2026-09-13), merged into `vs2/wave7-integration`

Built as two sequential phases (same worktree-per-phase, merge-and-verify
pattern as T15). Both are done; the debugger line-map and the "fast
backend" are the only pieces of the original card still not built —
deliberately, a documented Phase 3 that hasn't been dispatched yet.

**Phase 1**: `tools/vs2_behavior_gen/` (model/generator/catalog for a
generic Action/Behavior palette, driven by `vs2.params.introspect()` —
mirrors T12's own "no parameter type special-cased" principle), the
two-zone tick skeleton (enforced by real Blockly connection-check types,
not just generator-side validation), and `Projectile` re-authored as a
block program, proven behaviorally equivalent to the hand-written class.
**Two real bugs found and fixed during review, both worth knowing about
for future phases**: (1) the generated-Projectile behavioral tests only
ran under CPython — the harness used `unittest`/`tempfile`/`importlib`,
none of which exist on MicroPython, so the "verified under real
MicroPython" claim in the original report wasn't actually backed by a
committed, repeatable test. Fixed by adding a plain-assert MicroPython
test file against a checked-in fixture (mirroring
`tests/test_director_headless.py`'s style), plus a CPython-side test
asserting the fixture matches the generator's current output (so it can't
silently drift). **This checked-in-fixture-plus-freshness-check pattern is
now the template for any future generated-code behavioral test that needs
to run on real MicroPython but whose generator/test-harness doesn't.**
(2) `web/styles.css` was edited (new `.vs2behblocks-*` rules) but
`web/index.html`'s `styles.css?v=...` cache-busting query was never
bumped — the whole new Blockly workspace rendered at zero height in a
browser with the old stylesheet cached, real DOM elements present
(confirmed via the accessibility tree) but invisible (confirmed via
`getBoundingClientRect()`). **Any time `web/styles.css` changes, bump its
`?v=` in `index.html`, then actually verify in a real browser** — an
accessibility-tree check alone would have missed this; only a real
rendered screenshot and a `getBoundingClientRect()` check caught it.

**Phase 2**: state hats (a new `state_machine` model shape: `states`/
`initial`/per-state `enter`/`step`/`exit` bodies, two new per-sprite node
kinds `goto_state`/`hold`, plus `set_state`/`call_callback`/`spawn`/
`play_sound` usable in either shape), `StateMachine` added to the
catalog, and **`Damageable`** — a brand-new Behavior designed from
scratch (nothing like it existed anywhere in the codebase; the identically-
named class in `tests/test_vs2_params.py` is an unrelated parameter-shape
test fixture, not a spec to satisfy literally — it's missing a "what
damages this" field entirely, which the real one needed and added). Also:
a small original game, `games/vs2_examples/vasura_states_demo`,
recreating the *shape* of `vasura_espacial`'s real hand-rolled state
machine (`orbiting → chiller_falling → falling → exploding`, with
`hold()`-based timed transitions and a `Collide`-driven interrupt) through
the new state-hat blocks — this is the `StateMachine` demonstration the
user asked for, scoped down from a full port of the 1815-line original
(out of scope; not on T18's port list either) to a small, focused proving
case, the same proportion as T16's own `event_sheet_demo`.
**Deliberately not done**: no Blockly UI for state hats or `Damageable`
(judged out of proportion for this phase, same as T16 shipping without a
panel before one existed) — `Damageable` and the state-hat model shape
are real and tested, just not yet exposed in the browser panel. The
generated `StateMachine` subclass correctly avoids the `super()` gotcha
above by calling `StateMachine.attached(self, subject)` (the unbound-call
form the real class's own docstring explicitly instructs), not
`super().attached(subject)` — verified this is correct by reading the
real class's docstring directly, not assumed.

### T18 — not started

Read its card in `docs/vs2-behaviors-implementation.md` fresh. `vixeous`
already landed as T15's proving case (see above); T18 is now really just
`games/alecu/vyruss_vs2` (a single 477-line file, similar scale and shape
to vixeous — same porting pattern should apply directly) plus the
launcher/registry plumbing (`games/registry.py`'s `GAME_SLUGS`, the
launcher icon-map line) for both ports, which T15 deliberately left for
this task. Does not depend on T17's Blockly work at all — it could have
run in parallel with T17, in hindsight, though it didn't here.

## Suggested immediate next action

Proceed to T18, off `vs2/wave7-integration`. `tools/vs2_scene_gen`
already has everything needed (T15 built it, and it's been exercised once
for real on `vixeous`) — this should be a more mechanical port than either
T15 or T17 needed to be. Consider opening a PR for `vs2/wave7-integration`
(against `design/vs2-behaviors` or against PR #158's branch) as a
checkpoint now that T15-T17 are all done and verified, including on real
hardware for T15/T16.
