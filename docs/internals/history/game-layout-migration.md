# Game Layout Migration Plan

This document describes the target repository layout for moving each game into its own folder, while keeping the current runtime and emulator working during the migration.

The goal is simple:

- keep each game's code and content close together
- make it easier to find everything that belongs to a game
- reduce cross-repo hunting as the project grows
- preserve shared runtime code as a separate concern

## Current Status

The repository is now operating on the new layout:

- game code and assets live under `games/<slug>/`
- the default boot flow starts from `system/launcher/code`
- launcher-only art lives under `system/menu`
- shared non-game assets live under `system/shared`
- image manifests use `__images__.yaml`

The old `apps/images`, `apps/sounds`, and `apps/micropython/apps` layout has now been retired.

## Goals

- Each game gets one top-level folder.
- Game code lives in `code/`.
- Game images live in `images/`.
- Game sounds live in `sounds/`.
- Shared engine/runtime code stays outside game folders.
- The migration can happen incrementally.

## Non-Goals

- Rewriting game logic during the layout migration.
- Changing the Python app entrypoint convention.
- Hiding sound paths behind a new alias system right away.

For now, sound playback may continue to use explicit full paths such as `dome_defander/play1`.

## Target Layout

```text
vsdk/
  games/
    vyruss/
      code/
        __init__.py
        main.py
      images/
        __images__.yaml
        ...
      sounds/
        ...
      README.md
    dome_defander/
      code/
      images/
      sounds/
    tincho_vrunner/
      code/
      images/
      sounds/
    vsjam25/
      vortris/
        code/
        images/
        sounds/
  system/
    launcher/
      code/
      images/
      sounds/
    menu/
      images/
      sounds/
    shared/
      images/
      sounds/
  apps/
    micropython/
      roms/
      ventilastation/
```

## Folder Responsibilities

### `games/<slug>/code`

Contains the Python code for one game.

- Use a package directory even for games that are currently single-file apps.
- Keep the existing `main()` convention as the game entrypoint.
- Internal helper modules stay next to the game that uses them.

Examples:

- `games/dome_defander/code/...`
- `games/tincho_vrunner/code/...`
- `games/vyruss/code/...`
- `games/vsjam25/vortris/code/...`

### `games/<slug>/images`

Contains all image assets for one game.

- Includes `__images__.yaml`.
- Includes menu art only if that art is game-specific and used only by that game.
- Is the physical source of ROM generation for that game.

### `games/<slug>/sounds`

Contains all sound effects and music for one game.

- Games may keep using full sound paths that include the slug.
- No special indirection is required for the first migration phase.

### `system/menu`

Contains menu-only content and code-independent assets for the launcher.

This is where current `menu` assets logically belong.

### `system/shared`

Contains assets that are intentionally reused across multiple apps and are not owned by one game.

This is the likely destination for content currently grouped under names like:

- `other`
- shared fonts
- common splash screens
- common debug/tutorial assets

## Registry Design

The repo should gain a game registry, but it should stay small and focused.

The registry should not define:

- the Python entrypoint
- the ROM source folder
- the ROM name
- the Python package path

Those should all be derivable from the slug and the standard repo layout.

Suggested game definition:

```python
[
    "dome_defander",
    "vyruss",
    "vsjam25.vortris",
]
```

The main rule is that a slug maps to a folder path.

Examples:

- `dome_defander` -> `games/dome_defander`
- `vyruss` -> `games/vyruss`
- `vsjam25.vortris` -> `games/vsjam25/vortris`

From that slug, tooling should be able to derive:

- code folder
- image folder
- sound folder
- Python package import path

### Dotted slugs

The slug may contain dots to represent nested folders that group related games.

Example:

- slug: `vsjam25.vortris`
- folder: `games/vsjam25/vortris`

This keeps the game identifier stable while allowing the repository to group games by jam, collection, or author namespace.

### Derived package path

The loader should be able to derive the import package from the slug.

Examples:

- `dome_defander` -> `games.dome_defander.code`
- `vsjam25.vortris` -> `games.vsjam25.vortris.code`

The loader can then import that package and call `main()` without storing per-game package paths in the registry.

### Menu definitions live outside the game registry

Fields like `enabled` and `menu_group` are useful, but they should not live inside the game definitions themselves.

Instead:

- move menu definition logic out of `apps/micropython/main.py`
- create a dedicated launcher app
- let that launcher app define which games appear in which menu
- make the launcher app the default thing that boots

This keeps the game registry simple and keeps curation concerns in the launcher, where they belong.

## Runtime Expectations

The following conventions should remain stable across the migration:

- `main()` is the app entrypoint
- each game is responsible for loading its own ROMs
- sound and music calls may keep explicit paths

Examples:

- `director.music_play("dome_defander/play1")`
- `director.sound_play("vortris/encastre")`

This lets game logic remain mostly unchanged while files move around it.

## Shared Asset Policy

Not every current asset folder maps to a game.

The existing tree already contains shared or cross-cutting content:

- `menu`
- `other`
- `ventilagon`
- `laupalav`
- `milalhhl`

These should be classified before moving files.

Rules:

- If assets are used by only one game, move them into that game's folder.
- If assets are used by multiple games, move them into `system/shared`.
- If assets are only used by the launcher, move them into `system/menu`.
- Do not assign shared assets to an arbitrary game just to make the tree look tidy.

## Migration Phases

### Phase 1: Add the new structure without changing behavior

Status: complete

- Create `games/` and `system/` folders.
- Add the registry module.
- Add a launcher app.
- Keep existing code, image, and sound paths working.
- Update tooling so it can resolve both old and new locations.

This phase is about compatibility scaffolding.

### Phase 2: Migrate one pilot game

Status: complete

Pilot used:

- `dome_defander`

Pilot migration tasks:

- move code into `games/<slug>/code`
- move images into `games/<slug>/images`
- move sounds into `games/<slug>/sounds`
- update the registry slug list
- verify ROM generation
- verify emulator loading

### Phase 3: Migrate simple single-file games

Status: complete

Examples:

- `vyruss`
- `vajon`
- `vance`
- `ventap`
- `vugo`
- `vong`

For each one:

- convert the file into a package directory under `code/`
- keep `main()` as the stable entrypoint
- move assets alongside it

### Phase 4: Migrate special cases

Status: complete for the current game set

These need extra care:

- gallery-driven apps
- apps that depend on shared asset pools
- apps whose current asset names do not match their code module cleanly
- launcher and menu behavior currently embedded in `main.py`

Examples:

- `gallery`
- `calibrate`
- `credits`
- `debugmode`
- `tutorial`
- `settings`
- `upgrade`

These may belong in `system/` rather than `games/`.

### Phase 5: Remove compatibility paths

Status: complete

Now that all games and system apps are migrated:

- old `apps/images/*` and `apps/sounds/*` trees are gone
- old `apps/micropython/apps/*` imports are gone
- runtime loading now resolves from `games/` and `system/`

## Tooling Changes Needed

The migration will require changes in these areas:

### ROM generation

Current tooling historically assumed image roots under `apps/images`.

It should instead:

- discover `__images__.yaml` files under `games/*/images` and `system/*/images`
- or derive image roots from game slugs and the standard folder layout

### Web audio lookup

Current browser audio lookup historically assumed `apps/sounds/<name>`.

Since full sound paths are acceptable for now, the browser can keep resolving explicit names, but the root path must eventually understand new sound locations such as:

- `games/<slug>/sounds/...`
- `system/shared/sounds/...`
- `system/menu/sounds/...`

### Loader / launcher

Current launcher configuration is hand-maintained in `main.py`.

It should move toward:

- a dedicated launcher app
- launcher-owned menu definitions
- a loader that derives the package path from the slug and calls `main()`

## Naming Rules

To reduce future friction:

- folder slug should be the canonical identifier
- dotted slugs should map to nested folders
- game sound paths should usually start with the slug
- package paths should be derived from the slug

Avoid special-case metadata unless the standard layout truly cannot express the game.

## Recommended First Implementation Slice

The safest first slice is:

1. add the registry
2. add a launcher app and move menu definitions into it
3. update ROM tooling to derive image roots from slugs or discovery
4. update the loader to derive the package path from the slug
5. migrate one pilot game

This yields a working end-to-end proof without forcing a big-bang repo move.

## Remaining Cleanup

The big structural move is done. The remaining work is narrower:

- decide how aggressively to organize future games into grouped dotted-slug folders
- simplify docs and tooling further now that the legacy layout is no longer present
- move any remaining system-owned code into `system/` if we want an even harder separation later

## Current Recommendation

Treat the migration as functionally complete for day-to-day development.

New work should go into `games/<slug>/` or `system/`, and remaining cleanup should focus on deleting compatibility code only when it stops buying us useful safety.
