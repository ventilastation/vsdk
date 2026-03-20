# AGENTS

This file captures the standing guidance and preferences the user has given during work on this project.

## Scope Boundaries

- Do not change game code under `apps/micropython/apps` in this branch.
- Keep changes confined to `apps/micropython/ventilastation` and the web emulator paths unless the user explicitly says otherwise.
- When fixing emulator/runtime behavior, prefer infrastructure changes over app-specific fixes.

## Web Emulator UX

- Move `Keyboard Arrows + Space/O/P/Esc` outside the debug panel, directly under the `Ventilastation Emulator` title.
- Add a bit more spacing between that keyboard hint and the `Show debug` button.
- Show a button to stop the rendering.
- On mobile browsers, provide controls below the display area:
  - a directional control on the left
  - four buttons on the right
  - the directional control should use the usual mobile-game pattern: hold with the left thumb and drag

## Error Handling

- Errors in any `Scene.step`, `Scene.on_enter`, or `Scene.on_exit` should be shown prominently in the browser.
- The browser UI should offer a way to open the debugger when those errors happen.

## Deployment / Hosting

- Fix asset paths so the web emulator can be served from the site root.
- Prefer deploy-friendly solutions for static hosting.
- For GitHub Pages / Jekyll hosting, prefer an in-repo workaround that bundles runtime assets into one archive/blob instead of relying on individual Python package files being published.

## Version Control / Workflow

- Commit changes per concern when practical.
- Before committing, compare branch history with `main` if needed to confirm whether game code changed.
- Keep game code untouched on this branch unless the user explicitly changes that rule.

## Documentation / Traceability

- Record important standing instructions in repo-visible documentation when useful, so future sessions can follow the same boundaries.
