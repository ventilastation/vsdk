// The GPU scene-compositing core (web/scene-shader-core.js) must produce
// exactly the frames the CPU compositor (led-render-core.js
// computeLedFramePixels) produces. The software executor interprets the
// same algorithm and the same packed texture buffers the GLSL consumes, so
// byte-equality here validates the packers + algorithm without a GL
// context; the GLSL itself is a function-for-function transcription of the
// executor (and tests/test_shader_parity.py compares the real GL output on
// a machine with a display).

import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const {
  COLUMNS,
  PIXELS,
  computeLedFramePixels,
  decodeVs2SceneBuffer,
} = require("../web/led-render-core.js");
const core = require("../web/scene-shader-core.js");

function createPalette(entries) {
  const palette = new Uint8Array(256 * 4);
  for (const [index, [r, g, b]] of Object.entries(entries)) {
    const base = Number(index) * 4;
    palette[base] = 0xff;
    palette[base + 1] = b;
    palette[base + 2] = g;
    palette[base + 3] = r;
  }
  return palette;
}

function makeAsset({ width, height, frames = 1, palette = 0, data }) {
  const bytes = Uint8Array.from(data);
  return {
    width,
    height,
    frames,
    palette,
    data: bytes,
    dataLength: bytes.length,
    loadedBytes: bytes.length,
  };
}

function makeVs2ScenePayload({ layers, sprites, tilemaps = [] }) {
  const headerSize = 16;
  const layerSize = 8;
  const spriteSize = 24;
  const tilemapSize = tilemaps.length ? 32 : 0;
  const framesBytes = tilemaps.reduce((total, tilemap) => total + tilemap.frames.length, 0);
  const payload = new Uint8Array(
    headerSize
    + layers.length * layerSize
    + sprites.length * spriteSize
    + tilemaps.length * 32
    + framesBytes
  );
  const view = new DataView(payload.buffer);
  payload[0] = "V".charCodeAt(0);
  payload[1] = "S".charCodeAt(0);
  payload[2] = "2".charCodeAt(0);
  payload[3] = 0;
  payload[4] = tilemaps.length ? 2 : 1;
  payload[5] = layers.length;
  payload[6] = sprites.length;
  payload[7] = tilemaps.length;
  view.setUint16(8, headerSize, true);
  view.setUint16(10, layerSize, true);
  view.setUint16(12, spriteSize, true);
  view.setUint16(14, tilemapSize, true);

  let offset = headerSize;
  for (let index = 0; index < layers.length; index += 1) {
    const layer = layers[index];
    payload[offset] = index;
    payload[offset + 1] = layer.mode;
    payload[offset + 2] = layer.visible === false ? 0 : 1;
    offset += layerSize;
  }
  for (const sprite of sprites) {
    payload[offset] = sprite.layer ?? 255;
    payload[offset + 1] = sprite.image_strip;
    payload[offset + 2] = sprite.frame || 0;
    payload[offset + 3] = sprite.mode ?? 1;
    payload[offset + 4] = sprite.flags ?? 1;
    view.setInt32(offset + 10, Math.trunc((sprite.x || 0) * 256), true);
    view.setInt32(offset + 14, Math.trunc((sprite.y || 0) * 256), true);
    offset += spriteSize;
  }
  let framesOffset = offset + tilemaps.length * 32;
  for (const tilemap of tilemaps) {
    payload[offset] = tilemap.layer ?? 255;
    payload[offset + 1] = tilemap.image_strip;
    payload[offset + 2] = tilemap.flags ?? 1;
    payload[offset + 3] = tilemap.mode ?? 1;
    view.setUint16(offset + 4, tilemap.columns, true);
    view.setUint16(offset + 6, tilemap.rows, true);
    view.setUint16(offset + 8, tilemap.tile_width, true);
    view.setUint16(offset + 10, tilemap.tile_height, true);
    view.setUint16(offset + 12, tilemap.viewport[0], true);
    view.setUint16(offset + 14, tilemap.viewport[1], true);
    view.setUint16(offset + 16, tilemap.viewport[2], true);
    view.setUint16(offset + 18, tilemap.viewport[3], true);
    view.setInt32(offset + 20, Math.trunc((tilemap.x || 0) * 256), true);
    view.setInt32(offset + 24, Math.trunc((tilemap.y || 0) * 256), true);
    view.setUint32(offset + 28, framesOffset, true);
    offset += 32;
    payload.set(Uint8Array.from(tilemap.frames), framesOffset);
    framesOffset += tilemap.frames.length;
  }
  return payload;
}

// The pre-VS2 wire table: 100 slots x 5 bytes, frame 0xFF hides a slot.
function makeLegacyTable(sprites) {
  const table = new Uint8Array(100 * 5);
  for (let slot = 0; slot < 100; slot += 1) {
    table[slot * 5 + 3] = 0xff;
  }
  for (const sprite of sprites) {
    const base = sprite.slot * 5;
    table[base] = sprite.x & 0xff;
    table[base + 1] = sprite.y & 0xff;
    table[base + 2] = sprite.image_strip;
    table[base + 3] = sprite.frame;
    table[base + 4] = sprite.perspective & 0xff;
  }
  return table;
}

// What app-support.js decodeSpriteStateBuffer produces for the CPU path.
function decodeLegacyTable(table) {
  const sprites = [];
  for (let slot = 0; slot * 5 + 5 <= table.length; slot += 1) {
    const offset = slot * 5;
    const frame = table[offset + 3];
    if (frame === 0xff) {
      continue;
    }
    const raw = table[offset + 4];
    sprites.push({
      slot,
      x: table[offset],
      y: table[offset + 1],
      image_strip: table[offset + 2],
      frame,
      perspective: raw & 0x80 ? raw - 0x100 : raw,
    });
  }
  return sprites;
}

const deepspace = core.packDeepspace();

function compareScene(label, { assets, paletteBytes, frame, sceneData }) {
  const expected = computeLedFramePixels(frame, assets, paletteBytes);
  const actual = core.renderSceneSoftware({
    strips: core.packStrips(assets),
    palette: core.packPalette(paletteBytes),
    sceneData,
    stars: core.packStars(core.computeStarPositions(frame.frame || 0)),
    deepspace,
    columnOffset: frame.column_offset || 0,
  });
  assert.equal(actual.length, expected.length, `${label}: pixel buffer size`);
  for (let index = 0; index < expected.length; index += 1) {
    if (actual[index] !== expected[index]) {
      const led = Math.floor(index / 4) % PIXELS;
      const column = Math.floor(index / 4 / PIXELS);
      assert.fail(
        `${label}: mismatch at column ${column} led ${led} channel ${index % 4}: `
        + `expected ${expected[index]}, got ${actual[index]}`,
      );
    }
  }
  console.log(`ok ${label}`);
}

// A sprite strip with distinguishable pixels: 4 wide x 6 tall x 2 frames.
// Column-major per frame, columns mirrored on screen like real strips.
function patternedAsset({ width = 4, height = 6, frames = 2, palette = 0 } = {}) {
  const data = [];
  for (let frame = 0; frame < frames; frame += 1) {
    for (let column = 0; column < width; column += 1) {
      for (let row = 0; row < height; row += 1) {
        // Sprinkle transparency to exercise the opaque-hit scan.
        if ((column + row + frame) % 3 === 0) {
          data.push(255);
        } else {
          data.push(1 + ((column + row * 2 + frame * 3) % 4));
        }
      }
    }
  }
  return makeAsset({ width, height, frames, palette, data });
}

const PALETTE = createPalette({
  1: [10, 20, 30],
  2: [40, 50, 60],
  3: [70, 80, 90],
  4: [100, 110, 120],
});

// Palette group 1 lives in the second 1024-byte block.
const TWO_GROUP_PALETTE = new Uint8Array(2048);
TWO_GROUP_PALETTE.set(PALETTE, 0);
TWO_GROUP_PALETTE.set(createPalette({ 1: [200, 210, 220], 2: [230, 240, 250] }), 1024);

function blankFrame(overrides = {}) {
  return { frame: 0, column_offset: 0, sprites: [], tilemaps: [], ...overrides };
}

{
  compareScene("empty scene, stars at tick 0", {
    assets: new Map(),
    paletteBytes: PALETTE,
    frame: blankFrame(),
    sceneData: core.packSceneLegacy(null),
  });
}

{
  compareScene("stars animate with the tick and column offset", {
    assets: new Map(),
    paletteBytes: PALETTE,
    frame: blankFrame({ frame: 1234, column_offset: 100 }),
    sceneData: core.packSceneLegacy(null),
  });
}

{
  const table = makeLegacyTable([
    { slot: 0, x: 10, y: 40, image_strip: 5, frame: 0, perspective: 1 },
    { slot: 1, x: 12, y: 60, image_strip: 5, frame: 1, perspective: 2 },
    { slot: 2, x: 250, y: 30, image_strip: 5, frame: 5, perspective: 1 }, // frame % totalFrames, x wraps
    { slot: 3, x: 66, y: 200, image_strip: 6, frame: 0, perspective: 0 }, // planet mode
    { slot: 4, x: 30, y: 10, image_strip: 5, frame: 0, perspective: -1 }, // negative byte acts as HUD
    { slot: 7, x: 10, y: 41, image_strip: 5, frame: 1, perspective: 1 }, // overlaps slot 0; slot 0 wins
  ]);
  const assets = new Map([
    [5, patternedAsset()],
    [6, makeAsset({ width: 2, height: 8, data: [1, 2, 3, 4, 255, 1, 2, 3, 4, 4, 3, 2, 1, 255, 2, 1] })],
  ]);
  compareScene("legacy sprite table: all modes, overlap, wrap, hidden slots", {
    assets,
    paletteBytes: PALETTE,
    frame: blankFrame({ sprites: decodeLegacyTable(table), frame: 77 }),
    sceneData: core.packSceneLegacy(table),
  });
}

{
  // Planet-mode ("fullscreen") sprite scaled at several distances, plus a
  // 255-wide strip (widened to 256).
  const wide = makeAsset({
    width: 255,
    height: 4,
    data: Array.from({ length: 256 * 4 }, (_, index) => (index % 5 === 0 ? 255 : 1 + (index % 3))),
  });
  const table = makeLegacyTable([
    { slot: 0, x: 0, y: 0, image_strip: 1, frame: 0, perspective: 0 },
    { slot: 1, x: 128, y: 250, image_strip: 2, frame: 0, perspective: 0 },
  ]);
  const assets = new Map([
    [1, wide],
    [2, patternedAsset({ width: 8, height: 16, frames: 1 })],
  ]);
  compareScene("planet mode near and far + 256-wide strip", {
    assets,
    paletteBytes: PALETTE,
    frame: blankFrame({ sprites: decodeLegacyTable(table) }),
    sceneData: core.packSceneLegacy(table),
  });
}

{
  const payload = makeVs2ScenePayload({
    layers: [
      { mode: 1, visible: true },
      { mode: 2, visible: false }, // hides its sprites
      { mode: 2, visible: true }, // overrides sprite mode to HUD
    ],
    sprites: [
      { layer: 0, image_strip: 5, frame: 1, mode: 1, flags: 1, x: 20, y: 50 },
      { layer: 1, image_strip: 5, frame: 0, mode: 1, flags: 1, x: 40, y: 50 }, // invisible layer
      { layer: 2, image_strip: 5, frame: 0, mode: 1, flags: 1, x: 60, y: 20 }, // mode override
      { layer: 255, image_strip: 5, frame: 0, mode: 1, flags: 0, x: 80, y: 50 }, // hidden flag
      { layer: 255, image_strip: 5, frame: 0, mode: 1, flags: 1 | 2, x: 100, y: 50 }, // flip X
      { layer: 255, image_strip: 5, frame: 0, mode: 2, flags: 1 | 4, x: 120, y: 10 }, // flip Y
      { layer: 255, image_strip: 6, frame: 0, mode: 0, flags: 1 | 4, x: 140, y: 30 }, // planet flip
      { layer: 255, image_strip: 5, frame: 0, mode: 1, flags: 1, x: -2.5, y: -3.5 }, // negative fixed point
    ],
  });
  const decoded = decodeVs2SceneBuffer(payload);
  const assets = new Map([
    [5, patternedAsset()],
    [6, makeAsset({ width: 2, height: 8, data: [1, 2, 3, 4, 255, 1, 2, 3, 4, 4, 3, 2, 1, 255, 2, 1] })],
  ]);
  compareScene("vs2 sprites: layers, flips, hidden, negative coords", {
    assets,
    paletteBytes: PALETTE,
    frame: blankFrame({ sprites: decoded.sprites, tilemaps: decoded.tilemaps, frame: 9 }),
    // Pass the raw VS2 wire payload. The GPU path accepts the same bytes that
    // cross the browser bridge; it does not need the CPU compositor's sprite
    // object array.
    sceneData: core.packSceneVs2(payload),
  });
}

{
  // Tilemaps: tunnel + HUD, empty tiles, viewport clipping, a second
  // palette group, and a sprite drawn on top.
  const tileData = [];
  for (let frame = 0; frame < 3; frame += 1) {
    for (let column = 0; column < 4; column += 1) {
      for (let row = 0; row < 4; row += 1) {
        tileData.push(frame === 2 && column === 3 && row === 0 ? 255 : 1 + ((frame + column + row) % 2));
      }
    }
  }
  const payload = makeVs2ScenePayload({
    layers: [],
    sprites: [
      { layer: 255, image_strip: 5, frame: 0, mode: 1, flags: 1, x: 12, y: 30 },
    ],
    tilemaps: [
      {
        image_strip: 9,
        frames: [0, 1, 2, 255, 1, 0],
        columns: 3,
        rows: 2,
        tile_width: 4,
        tile_height: 4,
        viewport: [2, 1, 9, 6],
        mode: 1,
        x: 100,
        y: 30,
      },
      {
        image_strip: 10,
        frames: [2, 0, 255, 1],
        columns: 2,
        rows: 2,
        tile_width: 4,
        tile_height: 4,
        viewport: [0, 0, 8, 8],
        mode: 2,
        x: 200,
        y: 12,
      },
    ],
  });
  const decoded = decodeVs2SceneBuffer(payload);
  const assets = new Map([
    [5, patternedAsset()],
    [9, makeAsset({ width: 4, height: 4, frames: 3, data: tileData })],
    [10, makeAsset({ width: 4, height: 4, frames: 3, palette: 1, data: tileData })],
  ]);
  compareScene("vs2 tilemaps: tunnel + HUD, empty tiles, viewport, palette group", {
    assets,
    paletteBytes: TWO_GROUP_PALETTE,
    frame: blankFrame({ sprites: decoded.sprites, tilemaps: decoded.tilemaps, frame: 3, column_offset: 17 }),
    sceneData: core.packSceneVs2(decoded),
  });
}

{
  // Full-density stress: 100 legacy sprites over the whole ring.
  const sprites = [];
  for (let slot = 0; slot < 100; slot += 1) {
    sprites.push({
      slot,
      x: (slot * 37) % 256,
      y: (slot * 11) % 256,
      image_strip: 5 + (slot % 2),
      frame: slot % 7,
      perspective: [0, 1, 2][slot % 3],
    });
  }
  const table = makeLegacyTable(sprites);
  const assets = new Map([
    [5, patternedAsset()],
    [6, patternedAsset({ width: 8, height: 10, frames: 3, palette: 1 })],
  ]);
  compareScene("100-sprite stress scene", {
    assets,
    paletteBytes: TWO_GROUP_PALETTE,
    frame: blankFrame({ sprites: decodeLegacyTable(table), frame: 500, column_offset: 3 }),
    sceneData: core.packSceneLegacy(table),
  });
}

console.log("scene shader core: software executor matches computeLedFramePixels");
