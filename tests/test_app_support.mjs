// web/app-support.js's decodeImageStripPayload() is the one place the web
// emulator reads a strip header: width and frame count are stored minus one
// (docs/internals/rom-format.md), so a full-circle image and a 256-glyph
// font decode with no special case.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

// app-support.js is a browser module: it reads window.location and the
// LED core that index.html loads before it.
globalThis.window = { location: { href: "http://localhost/emulator/" } };
createRequire(import.meta.url)("../web/led-render-core.js");
const source = readFileSync(new URL("../web/app-support.js", import.meta.url), "utf8");
const { decodeImageStripPayload } = await import(
  "data:text/javascript;base64," + Buffer.from(source).toString("base64"));

function payload(header, pixelCount) {
  return Uint8Array.from([...header, ...new Array(pixelCount).fill(7)]);
}

const wide255 = decodeImageStripPayload(3, payload([254, 8, 0, 2], 255 * 8));
assert.deepEqual([wide255.width, wide255.height, wide255.frames, wide255.palette], [255, 8, 1, 2]);
assert.equal(wide255.data.length, 255 * 8);

const wide256 = decodeImageStripPayload(4, payload([255, 8, 0, 0], 256 * 8));
assert.deepEqual([wide256.width, wide256.frames], [256, 1]);

const font256 = decodeImageStripPayload(5, payload([8, 16, 255, 0], 9 * 16 * 256));
assert.deepEqual([font256.width, font256.height, font256.frames], [9, 16, 256]);

const font255 = decodeImageStripPayload(6, payload([8, 16, 254, 0], 9 * 16 * 255));
assert.equal(font255.frames, 255);

const smallest = decodeImageStripPayload(7, payload([0, 1, 0, 9], 1));
assert.deepEqual([smallest.slot, smallest.width, smallest.height, smallest.frames, smallest.palette],
  [7, 1, 1, 1, 9]);

assert.equal(decodeImageStripPayload(8, Uint8Array.from([1, 2, 3])), null);

console.log("app support strip decode tests passed");
