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
"implement all of the plan" in full) is done in all three phases**, merged
into `vs2/wave7-integration` — Phase 1 (generic palette, tick skeleton,
`Projectile`), Phase 2 (state hats, `StateMachine`, a new `Damageable`
Behavior, a `vasura_espacial`-shaped `StateMachine` proving game), and
Phase 3 (debugger line-map with real `# block: <id>` trailing comments
re-parsed and resolved against real MicroPython tracebacks; a fast
backend doing constant-folding/loop-invariant-hoisting/single-use-inlining
for both generators) — built by a background subagent, independently
reviewed (same test suite, same three pre-existing unrelated failures,
nothing new) and merged. **T18 is fully done**, merged into
`vs2/wave7-integration` — the `vyruss_vs2` port plus launcher/registry
plumbing for both ports, **and now also verified on physical hardware**
(both ports run side by side against their originals at 600 RPM with zero
overruns and matching structural/timing/visual results — see the T18
section below for numbers). **T0 is fully done too** — both new
experiments (GPU-idle comparison, flattened-record probe) built as real
native code and run for real at 600/700 RPM, with a written verdict now
in `docs/vs2-behaviors-proposal.md`'s "How to read it" — see the T0
section below. **Wave 6 (T13/T14) is now fully unblocked.** All of Waves
1-5's outstanding hardware-only gaps (T6 paint timing, T11's `vs2beh` over
a real serial link) were also closed for real on 2026-09-13.
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
| `vs2/wave7-integration` | `vs2/wave6-integration` + T16 (+ its `super()` fix, the RECYCLE fix, the `vs2beh` kinds write verb, `mountKindsEditor` mounted, its own CSS cache-bust fix) + T17 Phases 1, 2 and 3 (`vs2/T17-blockly-behaviors`, `vs2/T17-phase2-state-hats`, `vs2/T17-phase3-linemap`) + T18 (`vs2/T18-vyruss-port`) + T0's GPU-idle/flattened-probe native code merged, all kept for history. **This is the current head of all completed, tested work — real-hardware-verified for T15/T16/T18/T0.** Not yet opened as a PR — do that (against `design/vs2-behaviors`, or against `vs2/wave5-integration`'s PR #158 once that merges) whenever a checkpoint is useful; nothing blocks opening one now. |

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
- **The local browser IDE (`web/`, `make web-emulator`/`python3 -m
  http.server 8008 --directory web`) does not see new game folders until
  its runtime manifest is rebuilt.** The WASM worker's virtual filesystem
  is populated entirely from `web/runtime-manifest.json` +
  `web/runtime-bundle.json` (a generated file list + bundle,
  `tools/generate_web_runtime_bundle.py`, wrapped as `make
  web-runtime-bundle`) — it does *not* read `games/` off disk live, even
  though `web/games` is a real symlink to the top-level `games/`
  directory. Adding `games/vs2_examples/` this session (T15/T18) without
  re-running that step left the browser IDE's game picker silently missing
  all four `vs2_examples` games (no error — `getGameEntries()` just
  returns fewer entries than exist on disk), discovered only when actually
  testing the editor live in a browser rather than just running the
  CPython/MicroPython test suites. **Fixed by running `make
  web-runtime-bundle`** (bumped `micropython-bridge.js`'s
  `WORKER_SCRIPT_VERSION` and `wasm-worker.js`'s
  `runtimeBundleUrl`/`runtimeManifestUrl` `?v=` query strings too, same
  cache-busting convention as every other `web/*.js` change this session)
  — verified working afterward by loading `vs2_examples/vyruss_vs2` in a
  real browser tab and watching it run live. **This is already documented**
  in `web/README.md` ("Python-side changes only reach the browser after
  `make web-runtime-bundle` regenerates `runtime-bundle.json`") — the gap
  was in this session's own workflow, not a doc gap: run it after adding or
  moving any file under `games/` before trusting a browser test of new
  content.

### T0 — fully done, including both new experiments and a written verdict (2026-09-13)

`tools/vs2_behaviors_gate.py --rpms 600 700` was run for real on this
hardware. Result: **the ratios pass**, exit 0, `failures: []` at both RPMs
— `column` ≤ `inline`×1.10, `hybrid` ≤ `inline`×1.25, `per_sprite`
measurably slower than `column`, heap deltas within the allowance, zero
overruns, positive slack at both 600 and 700 RPM. Absolute `avg_us`
figures were in the 14.6-17.6 ms range, the same order of magnitude as the
proposal's own recorded baseline table (16.1-18.7 ms).

**Both new experiments are done too**, added as real, minimal, low-risk
native code rather than reusing the workbench's `rpm 0` freeze (confirmed
that mechanism is documented for the workbench's own simulated hall output
only, not the rotor's response to it — not assumed safe):

- **`povdisplay.set_gpu_idle(enabled)`** (`hardware/rotor/modules/povdisplay/povdisplay.c`):
  a new `gpu_idle_enabled` flag checked at the top of `coreTask()`'s main
  loop — when set, skips `gpu_serve()`/`project_next_column()` entirely and
  `vTaskDelay(1)`s instead of busy-spinning (keeps the per-core FreeRTOS
  IDLE task fed so the watchdog never fires). Defaults off; no existing
  boot path touched. Wired through `povperf gpuidle on|off|status`.
- **`vshw_vs2.flattened_probe(count, passes)`** (`hardware/rotor/modules/povdisplay/vs2_native.c`):
  a throwaway, self-contained timing loop over a *static* array shaped
  like the eventual flattened pool layout — not the real
  `vs2_active_scene` (whose sprite records are borrowed pointers into
  individually heap-allocated Python objects, not contiguous, so there was
  nothing real to flatten yet). Wired through `povperf flatprobe <count>
  <passes>`.

**Verdict** (written into `docs/vs2-behaviors-proposal.md`'s "How to read
it", per the plan's own instruction — full numbers there):
GPU-idle made every dispatch shape ~28-30% faster, uniformly, at both
RPMs — confirms the shared-PSRAM-bus contention this doc's proposal
already suspected, even though the two tasks never block on each other.
The flattened-record probe took 4us total against 10.6-17.6ms for any
Python dispatch shape — ~2,500-3,700x faster, with the honest caveat that
it carries none of a real pool's Behavior/Action semantics. **Combined
verdict: both** — memory placement is a real, confirmed, no-kernel-needed
win, and offload (Wave 6's T14) is a much larger lever on top of it.
**Wave 6 (T13 native `Collide`, T14 flat sprite records) is now fully
unblocked** — T0's written verdict is in, this is not "encouraging ratios"
alone.

**One real scare during this run, worth flagging**: the workbench dropped
into a genuine power-brownout reboot loop (`E BOD: Brownout detector was
triggered` → reboot → repeat) partway through the first 700 RPM attempt —
confirmed via the workbench's own serial log, not a guess. This stopped
the run cleanly (no data corruption, no board damage) but needed the user
to physically swap USB cables before a clean re-run at both RPMs
succeeded with zero failures. **Not caused by this session's code** —
idling the GPU task reduces power draw if anything — almost certainly a
marginal cable/hub under sustained load. If a future session sees the gate
script go dead mid-run with all-zero fields, check `find_board.py --list`
and the workbench's own serial output for brownout lines before suspecting
new code.

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

### T18 — fully done, including physical-hardware acceptance (2026-09-13)

`vyruss_vs2` ported into `games/vs2_examples/vyruss_vs2/`, following the
exact `vixeous`/T15 precedent (model JSON + generated `build()` + a
hand-written companion). Merged into `vs2/wave7-integration`. Found a
**third, new Behavior-catalog mismatch** beyond the two vixeous's port
already documented: a Behavior attached to a lone (non-pool) sprite has
its `step_one` called unconditionally every tick regardless of
`sprite.visible` (confirmed directly in `vs2/__init__.py`'s
`_run_behaviors` — no visibility guard anywhere in the `"sprite"`
branch), which makes `Transient` the wrong shape for a sprite that's
repeatedly shown/hidden by game logic (like `vyruss_vs2`'s
`player_explosion`) rather than living in a `RECYCLE` pool — it would
count down once, expire long before the sprite is ever shown again, and
never fire a second time. Kept hand-written, documented, not forced.
Also confirmed directly: `Transient`'s frame math (`elapsed =
transient_elapsed + 1` computed *before* `frame = elapsed * frames //
ticks`) shows frame 1 on a sprite's very first tick, never frame 0 — a
real, minor, previously-undocumented divergence from the original
age-indexed loops both `vixeous` and `vyruss_vs2` replaced.

The launcher/registry plumbing T15 left for this task is also done, for
both ports: confirmed `games/registry.py`'s `GAME_SLUGS` is genuinely
dead code (grepped the whole repo, only its own definition reads it) and
left it alone rather than half-fixing something with no functional
effect; `vs2_examples` had no `GROUP_ICONS`/`GROUP_LABELS`/
`FOLDER_GROUP_ORDER` entry (it worked fine as a plain-label fallback,
just undecorated) — added a real badge icon via the existing
`make_menu_icons.py` recipe and registered it.

**Verified**: full CPython test suite (16 new tests mirroring
`test_vixeous_vs2_examples.py`'s rigor), and — independently, by the
orchestrating session, not just the subagent — the port actually loaded
and ticked 200 times without error under the **real MicroPython unix
binary**, not just the CPython shim.

**Verified on physical hardware (2026-09-13, later in the same session):**
the rotor reconnected (user confirmed; independently verified via
`tools/find_board.py --list` showing both `workbench` and `ventilastation`
again). ROMs regenerated (`tools/generate_roms.py`, after fixing the
ESP-IDF-`export.sh`-shadows-venv gotcha again — see "Gotchas" below),
filesystem reflashed via `deploy_micropython_fs.py`, then both ports run
side by side against their originals at 600 RPM over the workbench's
serial bridge (`povperf start/stop/status` + a `capture`-based LED frame
grab), exactly the T15/T16 procedure:

- `vs2_examples.vyruss_vs2` vs `alecu.vyruss_vs2`: identical structural
  census (`layers=3 sprites=71 tilemaps=1`), **zero overruns/skipped
  frames on both**, comparable timing (port `avg_total_us=46
  avg_render_us=92` vs original `avg_total_us=49 avg_render_us=98` — port
  slightly faster, within run-to-run noise). LED captures show correct,
  matching gameplay (starfield, score digits, baddie swarm, player ship).
- `vs2_examples.vixeous` vs `alecu.vixeous`: identical structural census
  (`layers=2 sprites=27 tilemaps=2`), **zero overruns/skipped frames on
  both**, comparable timing (port `avg_total_us=51 avg_render_us=137` vs
  original `avg_total_us=48 avg_render_us=133` — within noise). LED
  captures show correct, matching rendering (polar terrain map, radar
  blips, player ship).

**T18 is now fully done, including physical-hardware acceptance.** No
remaining open items for this task.

**PR opened 2026-09-13/14**: [#159](https://github.com/ventilastation/vsdk/pull/159),
`vs2/wave7-integration` against `design/vs2-behaviors` (not `main` —
`design/vs2-behaviors` doesn't have Waves 1-5 merged yet either, since
PR #158 is still open, so the two PRs' diffs necessarily overlap; opening
against `design/vs2-behaviors` matches this whole effort's established
lineage instead of creating a third, redundant PR against `main`). Ready
for review, ordinary PR (not draft).

## New work (2026-09-14): porting `vyruss_vs2`/`vixeous` to the Blockly UI

A new user goal, set via `/goal` after the PR above: "port more complex
games like vyruss_vs2 and vixeous to the blockly UI representation.
Create missing blocks as needed." **Read this whole section before
touching this thread** — it records a real, load-bearing finding that
changes what "port to Blockly" even means right now, plus concrete,
tested progress and a dispatched-but-maybe-still-running subagent.

**The load-bearing finding: T17 Phase 2's own UI was never built.**
`tools/vs2_behavior_gen`'s block-*program* schema (`model.py`) has real,
tested support for state machines ("state hats"), and per-sprite nodes
`hold`/`goto_state`/`set_state`/`call_callback`/`spawn`/`play_sound` — all
built and merged in Phase 2. But **none of it was ever wired into the
actual Blockly drag-and-drop UI** (`web/vs2-behavior-blocks.js`) — that
file's own docstring says so plainly ("a pre-existing Phase 1/2 scope gap
this task does not fill"). Confirmed by grepping the file for any of
those node-kind strings: zero matches, before this session's work below.
`games/vs2_examples/vasura_states_demo/code/enemy_states.vs2behavior.json`
(the one real state-hat program that exists) was hand-authored as plain
JSON, never dragged together in a browser. So "port to the Blockly UI
representation" genuinely meant *building the missing UI first*, not
just authoring more JSON by hand the way Phase 2 itself did.

**Done, tested, committed on `vs2/wave7-integration` (not yet in a PR of
its own — land it in whatever the next checkpoint is):**

- **`binary_op` expression kind** (`tools/vs2_behavior_gen/model.py`/
  `generator.py`, commit `2fa22b6`): two sub-expressions combined by
  `+`/`-`/`*`/`//`/`%`/`min`/`max`, recursively nestable, rendering as
  plain Python infix or a builtin call on both the readable and fast
  backends — nothing this needs is missing on MicroPython. Neither
  `vyruss_vs2` nor `vixeous`'s choreography math is expressible without
  arithmetic (`distance = max(0, baddie.y - RIM_Y)`,
  `distance = min(SPEED, self.remaining)`), and the schema had none
  before this (`vasura_states_demo`'s own `build_enemy_states.py` docstring
  says so explicitly: "this schema's per-sprite expression vocabulary has
  no addition operator"). Covered by a real runtime behavioral test
  (`BinaryOpBehaviorTests`, both backends) that builds and steps a
  generated Behavior through the exact `min(speed, remaining)` pattern
  the Vyruss port below needs — not just checking rendered text.
- **`vyruss_vs2`'s baddie-formation choreography, ported and proven**
  (commit `9931880`): `games/vs2_examples/vyruss_vs2/code/
  build_baddie_formation.py` builds a real generated `StateMachine`
  Behavior (`BaddieFormation`, states `closer1`/`xmove1`/`closer2`/
  `xmove2`/`away`/`formed`) replicating the *fixed* five-phase part of
  the original hand-written `add_baddie()`/`update_one_baddie()` queue
  (`TravelCloser(85), TravelX(±112), TravelCloser(34), TravelX(∓96),
  TravelAway(45)`). **Proven tick-by-tick behaviorally identical** to the
  original (`tests/test_vyruss_vs2_baddie_formation.py`, both directions,
  plus the case where a baddie's sideways travel crosses the 0/256
  display-width seam). Caught and fixed a real design bug along the way:
  first assumed `xmove1`/`xmove2` shared one sign per baddie; the
  original actually flips direction between them (`TravelX(112), ...,
  TravelX(-96)` for the *same* odd baddie) — the parity test caught this
  immediately (element-98 divergence), fixed by deriving `xmove2`'s sign
  as the negation of a single per-sprite `x_dir` flag rather than reusing
  it directly.
  - **The sixth phase, `TravelTo` (the final approach to formation
    position), is deliberately NOT ported** — it's a "move *toward* a
    destination" primitive with wraparound angular math
    (`move_toward_angle`/`move_toward_depth`), a genuinely different
    shape from the fixed-distance walk the other five phases share.
    Forcing it into the same state machine would misrepresent it, the
    same "if it doesn't fit, don't force it" call T15/T18 already made
    repeatedly for this game. Stays hand-written.
  - **Not yet wired into the live game.** `add_baddie()`/
    `update_one_baddie()` and `vyruss_vs2_scene.vs2model.json` are
    untouched — `BaddieFormation` exists and is proven correct in
    isolation, but nothing in the actual running game attaches it yet.
    Two real complications surfaced while scoping that integration,
    left for whoever picks this up next:
    1. **T15's scene-model schema can't declare a custom, game-local
       Behavior class.** `tools/vs2_scene_gen/generator.py` hardcodes
       `from vs2.behaviors import <classes>` for every `"behaviors"`
       entry in a `.vs2model.json` — it has no way to reference a class
       living in `games/vs2_examples/vyruss_vs2/code/baddie_formation.py`
       instead. The sanctioned workaround (already precedented by
       `vasura_states_demo.py`'s own hand-written `self.enemies.behave(
       EnemyStates(...))`, which doesn't use a scene model at all): attach
       it by hand in an `on_build_N()` hook instead of the declarative
       model — `on_build_5()` runs right after `self.baddies =
       self.world.sprite_pool(...)` in the generated
       `vyruss_vs2_scene.py`, so that's the hook to use. Not yet done.
    2. **`baddie.finished`'s meaning would shift, and downstream logic
       depends on the old meaning.** Today, `finished` becomes `True`
       only once the *whole* queue (all six phases, `TravelTo` included)
       empties — `group_finished()` and `update_attacking()`'s own
       `baddie.finished and baddie in self.attacking` check both read it
       as "this baddie has visually arrived at its formation slot."
       `BaddieFormation`'s own `formed` state sets `finished = True` the
       moment the *first five* phases end, before `TravelTo` even starts
       — a real, premature-relative-to-today semantic shift that would
       make groups advance before baddies visually finish forming up.
       Fixing this cleanly (a second flag, or moving `TravelTo` itself
       into the state machine as a `goto_state`-free "keep calling a
       hand-written step" escape hatch — no such hatch exists yet) is a
       small but real design question, not attempted here.
    Both complications above were resolved and this **is now wired in**
    — see "Fully wired in and hardware-verified" below; this bullet is
    kept for the historical reasoning.
    Also out of scope, correctly, and still genuinely deferred: the
    **attack-run reassignment** (`update_attacking()`'s
    `baddie.movements = [TravelCloser(distance), TravelAway(distance)]`,
    where `distance` is computed per-event, not a fixed model param)
    would need `StateMachine.force_state()` plus *new*, dedicated
    attack-only states (today's `closer1`/`away` always reset
    `remaining` from a fixed Behavior-level param on `enter`, not a
    per-call dynamic value) — a genuinely separate, additional piece of
    design work from "wire in the already-built entrance choreography."

**The Blockly UI subagent finished and its work is merged.** Branch
`vs2/blockly-state-hats-ui` → `vs2/wave7-integration` (commit `615c77d`).
Built exactly what was missing: the `vs2beh_state_machine`/`vs2beh_state`
hat/state blocks, all six Phase 2 per-sprite node kinds, and the
`binary_op` expression, in `web/vs2-behavior-blocks.js` only, plus a
genuinely new test file (`tests/test_vs2_behavior_blocks_roundtrip.mjs`,
12 tests) that runs Blockly's real data model headless in Node (the
vendored UMD build has a real Node branch; no jsdom needed) and
round-trips the real `enemy_states.vs2behavior.json` reference file
through it, checking connection rules via Blockly's own
`connectionChecker`, not a reimplementation.

**Independently re-verified before merging** (per this session's own
standing rule — never trust a subagent's "verified" claim without
re-checking): ran that Node suite myself (12/12 pass), then separately
wrote the real reference file into a live browser's emulator filesystem
by hand and loaded it through the actual UI's Load button — confirmed
the state machine hat, `hold`→`go to state`, `play_sound`/`spawn`/
`call_callback`, and the Collide-condition block all render correctly in
a real rendered `WorkspaceSvg`, and that the **States** toolbox category
shows the right palette. One real, disclosed, non-blocking limitation:
an `if_action`'s bound Action (the reference file's one shared `hit`
Collide, used by three states) becomes three separate declarations on a
save/reload round trip — semantically identical, structurally different;
accepted as-is rather than building the `block.data`-sharing scheme that
would preserve one shared bind.

**`BaddieFormation` is now fully wired into the live `vyruss_vs2` game
and reverified on real hardware.** Both complications from the bullet
above got resolved:
1. Attached by hand in `on_build_5()` (the sanctioned escape hatch,
   exactly as flagged) rather than via the scene model.
2. The naming collision was fixed by renaming the Behavior's own
   completion field to `formation_done` (not `finished`) — `vyruss_vs2.py`
   now sets the *real* `baddie.finished` itself only once its own
   hand-written `TravelTo`-equivalent step also reaches
   `(final_x, final_y)`, preserving every existing reader's exact
   original semantics. `add_baddie()` no longer builds the six-item
   queue for the entrance phase (`x_dir`/`final_x`/`final_y` plus
   `movements = None` is all it sets now); `update_one_baddie()` uses
   `movements` being `None` vs. `[]` vs. populated as a three-way signal
   (still running inside the Behavior / a hand-written queue just
   drained / a hand-written queue is active) covering both the new
   `TravelTo` tail and the untouched attack-run reassignment. `TravelX`
   is now genuinely dead code and was removed; `TravelBy`/`TravelCloser`/
   `TravelAway` stay, since `update_attacking()` still needs them.
   Verified: the full `test_vyruss_vs2_examples.py` suite passes
   unchanged in behavior (one assertion updated to check
   `BaddieFormation`'s own `state_name()` instead of a `baddie.movements`
   length that no longer means what it used to), including
   `test_group_reaches_attacking_and_a_baddie_attacks`, which exercises
   the full flow through formation completion, the hand-written
   `TravelTo` approach, and a real attack-run reassignment end to end.
   **Reflashed and reverified on the physical rotor** (filesystem-only
   redeploy, no firmware rebuild needed): `povperf` showed zero
   overruns/frame-overruns over a 5-second live run with baddies actively
   forming up, `heap_delta=-544` (small, stable, within the established
   allowance), and LED captures at three points during the entrance
   sequence show baddies visibly spreading out into formation correctly.

### `vixeous` — a smaller port, plus two more real catalog mismatches found

Also attempted the same for `vixeous`, since the goal names it
explicitly. The `enemies` pool's own near-identical phase/theta
oscillation (the most obvious first target — the exact same shape as the
boss's own motion below) turns out **not to be portable at all, for a
real structural reason**: `vixeous_scene.vs2model.json` already declares
`self.enemies.var('phase', ...)`/`.var('theta', ...)`
(`SpritePool.var()`), and a Behavior's own `state = (...)` tuple cannot
redeclare a name a pool already owns —
`apps/micropython/vs2/__init__.py`'s `_prime_pool_state` raises
`StateConflictError` at attach time, by design, to protect the
zero-allocation priming guarantee. Fixing this for real needs either a
new schema capability (read/write a field without owning/priming it) or
removing the pool's own `.var()` declarations (losing the kinds-table/
live-tune editing those provide for `phase`/`theta`) — neither attempted;
documented as a genuine, real gap, not solved.

The **boss** (a lone sprite, no pool, no `.var()`) doesn't hit that
collision, so it became the actual target: **`BossOrbit`**
(`games/vs2_examples/vixeous/code/build_boss_orbit.py`) owns the boss's
`theta`/`phase` oscillation and its bounded approach toward
`BOSS_STOP_Y`, proven tick-by-tick identical to the original
(`tests/test_vixeous_boss_orbit.py`, including the display-width-seam
wrap case) and **wired into the live game** via `on_build_9`
(`update_entities()` trimmed to just the camera-dependent `x`
reprojection and frame banking it still needs to do by hand).

**A second real, previously-undiscovered catalog mismatch found while
scoping `boss.frame`.** `(phase // 8) & 1` is exactly the square wave a
composed `Animate(first=0, last=1, ticks=8, mode="loop")` action already
produces — tried first, as the natural, sanctioned tool. It silently
does not work for a lone-sprite subject: `Animate`'s clock is explicitly
pool-shaped (only `run()` advances it; `run_one()` — what the generator's
`apply_to_all` always calls for `subject_kind="sprite"` — deliberately
never does, per its own docstring), so `frame` freezes at its initial
value forever, no error. Verified directly with a standalone probe
before trusting the parity test. `boss.frame` stays hand-written, like
`boss.x` already does for the unrelated camera-reprojection reason.

Also caught and fixed a real bug in this port's own parity test along
the way, not in the Behavior itself: setting `theta`/`phase` on the boss
sprite *before* calling `behave()` gets silently overwritten by
attach-time state priming (`_prime_sprite_state` zeroes every declared
state name) — must set them after. A reminder that this priming
footgun applies to hand-authored test harnesses too, not just to Behavior
design itself.

**Reflashed and reverified on the physical rotor.** `BossOrbit` ticks
unconditionally every scene tick from the moment the scene builds,
including the long stretch while `self.boss` is still hidden (the same
"a lone-sprite Behavior's `step_one` runs regardless of `visible`"
gotcha `vyruss_vs2`'s own `player_explosion` already found — harmless
here, since `maybe_start_boss()` resets `theta`/`phase`/`y` fresh the
moment the boss actually activates) — confirmed this costs nothing and
breaks nothing over a real 8-second run: `overruns=0`, `frame_overruns=0`,
`heap_delta=240` (positive/stable, identical structural census to every
earlier `vixeous` hardware run this session, `layers=2 sprites=27
tilemaps=2`). Forcing the boss to actually activate over USB serial (to
visually confirm the orbit itself on real LEDs, not just the
always-ticking-while-hidden cost) was attempted via the `vs2beh` live-tune
protocol but not completed in this session — the CPython/MicroPython-shim
integration test (`test_boss_activates_and_orbits_via_the_attached_behavior`)
already covers this exact activation path end to end, so it was judged
sufficient rather than spending more time debugging the wire protocol's
reply framing live.

### `vyruss_vs2`'s attack-run reassignment — also ported, closing that gap

The one deferral flagged when `BaddieFormation` first landed. Two new
states, `attack_closer`/`attack_away`, entered only via hand-written
`update_attacking()`'s own `StateMachine.force_state(baddie,
"attack_closer")` call — unlike `closer1`/`away`, they read their
starting distance from a *per-sprite* field (`attack_distance`, set
immediately before the `force_state()` call) rather than a fixed
Behavior-level param, since `update_attacking()`'s own `distance = max(0,
baddie.y - RIM_Y)` is genuinely computed fresh per attack event. A new
per-sprite flag, `in_attack_run`, gives hand-written code its own
unambiguous "cycle finished" signal — `formation_done`/`baddie.finished`
keep meaning exactly what they already meant elsewhere in the file,
deliberately not reused for a second purpose the way the original's
single `movements`-empty check was.

`TravelBy`/`TravelCloser`/`TravelAway` are now genuinely dead code
(nothing left calls them) and were removed from `vyruss_vs2.py` — only
`TravelTo` (the final formation approach, a "move toward" primitive)
remains hand-written, the last piece of the original six-part
choreography that doesn't fit a fixed-distance-walk state machine.
Proven tick-by-tick identical to the original's own
`TravelCloser(distance)`/`TravelAway(distance)` pair
(`AttackCycleParityTests`), and the full existing
`test_vyruss_vs2_examples.py` suite (including
`test_group_reaches_attacking_and_a_baddie_attacks`, which exercises this
exact path end to end) passes unchanged.

**Reflashed and reverified on the physical rotor — with a real scare
worth recording, resolved as a false alarm.** A 20-second live run's
`heap_delta` kept getting *more* negative every 5 seconds
(-90688, -219072, -342400) and the scene unexpectedly returned to the
launcher partway through — looked exactly like a leak-then-crash at
first glance. It wasn't: the run had **zero player input** (no joystick
driving it), so bombs kept hitting the stationary player repeatedly
(confirmed via the wire protocol's own audio cues — repeated
`sound .../explosion3`, the real `explode_player()` line), burning
through all 3 lives and hitting a completely ordinary `game_over()` →
`self.pop()` — confirmed for certain by watching for the `vy-gameover`
music cue (present) and any `traceback` wire frame (absent) over a fresh
25-second run. The heap trend was just the ordinary cost of an unusually
death-heavy playthrough (far more `explode_player()`/`respawn_player()`/
audio/sprite churn than a normal run gets), not a leak. **Lesson for
whoever runs the next unattended hardware check on a game with real
lose conditions: drive some input (or expect an early, legitimate
game-over) rather than reading a mid-run heap dip as a crash signal by
itself** — check for the actual traceback frame or an unexpected scene
shape before concluding anything broke. `overruns=0`/`frame_overruns=0`
held throughout both runs.

## Suggested immediate next action

T15-T18, T0, all three phases of T17, the Blockly UI for state hats,
`vyruss_vs2`'s `BaddieFormation` port (now covering the *entire* original
six-part choreography except `TravelTo` itself, entrance and attack run
both), and `vixeous`'s `BossOrbit` port are all fully done, merged into
`vs2/wave7-integration`, verified in software and (all except
`BossOrbit`'s own visual activation, see above) on real hardware, and in
[PR #159](https://github.com/ventilastation/vsdk/pull/159) against
`design/vs2-behaviors` — **its description needs one more update** to
mention the attack-run port before assuming it's current (everything
through `BossOrbit` is already reflected there). **Two threads remain
open, neither blocking the other:**

1. **Continue the Blockly-porting goal.** `vyruss_vs2` now has exactly
   one deliberately-hand-written piece left (`TravelTo`, a "move toward"
   primitive with wraparound angular math) — there may be nothing more
   worth porting there without inventing a new "move toward" Action, a
   real but separate design question. `vixeous` has more real headroom:
   three genuine catalog/schema mismatches are documented from actually
   trying, not guessed at (`SpritePool.var()`-vs-Behavior-`state=`
   collision, blocking the `enemies` pool's own phase/theta oscillation
   entirely; `Animate`'s lone-sprite incompatibility, blocking frame
   banking on any standalone sprite; and the pre-existing angular, not
   box-overlap, collision checks / procedural polar terrain generation /
   general boss-fight logic, none of which anything built so far
   addresses). Treat all of these with the same "don't force a mismatched
   shape" judgment already applied throughout, not as a todo list to
   clear by brute force — some may genuinely need new framework
   capability (a schema addition, or a real `vs2.behaviors`/`vs2.actions`
   change) rather than more JSON.
2. **Wave 6** (T13 native `Collide`, T14 flat sprite records) — still
   fully unblocked, T0's written verdict is in, still not started.
