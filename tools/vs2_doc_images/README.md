# VS2 documentation images

Regenerates everything in `docs/vs2/images/`: emulator screenshots of the
tutorial examples and of the finished tutorial game, and the diagrams.

The committed set was taken with the emulator's **2D canvas fallback** in
headless Chromium, because that machine had no usable WebGL. The WebGL renderer
looks nicer (soft glow, round LEDs), so retake them on a machine with a GPU; see
[Retaking everything with WebGL](#retaking-everything-with-webgl).

## The images

This table comes from `node capture.mjs --list`.

| Image | Kind | Source | Command | Used in |
|---|---|---|---|---|
| `display-axes.png` | diagram | `diagrams/display-axes.svg` | `node capture.mjs display-axes` | tutorial/display.md |
| `draw-order.png` | diagram | `diagrams/draw-order.svg` | `node capture.mjs draw-order` | tutorial/display.md |
| `layer-tree.png` | diagram | `diagrams/layer-tree.svg` | `node capture.mjs layer-tree` | reference/drawables.md |
| `scene-lifecycle.png` | diagram | `diagrams/scene-lifecycle.svg` | `node capture.mjs scene-lifecycle` | reference/scene.md, tutorial/first-game.md |
| `strip-ship.png` | diagram | `diagrams/strip-ship.svg` | `node capture.mjs strip-ship` | tutorial/first-game.md |
| `strip-trench.png` | diagram | `diagrams/strip-trench.svg` | `node capture.mjs strip-trench` | tutorial/tilemaps-and-text.md |
| `first-game.png` | emulator screenshot | `examples/first.py` | `node capture.mjs first` | tutorial/first-game.md |
| `first-game-moved.png` | emulator screenshot | `examples/first.py` | `node capture.mjs first` | tutorial/first-game.md |
| `display-angles.png` | emulator screenshot, annotated | `examples/angles.py` | `node capture.mjs angles` | tutorial/display.md |
| `display-projections.png` | emulator screenshot, annotated | `examples/projections.py` | `node capture.mjs projections` | tutorial/display.md |
| `display-layers.png` | emulator screenshot | `examples/layers.py` | `node capture.mjs layers` | tutorial/display.md |
| `labels-flips.png` | emulator screenshot, annotated | `examples/flips.py` | `node capture.mjs flips` | tutorial/tilemaps-and-text.md |
| `game-title.png` | emulator screenshot | `games/demos/tutorial_game (played)` | `node capture.mjs game` | tutorial/scenes-and-input.md |
| `game-play.png` | emulator screenshot | `games/demos/tutorial_game (played)` | `node capture.mjs game` | tutorial/index.md, tutorial/tilemaps-and-text.md |
| `game-over.png` | emulator screenshot | `examples/gameover.py` | `node capture.mjs gameover` | tutorial/scenes-and-input.md |
| `sprites-frames.png` | emulator screenshot, annotated | `examples/frames.py` | `node capture.mjs frames` | tutorial/sprites.md |
| `pools.png` | emulator screenshot | `examples/pools.py` | `node capture.mjs pools` | tutorial/pools.md |
| `tilemaps.png` | emulator screenshot | `examples/tilemap.py` | `node capture.mjs tilemap` | tutorial/tilemaps-and-text.md |
| `labels.png` | emulator screenshot | `examples/labels.py` | `node capture.mjs labels` | tutorial/tilemaps-and-text.md |
| `budgets-legibility.png` | emulator screenshot, annotated | `examples/legibility.py` | `node capture.mjs legibility` | tutorial/budgets.md |

Notes on specific images:

- **`sprites-frames.png`** uses `mario_runs.png` from the `vugo` game, not the
  tutorial game's art, because a walking character's frames differ visibly. The
  sprites are spaced 24 columns apart (each is 20 wide) so none overlap; retake it
  and check that after changing the spacing or the art.
- **`game-play.png`** is the real game after pressing A on the title, and the
  enemies appear at random places. Run `node capture.mjs game` again until the
  picture shows several enemies at different depths and the ship still alive (the
  script does not dodge, so an enemy can hit the ship first and the shot then shows
  the game-over screen). `game-title.png` is written by the same run.
- **`game-over.png`** does not play the game: `examples/gameover.py` opens the
  game's own `GameOver` scene with a fixed score of 130 (13 enemies dodged), so it is the
  same every time.
- **Annotated** images have text drawn over the screenshot (`labels` in
  `capture.mjs`). The text is placed in empty parts of the disc and in coordinates
  of an 880 pixel square, so it should still sit in the same place with the WebGL
  renderer. Check each one by eye after a retake: the WebGL LEDs are a little
  larger and softer, and a label must not overlap a drawing.
- **`first-game-moved.png`** holds the left button for 700 ms, so the ship's
  position depends on the emulator's frame rate. Anywhere on the upper left of
  the disc is fine.
- The **diagrams** are SVG, drawn in the same browser, and do not depend on the
  renderer. They only need regenerating when an SVG changes.

## Retaking everything with WebGL

You need Node 18 or newer, Python 3, a Chrome or Chromium that has WebGL (any
desktop browser install does), and a checkout of this repository.

1. **Build what the browser runs.** The emulator runs the Python in
   `web/runtime-bundle.json`, and the ROMs it contains were built from the games'
   PNGs, so regenerate both from the current tree first:

   ```sh
   make generate-roms        # needs Python 3.12+ with Pillow, numpy and PyYAML
   make web-runtime-bundle
   ```

   Skipping this shows the old runtime. The tutorial game, in particular, needs the
   director fix that gives switched-to scenes their app markers, or its game
   scene will render through the legacy sprite path.

2. **Serve the web emulator**, and leave it running:

   ```sh
   cd web && python3 -m http.server 8765
   ```

3. **Install the script's one dependency** (once):

   ```sh
   cd tools/vs2_doc_images && npm install
   ```

   If you do not have a Chrome you can point at, let Playwright download one:
   `npx playwright-core install chromium` (then leave `CHROMIUM` unset).

4. **Take the screenshots** with the WebGL renderer. `GPU=1` stops the script from
   forcing Chromium onto its software renderer, and `RENDERER` picks what draws
   the disc:

   ```sh
   # the WebGL renderer, with the CPU compositor (what most people see)
   GPU=1 RENDERER=webgl CHROMIUM=/path/to/chrome node capture.mjs

   # or the GPU shader compositor
   GPU=1 RENDERER=shader CHROMIUM=/path/to/chrome node capture.mjs
   ```

   Add `HEADFUL=1` to watch the browser window if a run hangs or the picture is
   blank, since some systems only give WebGL to a visible window. One image or
   example at a time works too: `node capture.mjs pools tilemap`.

5. **Review** every image in `docs/vs2/images/` (the table above lists them),
   rerun `game` until `game-play.png` is a good frame, then build the docs
   (`pip install -r docs/vs2/requirements.txt && sphinx-build -W docs/vs2 /tmp/out`)
   and commit the images.

Other environment variables: `BASE` (emulator URL, default
`http://localhost:8765`), `OUT` (output directory, default `docs/vs2/images`),
`CHROMIUM` (browser binary), `DEBUG=1` (prints the page layout before each shot).
`RENDERER=2d`, the default, is the headless-friendly canvas fallback.

## How it works

- `examples/<name>.py` are small scenes written against the VS2 API. Each is
  loaded into the browser emulator's workspace as `games/docs/<name>` (nothing is
  written into the repo's `games/` tree), its ROM is built in the browser, the
  runtime is restarted into it, and the stage is saved after the scripted key
  presses listed in `capture.mjs`. Some screenshots get text labels drawn over
  them (`labels` in `capture.mjs`).
- The `game` entry loads the finished tutorial game from `games/demos/tutorial_game`
  as it is in the repo, and plays it with scripted key presses.
- A screenshot is of the emulator's stage (the `.stage-display` element: the dark
  panel with the black disc inset in it), so the edge of the fan is visible. The
  base-controls preview and the fullscreen button are hidden for the shot.
- `diagrams/*.svg` are rendered to PNG with the same browser. `{{art:...}}` in an
  SVG is replaced with a PNG from `games/` as a data URI.
- The art comes from the games under `games/` (`ART` in `capture.mjs`), except
  `art/clouds.png`, which `make_clouds.py` draws for the layers example. The
  tutorial game's tileset, `games/demos/tutorial_game/images/trench.png`, is drawn
  by `make_trench_tiles.py` (dark hull plating with a few lit structures); rerun it
  after changing a tile, then retake the images that use it.
- Before each screenshot the emulator is paused, the way it pauses when its tab is
  hidden, and unpaused afterwards. A frame that lights the whole disc is slow to
  composite, and with the loop running a screenshot could take a minute, which is
  long enough for a game's 30 second idle timeout to send it back to the launcher.
