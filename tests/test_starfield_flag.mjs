// A scene that does not ask for the starfield gets none: the browser
// renderers draw the background stars only while frame.starfield is not false.

import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const render = require("../web/led-render-core.js");
const shader = require("../web/scene-shader-core.js");

function litPixels(frame) {
  const pixels = render.computeLedFramePixels(frame, new Map(), null);
  let lit = 0;
  for (let index = 0; index < pixels.length; index += 4) {
    if (pixels[index] || pixels[index + 1] || pixels[index + 2]) {
      lit += 1;
    }
  }
  return lit;
}

assert.ok(litPixels({ frame: 7, sprites: [] }) > 0, "stars are drawn by default");
assert.ok(litPixels({ frame: 7, sprites: [], starfield: true }) > 0, "and when asked for");
assert.equal(litPixels({ frame: 7, sprites: [], starfield: false }), 0, "none when switched off");

assert.ok(shader.computeStarPositions(7).length > 0, "shader path: stars by default");
assert.ok(shader.computeStarPositions(7, true).length > 0, "shader path: stars when asked for");
assert.deepEqual(shader.computeStarPositions(7, false), [], "shader path: none when switched off");

console.log("starfield flag tests passed");
