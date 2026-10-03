# Documentation improvement proposal

- **Status:** Proposed; implementation has not started.
- **Audience:** Maintainers and contributors changing project documentation.
- **Review date:** 3 October 2026.
- **Baseline:** Working tree based on `f7b3a2c` on `main`; existing local
  changes in the Retro-Go submodule were not altered.

This proposal records a project-wide documentation review and a six-change
implementation plan. Findings describe the review baseline; they should be
checked against current code when each change is implemented. Creating this
proposal does not resolve the issues recorded below.

The proposed outcome is a short, current starting path for each audience,
one authoritative description of each supported task or contract, and a
clear boundary between current instructions and historical evidence. Start
with factual corrections and onboarding; reorganize files only after their
purpose and status are settled.

The scope is documentation, navigation, publication checks, and asset
cleanup. Firmware behavior, API changes, ROM-format migration, removing
historical game code, and new editor features require separate work.

For the recommended work order, see the [implementation plan](#implementation-plan).
For individual dispositions, see the [file-by-file inventory](#file-by-file-inventory).
The [proposed organization](#proposed-organization) is an end state rather
than a requirement to move all files in the first change.

## Overall assessment

The project has useful documentation and a good VS2 teaching core. Its biggest problem is authority: a reader can find several plausible descriptions of the same system, written at different stages of development, with no dependable way to know which applies. The highest-value change is to make one current page authoritative for each task or contract, and move superseded plans out of the normal reading path.

Keep the VS2 tutorial, generated API reference, runnable chapter files, protocol specifications, hardware acceptance procedure, and lessons from difficult hardware bugs. Simplify the entry points and separate instructions, reference, explanation, and historical evidence. A wholesale rewrite would discard useful work and is unnecessary.

## Scope and verification

- Reviewed the 66 tracked first-party Markdown files, including all 51 under `docs/`, component READMEs, AGENTS.md, TODO.md, and the two game-specific READMEs. The inventory below gives a disposition for every file.
- Also inspected documentation build configuration, CI, Makefile targets, launch scripts, relevant source/docstrings and CLI help definitions, browser page text, credits, and the two mechanical drawing PDFs. Vendored libraries and the Retro-Go submodule's upstream documentation are outside this prose cleanup; project claims about that integration were checked against the available source. The submodule already had local changes.
- Built VS2 HTML with Sphinx 8.2.3, using `-W --keep-going`: **passed, zero warnings**. Build output and the isolated documentation environment are under `/tmp`, not in the source tree. This build includes 17 Markdown pages, not the other 34 Markdown files under `docs/`.
- Checked local Markdown file/directory targets: **six broken relative links**. Checked all 28 figure/image/literalinclude directives: their referenced files exist.
- Ran the existing tutorial-step tests: **6 passed**. Ran the finished tutorial-game tests: **12 passed**. Syntax-parsed 17 tutorial/screenshot example Python files successfully. CI already compiles the chapter step files with mpy-cross and runs tutorial behavior tests; preserve this investment.
- Used MicroPython v1.26.1's Unix port to isolate dynamic two-index assignment: 1,000 `grid[col, row] = value` calls retained **32,032 bytes** with automatic GC disabled; equivalent direct bytearray writes retained **0 bytes**. This is a demonstration of the tuple created by the indexing syntax, not a measurement on the rotor or a complete VS2 allocation benchmark.
- During the audit, no firmware was flashed, no deployment was made, and existing project documentation was not edited. This proposal and its index entry were added afterward. External website availability and fresh installations on all operating systems were not tested. Historical hardware-verification claims below come from the repository's records, not a new hardware session.

### Reproducing the runnable checks

Use the project Python environment described in the
[emulator setup guides](../README.md#the-path) for the tutorial tests:

```sh
python3 tests/test_tutorial_steps.py
python3 tests/test_tutorial_game.py
```

The documentation build can use an isolated environment, from the repository
root:

```sh
python3 -m venv /tmp/vsdk-docs-venv
/tmp/vsdk-docs-venv/bin/python -m pip install -r docs/vs2/requirements.txt
/tmp/vsdk-docs-venv/bin/python -m sphinx -b html -W --keep-going docs/vs2 /tmp/vsdk-docs-html
```

To isolate the tuple-indexing allocation, run this with the MicroPython Unix
port. Exact byte counts depend on runtime version and build; the recorded
result above is from v1.26.1. This wrapper demonstrates indexing syntax,
not the complete VS2 implementation:

```python
import gc

cells = bytearray(4)

class Grid:
    def __setitem__(self, position, value):
        cells[position[1] * 2 + position[0]] = value

grid = Grid()
col = 0
row = 0
gc.collect()
gc.disable()
start = gc.mem_alloc()
for _ in range(1000):
    grid[col, row] = 1
indexed_bytes = gc.mem_alloc() - start
gc.collect()
start = gc.mem_alloc()
for _ in range(1000):
    cells[row * 2 + col] = 1
direct_bytes = gc.mem_alloc() - start
gc.enable()
print("indexed tuple bytes:", indexed_bytes, "direct bytes:", direct_bytes)
```

The six broken file/directory links and 28 existing directive targets are
recorded audit results. A maintained general link/anchor checker is part of
the proposed publication work, not an existing CI guarantee.

## What already works well

1. The README's game-development/internals split is useful. Preserve it, but add an obvious path for console operators and browser users.
2. VS2's tutorial teaches one concrete game, uses real art, explains the unusual polar coordinates, and ends with budgets. The cumulative source files are much more useful than disconnected snippets.
3. The reference comes from docstrings. Keep it tied to code rather than writing a second independent method catalog.
4. Protocol and acceptance documents contain exact layouts, commands, and gates. These details are valuable; improve their accuracy and discoverability rather than deleting them for brevity.
5. Audio placement, the pointer-and-length WASM bridge rule, NVS ownership, and serialized flashing are documented project invariants. They deserve concise canonical explanations and links from local instructions.
6. Investigation notes record unusually useful debugging evidence. Preserve the resolved cause and lessons, with the original chronology clearly secondary.

## Findings and recommended changes

### 1. Give new game developers one current starting path

[docs/README.md](../README.md) recommends VS2 but then sends readers to `ventap` and `vyruss`, both legacy examples. The root README still describes cloning the smallest game. [developers-guide.md](../developers-guide.md) mixes shared project conventions with a complete V1 tutorial; its legacy warning appears only when the reader reaches Part IV, after they have already copied V1 code and learned V1 scene lifecycle.

Make `games/demos/tutorial_game`, the VS2 tutorial, and a minimal VS2 starter the primary examples. Label V1 examples at the link, not several chapters later. Extract shared folder/assets/menu/submission material into one current guide, and move the V1 lifecycle/sprite material to an explicitly labeled legacy guide. Also fix the old guide's `{ "api": "vs2" }` example to include `api_revision: 2` whenever it is presented as usable metadata.

Do not rewrite historical jam games just to make the documentation consistent.

### 2. Put working destinations in the entry points

The root README and docs index mention the browser emulator without linking directly to its public entry point. They mention Read the Docs without a direct published documentation URL. Browser readers are sent toward a deployment page; VS2's Sphinx-specific directives are difficult to read on GitHub.

Add three prominent destinations: **Play/edit in the browser**, **Make your first VS2 game**, and **Install the desktop emulator**. Link both the published documentation and its source. Resolve the published documentation URL from the project's configured deployment rather than guessing a Read the Docs project name.

Move the root README's detailed CPU/shader renderer comparison into an emulator guide; the root page should orient readers and get them running.

### 3. Correct the public renderer explanation

[VS2 design notes](../vs2/design-notes.md) and the tutorial introduction say there is no framebuffer and describe scene composition as something done at each physical angle deadline. The current renderer has two complete polar framebuffers and separates background projection from the timed LED-column service. See [povdisplay.c](../../hardware/rotor/modules/povdisplay/povdisplay.c).

Teach the stable concept: the physical output has an angular deadline, and game logic is independent of rotation. Put the current double-buffered implementation in internals. Remove the false framebuffer assertion from introductory material and align it with the hardware-acceptance page, which already describes the separate service and projection timings.

### 4. Make the allocation guidance precise

[Budgets](../vs2/tutorial/budgets.md) explicitly lists `tilemap[col, row] = WINDOWS` as allocation-free. Dynamic comma indexing creates a tuple, as the local MicroPython check demonstrates. [Going further](../vs2/going-further.md) already shows the direct `tilemap.cells[row * columns + col]` alternative.

Keep convenient checked indexing in the introductory examples, but distinguish it from direct buffer writes recommended for frequent updates. Avoid claims such as “nothing after this allocates,” “nothing is allocated while the game runs,” and “costs nothing” unless they have target-specific evidence. Sealing prevents new render objects; it cannot prevent arbitrary Python allocation, and timers deliberately store callbacks and arguments.

The advice to build once and reuse objects is good. Explain its actual guarantees and make the fast path easy to find. This correction does not require changing the API.

### 5. Describe geometry and limits as they are maintained today

The display tutorial says geometry comes from a generated target definition. The current Python `display_geometry.py` and C `display_geometry.h` are paired definitions maintained together, and VS2's `_Limits` contains explicit values alongside native constants.

Correct the documentation to describe the present arrangement. If a generated single source is still desirable, record that as future work; do not describe the proposal as already implemented. Keep the recommendation to read `vs2.display` and `vs2.limits` in game code.

### 6. Update the normative host protocol to VS2 payload version 3

[host-protocol.md](host-protocol.md) presents version 1 as current and says VS2 is adapted into the sprite renderer shape. [The runtime](../../apps/micropython/vs2/__init__.py) emits version 3 with tilemap records, cell data, and ordered draw references; browser and native desktop decoders support the newer layouts.

Document the current header, record layouts, draw-order section, and version compatibility. Label versions 1 and 2 as older accepted transports. Cross-reference decoder tests. Keep API revision 2 and transport payload version 3 clearly distinct: they version different things.

The table also omits install-related messages and several calibration/profiler responses used by existing hosts. Decide whether this page is the full command registry or a short registry that links to subsystem contracts, then complete it accordingly.

### 7. Complete the ROM specification without pretending the sentinel migration shipped

[rom-format.md](rom-format.md) describes strip records without their glyph trailer. Current Python and JS builders also write a trailing little-endian glyph-length field and UTF-8 glyph map after each strip's pixels. That trailer and compatibility behavior belong in the normative specification.

[rom-width-sentinel.md](rom-width-sentinel.md) remains important: the width sentinel and frame clamp are still in current builders. **Keep it as an active proposal/investigation.** However, parts of its audit are stale: JS now accepts `glyphs:` and both builders emit glyph trailers. Update individual work items and attach its old “34 ROMs / 475 records” findings to the audited revision. Do not turn snapshot counts into permanent facts about the current tree.

Do not change ROM encoding as part of a documentation cleanup. That requires its own compatibility and hardware work.

### 8. Replace obsolete audio protocol sections

[emulator-audio.md](emulator-audio.md) starts with a useful current status, then reintroduces the original proposed protocol. Its old `aframe <len>` format, opcode map, cycle-based timing description, and phasing conflict with the actual `aframe <nbytes> <nsamples>` sample-based register log. The real contract is in `emu_audio_bridge.h` and the host wrappers.

Rewrite this as current architecture, exact wire contract, desktop/browser support matrix, build instructions, and verification limits. Keep unverified hardware/audio fidelity explicitly unverified. Remove obsolete rollout instructions from active sections.

[emulator/chipsynth/README.md](../../emulator/chipsynth/README.md) lists only Genesis/SMS as implemented and NES as planned, but its Makefile and desktop factory table implement Genesis, SMS, NES, GB, and MSX. Update that table, explain the smaller SMS/NES/MSX browser subset, and avoid implying bit-exact full audio where ROM-dependent sample channels or fidelity limits apply.

### 9. Remove old native-build instructions from the active path

[native-app-handoff.md](native-app-handoff.md) still describes separate IDF 5.4/5.0.4 trees, a combined factory+Voom image, and `--micropython-idf-path` / `--retro-go-idf-path` options. The existing builder accepts a single `--idf-path`; current build guidance and workbench lockfile use the 5.5.x family. The old combined builder still exists, so classify it as legacy tooling rather than claiming the file was removed.

Extract the still-useful native launch/return contract into current on-device architecture. Archive the old combined-image workflow. Make `building.md` the sole toolchain/flash instruction page, with a decision table for `flash-full`, `flash-recovery`, and `initial-flash`.

### 10. Fix the web architecture page's repository identity

[web-emulator-architecture.md](web-emulator-architecture.md) says the top-level `emulator/` is only the website's published copy. Inside this repository it is the desktop host. Use explicit names: **vsdk/emulator** versus **website/emulator**.

The page also contains a long native-app handoff section with the obsolete factory-only layout and split IDF setup. Move that subject to on-device architecture. Keep this page focused on browser workers, WASM filesystem, input/events, scene payloads, renderer selection, and pointer-based transport. Update old browser implementation paths to the current platform modules.

Preserve the pointer-and-length rule and the heap regression procedure prominently.

### 11. Bring the workbench document's status and commands into agreement

[workbench.md](workbench.md) describes hardware-verified capture and later says it has not been flashed. It says host selection uses RESYNC probing, while `find_board.py`, `building.md`, and AGENTS.md now describe USB-ID registry lookup. It describes a transparent non-parsing bridge, although RESYNC and reserved USB capture commands are intercepted. Its clock examples say 20 MHz; the default Makefile configuration is 30 MHz and the real value comes from NVS.

Fix these contradictions, replace “button-state byte” in old diagrams with the current frame, and use the Makefile flashing targets instead of `idf.py ... flash monitor`. Keep exact wiring, UART, UDP, and USB capture contracts. Split a short wiring/run/troubleshoot guide from the long telemetry reference and design history.

### 12. Remove the obsolete direct-to-rotor Wi-Fi development diagram

[input-protocol-v2.md](input-protocol-v2.md) still shows a laptop connecting by TCP to the spinning main board in “desktop / Wi-Fi mode.” Current local desktop TCP connects to the MicroPython subprocess; physical display telemetry comes from the workbench over UDP.

Correct that diagram and keep the normative joystick, command, and RESYNC parts together. Move the superseded implementation outline and “files changed/not changed” rollout material into history, or delete it after extracting any unique rationale. It currently occupies nearly half the page and restates old mappings.

### 13. Reconcile OTA's repeated descriptions

[ota.md](ota.md) has good operational evidence but several descriptions have drifted apart. Its flash-full section explains on-flash hash verification, while the tier-2/3 summary says an NVS hash match is sufficient to skip. Current `_partition_matches()` checks actual flash contents for inactive partitions. Its file-cache explanation says nothing besides the updater writes fielded files, while the package installer is another writer and the package document explains collisions with in-tree games.

Describe the actual cache and verification rules once, including package/manual-write implications. Reconcile `flash-recovery` provisioning with `building.md`: the helper can seed missing wiring and supplied Wi-Fi configuration, preserving existing values; it is not simply “never writes NVS.” Fix the illustrative MicroPython image size of 2,490,368 bytes, which exceeds the documented 2 MiB slot. Explain factory recovery, normal `micropython`, and firmware-update handoff in one canonical location.

Make an operator-facing OTA runbook with prerequisites, trigger, visible progress, expected reset, and troubleshooting. Keep the implementation explanation, failure matrix, and measured rollback evidence in reference/explanation material. Move session anecdotes and now-resolved debugging chains out of the normal procedure.

### 14. Treat solved corruption investigations as solved

The internals index says menu corruption has two statically found fixes that are not hardware-verified. The investigation itself records a third root cause and successful hardware validation on 24 July 2026. OTA-ring corruption and its original feature plan also say implemented/fixed and hardware-verified.

Archive the three resolved documents after extracting concise lessons: buffer ownership, correct buffer-protocol types, duplicate ROM loads, and display initialization retries. Lead historical investigations with final cause, fix, and evidence. Move rejected hypotheses and old instructions behind a clear historical heading; old “not tested” sentences currently contradict their own conclusions.

Do not delete the evidence or turn historical session commands into recommended current recovery procedures.

### 15. Update branch-scoped status language carefully

`game-packages.md`, `remote-workbench-access.md`, and `vs2-hardware-acceptance.md` ask for feature/implementation branches although their associated source is present in the current `main` tree. The VS2 rework proposal still ends “implementation can start,” despite the new package/lifecycle/reference being present.

Replace branch instructions with a supported revision or feature prerequisite and links to historical commits where useful. Distinguish **implemented**, **host-tested**, **hardware-tested**, and **deployed**; source presence is not proof of all four. In particular, keep the package page's hardware-validation checklist marked unverified until there is evidence to change it.

The package checklist also names `make dev-emulator`, which is absent; use `make run-emulator` or the documented launch command after checking the intended workflow. “Risk #5 from the plan” has no useful local destination.

### 16. Replace the stale IDE proposal with a current integration contract

[web-ide-integration.md](web-ide-integration.md) mixes future GitHub product ideas with implemented workspace methods. It says Monaco loads from a CDN, but the loader uses the vendored `web/vendor/monaco/vs`. It describes paths as relative to `/apps/micropython`; current workspace resolution explicitly handles `games/`, `system/`, `apps/`, and ROMs separately.

Document exact path resolution and current methods, restart/save behavior, and persistence. Move GitHub clone/commit/push and alternative iframe architecture into a pending proposal. Avoid suggesting implemented GitHub synchronization.

Add a short browser user guide: open or create a game, edit code, edit PNGs, rebuild/run, inspect a traceback, export/share, and understand what “Save” retains across a reload. Distinguish distribution packages from original editable asset sources.

### 17. Fix the six broken local links and textual leftovers

| Source | Current link | Correct direction |
|---|---|---|
| `docs/internals/building.md:5` | `docs/` | `../README.md` |
| `docs/internals/workbench.md:43` | `hardware/workbench/` | `../../hardware/workbench/` |
| `docs/internals/workbench.md:173` | `hardware/rotor/modules/povdisplay/povdisplay.c` | prepend `../../` |
| `docs/internals/workbench.md:417` | `apps/micropython/ventilastation/serialcomms.py` | prepend `../../` |
| `docs/internals/workbench.md:454` | `hardware/rotor/modules/povdisplay/minispi.c` | prepend `../../` |
| `docs/internals/workbench.md:474` | `hardware/workbench/workbench_esp32s3/` | prepend `../../` |

Also replace textual references to `ARCHITECTURE.md`, `BUILDING.md`, and the misleading `DEPLOY.md` link label with real current filenames and section links. Update the ROM README's `games/*/images` pattern to `games/*/*/images`, and link directly to the relevant guide.

Mechanical Assembly's root-relative `/docs/images/...` links are not portable across GitHub and a deployed subpath; use real relative links.

### 18. Make the index complete and organize by task

`emulator-performance.md` has no direct entry in the internals index. The OTA feature/history notes are reachable indirectly but not classified there. `history/` has no README that explains its contents. Two superseded design documents remain at the game-developer docs root, where readers naturally assume they are current.

Give every maintained page a home in an index or toctree. Start internals by task: change runtime, change desktop emulator, change browser/IDE, build/operate hardware, inspect a wire contract. Its current suggested reading order puts firmware architecture/building before browser work, even when no hardware is relevant.

Do not flatten all technical details into one very long developer guide.

### 19. Unify publication and checks using the existing tooling

Read the Docs builds only `docs/vs2`. General setup instructions link out to GitHub, and internals live outside that search/navigation/check boundary. CI tests the software but has no Sphinx build or general documentation-link job.

Prefer extending the existing Sphinx/MyST/Furo setup into one documentation site with audience-based navigation and shared search. There is no need for a second documentation generator. Keep `docs/vs2` source paths stable initially; widening the Sphinx source root and toctree is a separate, reviewable change.

Add a CI docs build with warnings as errors, local target/anchor checks across first-party Markdown, and validation of literalinclude paths. Run external link checks periodically rather than making every PR depend on third-party availability. Keep existing executable tutorial and mpy-cross checks; add checks only where coverage is missing.

### 20. Repair desktop setup and add troubleshooting

The OS setup pages are wonderfully short, but have no common prerequisite/tested-version matrix, successful-start example, or troubleshooting. macOS is written specifically for an M1/Homebrew layout and omits FFmpeg even though the audio conversion path invokes it. Windows uses global pip instead of the `.venv` flow and states “Python > 3.13,” whereas CI uses 3.12; the real supported matrix should be verified rather than inferred from either statement. The Windows MicroPython executable is already tracked in `emulator/micropython.exe`; explain that bundled runtime rather than asking users to install one unnecessarily.

Share clone/environment/start/controls text once, with small per-OS dependency sections. Document optional native renderer compilation/fallback, FFmpeg configuration/fallback, audio backend issues, MicroPython executable discovery, OpenGL fallback, game-not-found errors, and where tracebacks appear. Validate each promised platform on a clean install before broadening support claims.

### 21. Add the missing contributor and component entry points

AGENTS.md carries contributor rules, but humans lack a short guide covering setup, test prerequisites, partial/skipped test categories, required checks per subsystem, and docs editing/building. Source/docstrings contain useful commands that are hard to discover.

Add a concise contributor guide linked from README. An `emulator/README.md` should explain the three supported modes and link to the relevant guides. A `tests/README.md` should explain the existing runner, required tools, skipped categories, and hardware gates. Tools can have a small catalog of common tasks linking to `--help`; do not duplicate every flag or wrap every script in another manual. `games/` and `system/` entry READMEs can be very small pointers to conventions and the appropriate examples.

### 22. Give hardware users a complete route

`hardware/rotor/README.md` contains only an old generic MicroPython clone/build sketch and never directs readers to the project's board target, NVS provisioning, or current flash procedures. `hardware/base/README.md` is three sentences despite production scripts, audio, UART, controller input, an Arduino relay, and OTA hosting living there. The workbench README is a useful pointer but lacks a quick build/wire/run summary.

Add a hardware index linking electronics, mechanical assembly, supported revisions/wiring, rotor flashing, base setup, and workbench testing. Expand the base guide around actual headless operation, input/audio checks, device selection, launch supervision/logs, and release bundle installation. A contributor should not have to discover `base-remote.sh` and `consoleengine.py` to learn how the machine runs.

Make the official docs use the serialized Makefile flash targets. Existing low-level flashing helpers and recovery snippets need classification; do not promote direct script/`esptool` invocation as the day-to-day path. If an essential recovery action has no Makefile wrapper, handle the wrapper as a separately scoped tooling task.

### 23. Preserve and identify the mechanical assets

The assembly prose, CAD link, photographs, and both single-page PDFs are useful and belong with the hardware files. The axle drawing has dimensions and a small title block, but important identification/material/revision fields are blank. The fan/support drawing has no comparable identification block. PDF text extraction produces no usable text, so visual rendering is essential for review.

Keep the originals. Add adjacent metadata for part name, compatible machine revision, CAD source/export revision, material/thickness, units, and what changes when the fan/slip ring differs. Link the assembly guide from the hardware index. This is a provenance/discoverability improvement, not a validation of manufacturing dimensions.

### 24. Turn TODO.md into a trustworthy queue

Its introduction says completed/discarded items are pruned, but many remain. Several unmarked items describe features now present: game packages, relative sound names, VS2 tilemaps/text, generated web bundles, and a Vixeous game. The mix of `[done]`, `[planned]`, `[HIGH]`, `[ONGOING]`, raw requests, separators, and duplicated plans makes it hard to tell what to pick up next.

Choose one queue: GitHub issues, or a short TODO containing only current open items and links. Remove done/discarded entries and duplicates after checking actual feature completeness. Turn long product requests into issue/proposal links. Give ongoing work an owner or issue and a concrete next action. Preserve historical requests only when they encode a requirement not available elsewhere.

### 25. Remove low-value clutter conservatively

- `docs/internals/history/design-notes.md` is an old Spanish roster/behavior scratchpad with little explanation or reusable engineering context. Candidate for removal from active documentation; preserve only unique attribution or requirements if needed.
- `hardware/pre-voom/README.md` should identify the hardware experiment as historical and link to current native-app docs. Removing the experiment's source is a separate decision.
- Root `index.html` is a second, older browser shell with stale keyboard/help text. The build/screenshot tools inspected use `web/index.html`. Candidate for deletion or a small redirect after checking external consumers, not an authoritative emulator entry point.
- `docs/images/polar-coords.png` has no Markdown references. Candidate for deletion after checking code/site consumers.
- `docs/images/` totals about 16.3 MB, largely large hardware photographs. Optimize web derivatives and move hardware-only images beside hardware docs when reorganizing; preserve original CAD drawings and source photographs where needed.
- Root README image alt text is just “image.” Use meaningful descriptions. Prefer durable project-owned image references for important explanatory figures.
- Keep game README text and audio credits. Their unusual `code/` or `images/` placement is discoverability debt, not evidence they are disposable. Link them from a game catalog or local pointer rather than restyling jam history. Song chart `.txt` files are runtime data and must not be mistaken for old documentation.

### 26. Keep screenshot regeneration useful without making it brittle

`tools/vs2_doc_images/README.md` is detailed and valuable. Keep it beside the generator and link it from the docs contributor workflow. Its examples and figures support the tutorial well.

Move one-off comments about the original capture machine or required fixes into historical notes when no longer relevant. Prefer fixed seeds/controlled game states and explicit waits over “rerun until a good frame”; include the renderer/runtime revision in capture metadata. Keep committed instructional screenshots, and distinguish them from temporary debug evidence.

## Proposed organization

Start with a complete index and accurate status. Move files only after their authority and purpose are settled. This target tree preserves the established VS2 tutorial/reference paths and keeps the rest shallow:

```text
README.md                         brief introduction and start links
AGENTS.md                         contributor/agent invariants
TODO.md                           open work only, or issue-index pointer

docs/
  README.md                       one start page, grouped by reader goal
  guides/
    emulator-setup.md              shared flow with OS-specific sections
    emulator-use.md                controls, modes, renderers, debugging
    browser-ide.md                 edit, run, assets, save/export
    game-assets-and-packaging.md   layout, YAML, icon/meta, sounds, package
    contributing.md               source setup, checks, documentation work
  vs2/                            retain tutorial/reference/glossary structure
    migration.md                  short revision-1 to revision-2 guide
  legacy/
    sprites-api.md                V1 guide, clearly labeled
  internals/
    README.md                     tasks and complete subsystem index
    architecture/                 on-device, native apps, desktop, web, audio
    protocols/                    ROM, host, input, package, color profile
    operations/                   build/flash, OTA, workbench, calibration,
                                  remote access, hardware acceptance
    decisions/                    short accepted decisions and active proposals
    history/                      resolved investigations and superseded plans
      README.md                   status, revision, and replacement links

hardware/README.md                electronics/mechanics/base/rotor/workbench map
hardware/*/README.md              local purpose, quick start, canonical links
emulator/README.md                 desktop and headless host entry point
tests/README.md                    existing test categories/prerequisites
tools/README.md                    small task-to-tool catalog
```

The tree is an end state, not a reason to create lots of empty folders. An architecture/reference split may initially be headings within the internals index. Avoid moving VS2 files solely for symmetry. Preserve old URL/path entry points with short pointers or published redirects where readers may already depend on them.

For maintained operational pages, use a small consistent header: **purpose, audience, implemented/tested status, source of truth**. For plans and history, additionally give **status, baseline revision, date, and replacement**. Verification dates matter for hardware procedures and measured performance; do not add decorative “last updated” dates to every tutorial.

## Archive, merge, and remove decisions

| Material | Recommendation |
|---|---|
| VS2 API rollout plan | Archive; extract still-open work into issues/proposals first. Its old API examples are unsafe current guidance. |
| VS2 rework proposal | Convert important accepted decisions into a short revision-2 design record; archive the full proposal and old code-line snapshots. |
| Early OTA A/B proposal | Move to history; it already says superseded. Keep only a brief old-path pointer if needed. |
| Native app handoff plan | Merge current launch/return contract into on-device architecture; archive obsolete build/image sections. |
| IDE integration proposal | Replace with a current workspace contract; keep only genuinely unimplemented product work as a proposal. |
| Menu and OTA-ring corruption investigations | Archive as resolved; extract reusable ownership/type/initialization lessons. Preserve evidence. |
| OTA progress original request | Archive as implemented, retaining the original requirement record. Current behavior stays in OTA reference. |
| Emulator performance investigation | Keep as a dated performance case study; extract current profiling/comparison procedure into emulator use. |
| ROM width sentinel proposal | Keep active and update completed sub-items; do not archive the unresolved encoding problem. |
| Legacy developer guide | Split shared current game conventions from an explicitly legacy V1 guide. |
| Moved VS2 API guide | Keep a minimal pointer for compatibility; relocate its useful migration table and docs-build instructions. |
| Historical game-layout plan | Keep only if historical rationale is useful; add clear superseded labeling and a history index. Current layout belongs in current guides. |
| Old scratch design notes | Remove after checking for unique attribution/requirements. |
| Done/discarded TODO entries | Remove from current queue; Git history retains them. |
| Credits, game stories, CAD/PDFs, song charts | Preserve. They have purposes independent of the documentation navigation. |

## Implementation plan

### Change 1: Correct facts and links before moving anything

Fix the six relative links and old filename references. Correct framebuffer and allocation claims, current wire formats, synth support, workbench discovery/verification, unsupported native-build options, and the internals index's solved investigation status. Complete the ROM glyph trailer description. Update active proposal sub-items without claiming the sentinel migration shipped.

**Done when:** the known contradictions are resolved, local target checks pass, Sphinx remains warning-free, and tutorial tests still pass. No firmware/API/ROM encoding changes in this change.

### Change 2: Make the first-use experience coherent

Make the root README short and link directly to the browser and published docs. Use the VS2 starter/tutorial as the default first game. Extract shared game-assets/menu/packaging conventions and mark the V1 path at its entry. Add an emulator-use/browser-IDE guide, with explicit save/export behavior and basic troubleshooting. Standardize the setup flow while retaining honest tested-platform information.

**Done when:** a new developer can choose browser or desktop, run a game, change one line, find an error, and retain/export their work without following an obsolete API page.

### Change 3: Separate current contracts from development history

Create a history index, archive shipped plans/investigations, and extract concise accepted decisions and reusable debugging lessons. Fix branch-based prerequisites and preserve unverified hardware status. Clean TODO.md into current open work. Redirect/pointer old public paths before moving authoritative pages into clearer categories.

**Done when:** every active page is indexed, every plan has an explicit state, archived pages name their replacements, and search/navigation no longer presents old designs as current instructions.

### Change 4: Finish contributor and hardware runbooks

Add short emulator/tests/tools entry points. Expand rotor/base/workbench READMEs and a hardware index. Put the first-flash/update/recovery decision table in one place; route supported flashing through the Makefile. Document release-bundle/base operation and actual troubleshooting. Record the supported MicroPython/IDF versions or revisions needed to reproduce builds.

**Done when:** a contributor knows which checks apply, and a hardware operator has a complete sequence with expected results without hunting through source files or historical incident logs. Validate procedures on their promised platforms/boards before marking them verified.

### Change 5: Extend publication and automate the missing checks

Expand the existing Sphinx site to cover maintained first-party guides/internals, with one audience-based navigation and search. Add docs build/local link checks to CI, retain executable tutorial checks, and schedule external-link checks. Make the documentation build command canonical and easy to discover. Keep generated HTML and runtime bundles out of Git.

**Done when:** all maintained docs are reachable and locally checked, examples still run, and broken references fail before publication. History can remain available but excluded from the normal tutorial navigation.

### Change 6: Finish asset and low-value cleanup

Check consumers of root `index.html` and `polar-coords.png` before removing them. Optimize oversized photo derivatives, add meaningful alt text and mechanical metadata, and improve screenshot determinism. Preserve original assets and credits. Confirm old public links still land somewhere useful.

**Done when:** no new broken links, no required attribution/data lost, no duplicate stale emulator entry page, and documentation media has a clear purpose and provenance.

These are separate concerns and should be separate commits or small PRs. The first two changes bring the largest immediate benefit; folder moves come later.

## Ongoing maintenance rules

- One canonical page per task/contract; other pages link to it.
- Current reference describes current code. Plans do not silently become reference.
- Code changes that affect documented behavior update the relevant contract and examples in the same PR.
- Prefer runnable examples or literalinclude from tested source to independent copies.
- Record measurements with hardware/runtime/renderer revision and distinguish observations from hypotheses.
- Do not call host-tested behavior hardware-verified or deployed without evidence.
- Keep short start pages; put exact formats and unusual troubleshooting in linked reference/runbooks.
- Preserve attribution, original assets, and useful hardware investigation evidence.
- Minimize redirects/stubs over time, but do not break established links just to tidy filenames.

## File-by-file inventory

Every tracked first-party Markdown file is listed below. “Archive” means remove from the normal current reading path while preserving useful context and evidence. “Remove candidate” requires a consumer/attribution check first.


### Project entry points

| File | Disposition | Specific comment |
|---|---|---|
| [AGENTS.md](../../AGENTS.md) | Keep concise | Useful invariants and repository map. Link a human contributor guide; keep detailed operations in canonical guides rather than expanding this file. |
| [README.md](../../README.md) | Shorten and reorient | Add direct browser/docs/start links, choose a VS2 starter, move renderer comparison details, improve image descriptions. |
| [TODO.md](../../TODO.md) | Prune and normalize | Keep current open work with concrete next actions; verify and remove completed entries, duplicate plans, and stale feature requests. |
| [docs/README.md](../README.md) | Rebuild navigation | Make the audience split practical: browser/desktop start, VS2 tutorial, assets/packages, console operation, contribution, internals, explicit legacy/history. |

### Setup, developer guides and superseded root proposals

| File | Disposition | Specific comment |
|---|---|---|
| [docs/developers-guide.md](../developers-guide.md) | Split | Extract shared current game conventions; label and move the V1 API tutorial. Put revision-2 metadata in usable VS2 examples. |
| [docs/emulator-setup.Linux.md](../emulator-setup.Linux.md) | Merge shared flow | Keep Linux dependencies, identify tested distributions/versions, add expected start behavior and links to common troubleshooting. |
| [docs/emulator-setup.Windows.md](../emulator-setup.Windows.md) | Merge shared flow; verify | Clarify bundled MicroPython, virtual environment and FFmpeg setup; validate the Python requirement instead of preserving an unexplained >3.13 claim. |
| [docs/emulator-setup.macOS.md](../emulator-setup.macOS.md) | Merge shared flow; verify | Retain platform dependencies; cover FFmpeg and architecture-independent Homebrew discovery, and identify which macOS/runtime combinations were tested. |
| [docs/ota-upgrade-plan.md](../ota-upgrade-plan.md) | Archive; retain pointer | Already labeled superseded. Move full historical A/B proposal out of the developer root; point to current OTA architecture/runbook. |
| [docs/vs2-api-guide.md](../vs2-api-guide.md) | Reduce to compatibility pointer | Keep old links working. Move useful revision migration table and documentation-build instructions to their dedicated current pages. |
| [docs/vs2-api-rework-proposal.md](../vs2-api-rework-proposal.md) | Archive; extract design record | Implementation-start status is stale. Preserve accepted revision-2 decisions and unique requirements; remove obsolete implementation snapshots from active reading. |

### Internals and engineering history

| File | Disposition | Specific comment |
|---|---|---|
| [docs/internals/README.md](README.md) | Rebuild navigation | Index every maintained page by subsystem/task; fix solved-incident status; link a dedicated history index and browser-specific contributor route. |
| [docs/internals/base-control-api.md](base-control-api.md) | Keep as reference | Useful narrow command contract. Link from the base runbook and host registry; keep ownership and hardware-verification scope explicit. |
| [docs/internals/building.md](building.md) | Make canonical | Fix docs link; reconcile recovery NVS behavior, centralize toolchain requirements and flash decision table, link board registration and expected results. |
| [docs/internals/deploying-web-emulator.md](deploying-web-emulator.md) | Keep as operations | Good source/output and generated-file guidance. Distinguish repository roots and link from component docs; avoid duplicating it in user onboarding. |
| [docs/internals/emulator-audio.md](emulator-audio.md) | Rewrite current contract | Keep current architecture/status; replace incompatible proposal framing/opcodes, add real platform support and fidelity limits, move rollout history aside. |
| [docs/internals/emulator-performance.md](emulator-performance.md) | Keep as dated case study | Preserve measurements and methodology with revision/environment. Extract the repeatable comparison workflow into emulator use and add an index link. |
| [docs/internals/game-packages.md](game-packages.md) | Split guide/reference | Add an end-to-end packaging guide; retain format/installation contracts, remove branch assumptions and nonexistent dev-emulator target, preserve unverified hardware checklist. |
| [docs/internals/history/design-notes.md](history/design-notes.md) | Remove candidate | Sparse historical roster/behavior notes. Check unique attribution or requirements; otherwise remove from maintained docs rather than translating or expanding it. |
| [docs/internals/history/game-layout-migration.md](history/game-layout-migration.md) | Keep as history | Mark functionally complete and superseded; current catalog/menu/path conventions belong in the assets guide, not the old migration recommendations. |
| [docs/internals/host-protocol.md](host-protocol.md) | Correct normative contract | Document emitted VS2 transport version 3 and older compatibility; complete or link install/calibration/profiler messages and distinguish API revision from transport version. |
| [docs/internals/input-protocol-v2.md](input-protocol-v2.md) | Keep contract; archive rollout | Correct physical/local connection diagram and current frame terminology; separate stable command/RESYNC semantics from obsolete implementation outline. |
| [docs/internals/menu-sprite-corruption.md](menu-sprite-corruption.md) | Archive as resolved | Lead with final third cause, fix and hardware evidence. Preserve rejected hypotheses and logs as history; correct the internals index. |
| [docs/internals/native-app-handoff.md](native-app-handoff.md) | Merge then archive | Move current launch/return ownership to on-device architecture; archive split-IDF/combined-image workflow and unsupported command options. |
| [docs/internals/on-device-design.md](on-device-design.md) | Keep as architecture | Make this the native-app/recovery/partition overview; link operational recipes and wire contracts rather than retaining competing build instructions elsewhere. |
| [docs/internals/ota-progress-rings-plan.md](ota-progress-rings-plan.md) | Archive as implemented | Preserve the explicitly retained original request and outcome; current progress behavior should be linked from the OTA guide. |
| [docs/internals/ota-ring-sprite-corruption.md](ota-ring-sprite-corruption.md) | Archive as resolved | Preserve successful hardware validation, buffer/type/initialization lessons and investigation evidence; separate final result from superseded hypotheses. |
| [docs/internals/ota.md](ota.md) | Split runbook/reference | Keep rollback and failure evidence. Reconcile flash hashing, file-cache writers, recovery provisioning and oversized example; move session narrative to history. |
| [docs/internals/pov-color-pipeline.md](pov-color-pipeline.md) | Keep; improve route | Strong shared-pipeline explanation and calibration contract. Link from workbench/base operations, separate calibration procedure from detailed format/performance explanation. |
| [docs/internals/remote-workbench-access.md](remote-workbench-access.md) | Keep as runbook | Replace feature-branch prerequisite with current revision/capabilities; retain exact connection, ownership and recovery details with verified-environment status. |
| [docs/internals/rom-format.md](rom-format.md) | Complete normative contract | Add per-strip glyph-length/UTF-8 trailer and consumer compatibility; preserve compression/audio separation and link the unresolved sentinel issue. |
| [docs/internals/rom-width-sentinel.md](rom-width-sentinel.md) | Keep active; update audit | Encoding problem remains. Mark JS/glyph sub-items now complete and date snapshot counts; do not imply the incompatible replacement already shipped. |
| [docs/internals/vs2-api-plan.md](vs2-api-plan.md) | Archive; extract open work | Old module, lifecycle and payload examples conflict with revision 2. Preserve accepted ownership rationale; move truly unfinished milestones into active issues/proposals. |
| [docs/internals/vs2-hardware-acceptance.md](vs2-hardware-acceptance.md) | Keep as acceptance runbook | Useful hardware gates and separate timing budgets. Replace old implementation-branch prerequisite; label actual completed versus pending validation without inferring deployment. |
| [docs/internals/web-emulator-architecture.md](web-emulator-architecture.md) | Refocus and correct | Disambiguate vsdk/emulator from website/emulator, update platform paths, move native-app sections, preserve pointer transport invariant and heap regression procedure. |
| [docs/internals/web-ide-integration.md](web-ide-integration.md) | Replace proposal with current contract | Document implemented workspace/path/persistence behavior; correct Monaco source; isolate unimplemented GitHub and alternative architecture ideas as pending proposals. |
| [docs/internals/workbench.md](workbench.md) | Split; reconcile status | Short wiring/run guide plus telemetry reference. Fix the five broken relative links plus status/discovery/frame/clock inconsistencies and route flashing through serialized Makefile targets. |

### VS2 teaching and API reference

| File | Disposition | Specific comment |
|---|---|---|
| [docs/vs2/design-notes.md](../vs2/design-notes.md) | Keep; correct claims | Strong motivation for bounded objects and reuse. Correct framebuffer/deadline model and distinguish scene sealing from arbitrary Python allocation. |
| [docs/vs2/glossary.md](../vs2/glossary.md) | Keep; align guarantees | Useful linked vocabulary and correct image/audio separation. Match renderer and GC/allocation wording to current implementation and its limits. |
| [docs/vs2/going-further.md](../vs2/going-further.md) | Keep; improve cross-links | Good advanced patterns, direct cell writes, glyph tables and image handles. Link direct writes from budgets and link asset YAML conventions. |
| [docs/vs2/index.md](../vs2/index.md) | Keep as game-development landing | Good tutorial/reference/glossary structure. Link current assets/packages and browser/desktop setup; make the revision-2 scope explicit at entry. |
| [docs/vs2/reference/drawables.md](../vs2/reference/drawables.md) | Keep generated reference | Retain docstring-backed methods and explanatory diagrams. Add links to mutation/allocation and glyph/asset constraints where readers make hot-loop choices. |
| [docs/vs2/reference/errors.md](../vs2/reference/errors.md) | Keep | Good diagnostic table and actionable failures. Retain concrete remedies, current budgets and limitations; link packaging/image-id troubleshooting where relevant. |
| [docs/vs2/reference/index.md](../vs2/reference/index.md) | Keep | Helpful cheat sheet and task mapping. Keep services/module list in sync, and link detailed caveats rather than lengthening the cheat sheet. |
| [docs/vs2/reference/scene.md](../vs2/reference/scene.md) | Keep | Preserve lifecycle diagram and generated hooks; align setup/seal/transition/timer ownership with the current runtime and tested chapter examples. |
| [docs/vs2/reference/services.md](../vs2/reference/services.md) | Keep | Maintain source-backed controls/audio/base/display/save services. Link operational input/audio/base contracts without bringing hardware setup into API reference. |
| [docs/vs2/tutorial/budgets.md](../vs2/tutorial/budgets.md) | Correct guarantees | Replace false comma-indexing allocation claim, define what sealing guarantees, and separate object/cell/image budgets from target timing and heap measurements. |
| [docs/vs2/tutorial/display.md](../vs2/tutorial/display.md) | Keep; correct provenance | Strong coordinate/projection teaching. Correct generated-geometry claim and link actual paired definitions; keep target constants accessed through VS2. |
| [docs/vs2/tutorial/first-game.md](../vs2/tutorial/first-game.md) | Keep as default starter | Good runnable introduction with required revision metadata. Link setup and asset packaging at the point a reader creates their own game. |
| [docs/vs2/tutorial/index.md](../vs2/tutorial/index.md) | Keep; correct renderer claim | Preserve cumulative game flow, prerequisites and finished result. Remove no-framebuffer assertion and route readers here from root onboarding. |
| [docs/vs2/tutorial/pools.md](../vs2/tutorial/pools.md) | Keep | Useful fixed-capacity reuse pattern. Explain object-reuse guarantees precisely; retain real chapter source and tests rather than parallel handwritten snippets. |
| [docs/vs2/tutorial/scenes-and-input.md](../vs2/tutorial/scenes-and-input.md) | Keep | Good state-transition/input/score progression. Cross-link traceback location and save behavior in the emulator; preserve executable chapter checks. |
| [docs/vs2/tutorial/sprites.md](../vs2/tutorial/sprites.md) | Keep | Clear frame/movement/collision teaching. Preserve visual examples and tested source; avoid broad claims that all fractional or timed updates allocate nothing. |
| [docs/vs2/tutorial/tilemaps-and-text.md](../vs2/tutorial/tilemaps-and-text.md) | Keep; connect constraints | Good tile/text/flip examples. Cross-link glyph trailer/font limits and the direct cell-buffer path for repeated updates. |

### Component, hardware, tooling and game READMEs

| File | Disposition | Specific comment |
|---|---|---|
| [apps/micropython/roms/README.md](../../apps/micropython/roms/README.md) | Keep; correct paths | Generated-ROM warning is useful. Correct grouped game discovery to games/*/*/images and link the current assets guide. |
| [emulator/chipsynth/README.md](../../emulator/chipsynth/README.md) | Update support/build guide | NES is implemented, alongside Genesis/SMS/GB/MSX desktop factories. Explain browser subset, fallback behavior, build requirements and measured fidelity limits. |
| [emulator/ffmpeg-win/README.md](../../emulator/ffmpeg-win/README.md) | Merge or replace with pointer | Too vague to help installation. Put supported binary discovery/configuration in Windows setup, retaining only a short local directory-purpose note. |
| [games/vsjam-oct25/peronjam/images/README.md](../../games/vsjam-oct25/peronjam/images/README.md) | Preserve jam context | Historical game-local explanation/attribution belongs with the game. Add a discoverability pointer if needed; do not restyle or translate jam history. |
| [games/vsjam-oct25/tincho_vrunner/code/README.md](../../games/vsjam-oct25/tincho_vrunner/code/README.md) | Preserve jam context | Keep original story/instructions with the game; make it discoverable from a catalog/local pointer rather than moving it into general API docs. |
| [hardware/base/README.md](../../hardware/base/README.md) | Expand operator guide | Document actual headless host, UART/controllers/audio, relay, supervision/logs, release bundle and OTA hosting; link exact command contracts. |
| [hardware/pre-voom/README.md](../../hardware/pre-voom/README.md) | Label historical | Keep experiment context and link current native-console integration; deciding whether to remove experiment source is outside a documentation cleanup. |
| [hardware/rotor/3dmodels/Mechanical Assembly.md](<../../hardware/rotor/3dmodels/Mechanical Assembly.md>) | Keep; fix links/metadata | Preserve photos/CAD context; repair root-relative image paths, link from hardware index, add drawing revision/material/compatibility provenance. |
| [hardware/rotor/README.md](../../hardware/rotor/README.md) | Replace obsolete sketch | Link supported board/toolchain/build/flash/provisioning path and project invariants; generic upstream clone instructions are insufficient for this target. |
| [hardware/workbench/README.md](../../hardware/workbench/README.md) | Keep; add quick start | Useful canonical pointer. Add board purpose, wiring/prerequisites, serialized build/flash/run steps and expected capture results without duplicating telemetry reference. |
| [tools/vs2_doc_images/README.md](../../tools/vs2_doc_images/README.md) | Keep; make repeatable | Good image/source/command map. Link from contributing; replace transient capture-machine notes and random reruns with controlled screenshot procedures when practical. |
| [web/README.md](../../web/README.md) | Keep; tighten cross-links | Good local component map. Use the real deployment link label, clickable bridge/regression references, current workspace contract and user-guide pointer. |

## Related files and assets

| Material | Comment and disposition |
|---|---|
| `.readthedocs.yaml`, `docs/vs2/conf.py`, `docs/vs2/Makefile`, `docs/vs2/requirements.txt` | Keep the working Sphinx/MyST/Furo toolchain. Widen publication deliberately, document one canonical build command, and add CI coverage. Keep documentation dependencies separate from runtime dependencies. |
| `tests/run_tests.py`, tutorial tests, `.github/workflows/` | Preserve existing chapter behavior and mpy-cross checks. Add missing docs/local-link checks rather than writing tests that merely repeat prose. Explain skipped/tool-dependent categories in contributor instructions. |
| `docs/vs2/tutorial/steps/`, `games/demos/tutorial_game/code/`, `tools/vs2_doc_images/examples/` | Keep executable teaching sources and screenshot examples. Prefer literalinclude from these over drifting copies; distinguish tested chapter behavior from syntax-only screenshot checks. |
| `tools/vs2_doc_images/capture.mjs`, SVG diagrams, image-generation scripts | Keep beside their README. Improve fixed-state captures and record renderer/runtime provenance when screenshots are regenerated. These are documentation tooling, not clutter. |
| Root `index.html` versus `web/index.html` | Keep `web/index.html` as the maintained browser UI. Check external consumers of the old root shell, then delete it or replace it with a small compatible redirect. |
| `docs/images/` and `docs/vs2/images/` | Preserve useful photographs/tutorial figures. Optimize web derivatives, give images meaningful alt text, and remove genuinely unused files only after checking consumers. |
| `docs/images/polar-coords.png` | No Markdown reference found; verify code/site consumers before removal. Do not confuse the presence of newer diagrams with proof that an old asset is unused everywhere. |
| `hardware/rotor/3dmodels/Axle adapter.pdf` and `Fan blade and slip ring support.pdf` | Preserve both source drawings, reviewed as rendered single-page images. Add adjacent part/material/units/revision/CAD/compatibility metadata; do not treat this prose audit as manufacturing validation. |
| CAD/electronics files and assembly photographs | Keep alongside the relevant hardware, expose them through the hardware index, and specify supported revision/source provenance. Avoid relocating originals solely for folder symmetry. |
| `system/shared/other/sounds/credits.txt`, `games/vsjam-oct25/2bam_sencom/sounds/2bam_sencom_audio_credits.txt` | Preserve attribution and source links. Credits are required context for assets, not superseded design documentation. |
| `web/smoke-test.html`, `tests/browser/remote-video-smoke.html`, `tests/browser/remote-video-server-smoke.html` | Keep diagnostic pages. Link their launch prerequisites, expected pass output and scope from the browser/remote-workbench contributor instructions; they are verification tools, not public user guides. |
| `requirements.txt`, `requirements-remote-workbench.txt` | Link the relevant dependency set from desktop and remote-workbench setup; keep optional gateway dependencies distinguishable from the main emulator environment. |
| `emulator/gamecontrollerdb.txt`, CMake files | Controller mappings and build inputs are runtime/build data, not obsolete prose. Preserve them; document their role only where useful. |
| Song/chart `.txt` files | Preserve runtime data; they are not prose documentation and should not be swept into an archival cleanup. |
| Source comments/docstrings and CLI `--help` definitions | Preserve close-to-code contracts. Link these from a small tools/contributor catalog; update stale factual comments with their associated code rather than duplicating complete flag manuals. |
| Generated ROMs, `web/runtime-manifest.json`, `web/runtime-bundle.json`, generated HTML | Build output, not editable documentation sources. Keep uncommitted and rebuild through the documented workflows. |

## Limits and follow-up verification

This review identifies concrete local contradictions and checks the documentation toolchain/examples. It does not establish that an external documentation deployment is currently reachable, that every OS setup works on a clean machine, or that hardware procedures work on every board revision. Those checks belong to the implementation phase before labeling corresponding instructions verified.

Deletion candidates are deliberately narrow. A historical proposal can be misleading in current navigation while still containing valuable requirements; archiving it with a replacement link is usually more useful than erasing it. Keep ownership/attribution evidence, resolved hardware lessons, and the still-open ROM encoding investigation.
