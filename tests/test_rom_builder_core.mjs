// The browser ROM builder (web/rom-builder-core.js) must accept `glyphs:` in
// __images__.yaml and write the glyph table the way tools/generate_roms.py
// does: a little-endian u16 length and that many UTF-8 bytes trailing every
// strip's pixel data, zero-length when the strip declares none.

import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const builder = require("../web/rom-builder-core.js");

function assert(condition, message) {
  if (!condition) {
    console.error(`FAIL: ${message}`);
    process.exit(1);
  }
}

function glyphsOf(yamlValue) {
  const groups = builder.parseStripedefsYaml(
    `palettegroups:\n  g:\n    - strip: a.png\n      glyphs: ${yamlValue}\n`);
  return groups[0].items[0].glyphs;
}

// --- parsing -------------------------------------------------------------
assert(glyphsOf('"0123456789 *"') === "0123456789 *", "double-quoted glyphs");
assert(glyphsOf("'0123456789'") === "0123456789", "single-quoted glyphs");
assert(glyphsOf("'it''s'") === "it's", "doubled single quote");
assert(glyphsOf('"\\u00e9a"') === "\u00e9a", "double-quoted unicode escape");
assert(glyphsOf("ABC") === "ABC", "unquoted glyphs");

const noGlyphs = builder.parseStripedefsYaml(
  "palettegroups:\n  g:\n    - strip: a.png\n      frames: 2\n");
assert(noGlyphs[0].items[0].glyphs === "", "no glyphs key means an empty table");

let rejected = false;
try {
  glyphsOf('"unterminated\\"');
} catch (error) {
  rejected = true;
}
assert(rejected, "a malformed double-quoted string is rejected");

// --- building ------------------------------------------------------------
const yaml = [
  "palettegroups:",
  "  main:",
  "    - strip: digits.png",
  "      frames: 3",
  '      glyphs: "012"',
  "    - strip: ship.png",
  "      frames: 1",
  "    - strip: accents.png",
  "      frames: 2",
  '      glyphs: "\\u00e9\\u00f1"',
  "",
].join("\n");

function solidImage(width, height) {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < data.length; i += 4) {
    data[i] = 200;
    data[i + 1] = 40;
    data[i + 2] = 40;
    data[i + 3] = 255;
  }
  return { width, height, data };
}

const sizes = { "digits.png": [12, 5], "ship.png": [8, 8], "accents.png": [10, 6] };
const rom = await builder.buildRom({
  stripedefsYaml: yaml,
  loadImage: async (filename) => solidImage(...sizes[filename]),
});

const view = new DataView(rom.buffer, rom.byteOffset, rom.byteLength);
const stripCount = view.getUint16(0, true);
const paletteCount = view.getUint16(2, true);
assert(stripCount === 3, `strip count is ${stripCount}`);
const offsets = [];
for (let i = 0; i < stripCount; i += 1) {
  offsets.push(view.getUint32(4 + i * 4, true));
}
const recordsEnd = view.getUint32(4 + stripCount * 4, true);
assert(paletteCount === 1, "one palette group");

const expected = {
  "digits.png": "012",
  "ship.png": "",
  "accents.png": "\u00e9\u00f1",
};
const decoder = new TextDecoder();
for (let n = 0; n < stripCount; n += 1) {
  const start = offsets[n];
  const end = n + 1 < stripCount ? offsets[n + 1] : recordsEnd;
  const nameLength = rom[start];
  const name = decoder.decode(rom.subarray(start + 1, start + 1 + nameLength));
  const attrs = start + 1 + nameLength;
  // The pixel data is the image's own width times its height; the trailer
  // follows it.
  const trailer = attrs + 4 + sizes[name][0] * sizes[name][1];
  const glyphLength = view.getUint16(trailer, true);
  assert(trailer + 2 + glyphLength === end,
    `${name}: trailer is ${glyphLength} bytes but the record ends ${end - trailer - 2} bytes after its length field`);
  const glyphs = decoder.decode(rom.subarray(trailer + 2, trailer + 2 + glyphLength));
  assert(glyphs === expected[name], `${name}: glyphs ${JSON.stringify(glyphs)}`);
}

console.log("rom builder core tests passed");
