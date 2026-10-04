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
// The CLI reads these with PyYAML, so the browser must read them the same way.
assert(glyphsOf('"0123456789"  # digits') === "0123456789", "trailing comment after a double-quoted value");
assert(glyphsOf("'ab'   # note") === "ab", "trailing comment after a single-quoted value");
assert(glyphsOf('"a # b"') === "a # b", "a # inside the quotes is part of the value");
assert(glyphsOf('"\\x41\\e\\0"') === "A\u001b\u0000", "YAML hex and named escapes");
assert(glyphsOf('"\\U0001F600"') === "\u{1F600}", "eight-digit unicode escape");
assert(glyphsOf('"a\\tb\\\\"') === "a\tb\\", "tab and backslash escapes");
assert(glyphsOf('""') === "", "an empty string");

const noGlyphs = builder.parseStripedefsYaml(
  "palettegroups:\n  g:\n    - strip: a.png\n      frames: 2\n");
assert(noGlyphs[0].items[0].glyphs === "", "no glyphs key means an empty table");

function rejects(yamlValue) {
  try {
    glyphsOf(yamlValue);
  } catch (error) {
    return true;
  }
  return false;
}

assert(rejects('"unterminated\\"'), "a malformed double-quoted string is rejected");
assert(rejects("0123456789"), "an unquoted number is rejected, as generate_roms.py rejects it");
assert(rejects("ABC"), "unquoted text is rejected");
assert(rejects('"ab" cd'), "text after the closing quote is rejected");
assert(rejects('"\\q"'), "an unknown escape is rejected");
assert(rejects('"\\x4"'), "a short hex escape is rejected");

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

// --- strip headers -------------------------------------------------------
// Width and frame count are stored minus one, so the full circle (256 wide)
// and a 256-glyph font fit a byte with no special case, the same bytes
// tools/generate_roms.py writes (docs/internals/rom-format.md).
async function headerOf(width, height, frames) {
  const built = await builder.buildRom({
    stripedefsYaml: `palettegroups:\n  g:\n    - strip: a.png\n      frames: ${frames}\n`,
    loadImage: async () => solidImage(width * frames, height),
  });
  const start = new DataView(built.buffer).getUint32(4, true);
  const attrs = start + 1 + built[start];
  return Array.from(built.subarray(attrs, attrs + 4));
}

const cases = [
  [[255, 8, 1], [254, 8, 0, 0]],
  [[256, 8, 1], [255, 8, 0, 0]],
  [[9, 4, 255], [8, 4, 254, 0]],
  [[9, 4, 256], [8, 4, 255, 0]],
  [[1, 255, 1], [0, 255, 0, 0]],
];
for (const [[width, height, frames], expectedHeader] of cases) {
  const header = await headerOf(width, height, frames);
  assert(JSON.stringify(header) === JSON.stringify(expectedHeader),
    `${width}x${height}x${frames} header is ${header}, expected ${expectedHeader}`);
}

// Images no header can describe exactly are errors that name the file.
async function buildError(yamlText, images) {
  try {
    await builder.buildRom({
      stripedefsYaml: yamlText,
      loadImage: async (filename) => images[filename],
    });
  } catch (error) {
    return error.message;
  }
  return null;
}

const uneven = await buildError(
  "palettegroups:\n  g:\n    - strip: pollitos.png\n      frames: 5\n",
  { "pollitos.png": solidImage(256, 19) });
assert(uneven && uneven.includes("pollitos.png") && uneven.includes("5 equal frames"),
  `uneven sheet error: ${uneven}`);
const tooManyFrames = await buildError(
  "palettegroups:\n  g:\n    - strip: font.png\n      frames: 257\n",
  { "font.png": solidImage(257, 4) });
assert(tooManyFrames && tooManyFrames.includes("font.png") && tooManyFrames.includes("257 frames"),
  `frame count error: ${tooManyFrames}`);
const tooTall = await buildError(
  "palettegroups:\n  g:\n    - strip: tower.png\n",
  { "tower.png": solidImage(4, 256) });
assert(tooTall && tooTall.includes("tower.png") && tooTall.includes("256 px tall"),
  `height error: ${tooTall}`);
const duplicate = await buildError(
  "palettegroups:\n  g:\n    - strip: a.png\n    - strip: sub/a.png\n",
  { "a.png": solidImage(4, 4), "sub/a.png": solidImage(4, 4) });
assert(duplicate && duplicate.includes("duplicate image id a.png"), `duplicate id error: ${duplicate}`);

console.log("rom builder core tests passed");
