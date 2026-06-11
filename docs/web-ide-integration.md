# Web IDE Integration

This note captures a practical way to add a browser IDE to the web emulator without turning the emulator into a Git client, editor, and project manager all at once.

## Target user flow

1. The user opens the browser emulator page.
2. The user clones or imports a game project from GitHub.
3. The project appears in a web IDE file tree.
4. The user edits source files in the IDE.
5. The IDE writes those files into the emulator workspace.
6. The emulator restarts or hot-reloads the runtime.
7. The user tests the game immediately in the emulator.
8. The user commits and pushes changes back to GitHub.

## Recommended split

Keep the feature split into three layers:

1. GitHub sync layer
   - clone, fetch, commit, push
   - auth handling
   - branch and conflict UX

2. IDE workspace layer
   - file tree
   - editor tabs
   - dirty state
   - save/revert/rename/create/delete

3. Emulator runtime layer
   - load project files into MicroPython
   - restart the runtime
   - stream frames back into the preview

The web emulator should own only layer 3 directly.

## Why this split matters

The current browser runtime already boots MicroPython inside `vsdk/web/wasm-worker.js` and owns the in-browser filesystem mounted at `/apps/micropython`.

That means the lowest-friction integration is:

- treat the cloned game repo as a workspace snapshot
- mirror the editable files into the worker filesystem
- restart the runtime to pick up changes

This avoids rebuilding `runtime-bundle.json` for every edit, which is important because the bundle is a deployment artifact, not a good live-edit loop.

## New emulator-side API

The browser host now exposes:

- `window.VentilastationWebEmulator`

That API is intended to be consumed by a future embedded IDE pane or by another page shell that composes the emulator with an editor.

The current built-in editor choice is Monaco.

Available methods:

- `listProjectFiles(path = ".")`
- `readProjectFile(path, encoding = "utf8")`
- `writeProjectFile(path, content, encoding = "utf8")`
- `deleteProjectFile(path)`
- `applyProjectSnapshot(files)`
- `restartRuntime({ full = true })`
- `getRuntimeInfo()`

All project paths are relative to the MicroPython project root:

- `/apps/micropython`

So an IDE can write:

- `apps/my_game.py`
- `ventilastation/menu.py`
- `roms/my_game.rom`

without needing to know the worker's absolute filesystem layout.

## Suggested browser architecture

### Option A: Embedded IDE in the same page

Best for:

- the smoothest single-page workflow
- live preview beside the editor

Suggested shape:

- left pane: repo tree
- center pane: code editor
- right pane: emulator preview
- top bar: clone, branch, commit, push, restart

The IDE writes through `window.VentilastationWebEmulator.writeProjectFile(...)` and calls `restartRuntime()` after save or on an explicit Run action.

The current implementation starts here with:

- a Monaco panel inside the emulator sidebar
- a workspace file list
- explicit `Save` and `Save + Run` actions
- lazy Monaco loading from a CDN

### Option B: Parent shell + iframe

Best for:

- keeping the emulator page mostly independent
- making the IDE app easier to iterate on

Suggested shape:

- parent app hosts the IDE and GitHub UX
- emulator runs in an iframe
- parent calls the iframe's `contentWindow.VentilastationWebEmulator`

This keeps the editor UI from mixing too deeply with `vsdk/web/app.js`.

## GitHub integration notes

For GitHub support, the browser app should manage a real repository workspace rather than a loose file list.

That layer should handle:

- clone by repository URL
- branch selection
- status/diff
- commit creation
- push with auth

Then it should publish the checked-out working tree into the emulator via:

- `applyProjectSnapshot(files)`
- `restartRuntime()`

## Storage strategy

There are two useful storage models:

1. Session-only
   - simplest
   - good for early prototyping
   - project disappears on refresh

2. Persistent browser workspace
   - better real user experience
   - keeps cloned repos and unsaved edits across reloads
   - better fit for Git clone/push workflows

For a serious GitHub workflow, persistent browser storage is the better target.

## Live-edit behavior

There are two reasonable execution models:

1. Save then restart
   - simplest and safest
   - easiest for MicroPython bootstrapping

2. Incremental hot-reload
   - faster feeling
   - much harder to keep correct with scene state and imports

Start with save then restart. It matches the current runtime architecture better.

## Suggested rollout

1. Build a minimal browser workspace UI around the new API
2. Add editor integration and file tree
3. Add repo import/export in browser storage
4. Add GitHub clone/fetch/commit/push
5. Add branch and diff UX
6. Only then consider hot-reload or collaboration features

## Important caveat

The current workspace API lives in memory inside the bridge and worker lifecycle. A future production GitHub workflow should back that state with persistent browser storage so a worker restart or page reload does not lose the checked-out project.
