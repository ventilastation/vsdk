# VS2 documentation images

Regenerates everything in `docs/vs2/images/`: emulator screenshots of the
tutorial examples, and the diagrams.

```sh
# 1. serve the web emulator
cd web && python3 -m http.server 8765

# 2. in another shell
cd tools/vs2_doc_images
npm install
node capture.mjs            # everything
node capture.mjs pools      # one example or diagram, by name
```

Needs a Chromium that Playwright can drive. Set `CHROMIUM=/path/to/chromium`
if it is not at `/opt/pw-browsers/chromium`; `BASE` and `OUT` override the
emulator URL and the output directory.

## How it works

- `examples/<name>.py` are small scenes written against the VS2 API. Each is
  loaded into the browser emulator's workspace as `games/docs/<name>`
  (nothing is written into the repo's `games/` tree), its ROM is built in the
  browser, the runtime is restarted into it, and the polar canvas is saved
  after the scripted key presses listed in `capture.mjs`. Some screenshots get
  text labels drawn over them (`labels` in `capture.mjs`).
- `diagrams/*.svg` are rendered to PNG with the same browser. `{{art:...}}`
  in an SVG is replaced with a PNG from `games/` as a data URI.
- The art comes from the games under `games/alecu/` (`ART` in `capture.mjs`),
  except `art/clouds.png`, which `make_clouds.py` draws for the layers example.
