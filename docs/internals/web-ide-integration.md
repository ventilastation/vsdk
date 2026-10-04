# Browser workspace contract

**Status:** implemented browser workspace/editor integration. The source of truth
is `web/app.js`, `web/micropython-bridge.js`, and `web/wasm-worker.js`.
For visitors, use the [browser guide](../guides/browser.md).

## Host API

The browser exposes `window.VentilastationWebEmulator` after the
`ventilastation:ready` event. Workspace methods return promises:

| Method | Purpose |
|---|---|
| `listProjectFiles(path = ".")` | List workspace files |
| `readProjectFile(path, encoding = "utf8")` | Read text or base64 data |
| `writeProjectFile(path, content, encoding = "utf8")` | Update the worker filesystem and the page's overlay |
| `deleteProjectFile(path)` | Remove a workspace file |
| `applyProjectSnapshot(files = [])` | Replace the overlay with `{path, content, encoding}` entries |
| `restartRuntime({full = true, autostartSlug = null})` | Restart with the workspace overlay and optional game slug |
| `getRuntimeInfo()` | Inspect runtime state |

Use `games/<group>/<name>/code/<name>.py` for game code. Paths beginning with
`games/`, `system/`, or `apps/` resolve from the worker filesystem root.
Other relative paths resolve beneath the configured `fsRoot` (normally
`/apps/micropython`). `__runtime_roms__/` resolves to the runtime's ROM directory.
Do not assume every editable file is relative to `/apps/micropython`.

## Save, rebuild and restart

Monaco and Piskel are vendored under `web/vendor/`, not fetched from a CDN.
**Save** writes the current file. Saving PNGs/manifests rebuilds the affected
ROM through the workspace ROM builder. **Save + Run** saves the current file
and restarts into its game's slug; it does not automatically save every dirty tab.
**New Game** creates VS2 revision-2 code and metadata.

The bridge holds the overlay in a JavaScript Map and reapplies it when restarting
the worker. This preserves edits across runtime restarts within the same page,
not across browser reloads. Saving does not modify the deployed SDK, local files,
or a GitHub repository. Copy editable sources to a durable checkout before leaving.

The optional **Push to console** action builds a distribution package and calls
supported package-server endpoints. It is not GitHub synchronization or a source
backup. GitHub clone/fetch/commit/push was part of the superseded IDE proposal;
those actions are not implemented by the current editor.

Runtime-bundle generation and publishing are documented in
[deploying the web emulator](deploying-web-emulator.md). Do not hand-edit the
website's generated `emulator/` copy.
