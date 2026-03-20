const assert = require("node:assert/strict");
const {
  COLUMNS,
  PIXELS,
  computeLedFramePixels,
  getLedColor,
} = require("./led-render-core.js");

function createPalette(entries) {
  const palette = new Uint8Array(256 * 4);
  for (const [index, [r, g, b]] of Object.entries(entries)) {
    const base = Number(index) * 4;
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

function blankFrame(overrides = {}) {
  return {
    frame: 0,
    buttons: 0,
    column_offset: 0,
    gamma_mode: 1,
    sprites: [],
    events: [],
    ...overrides,
  };
}

function runTests() {
  {
    const palette = createPalette({ 1: [1, 2, 3] });
    const assets = new Map([
      [7, makeAsset({ width: 1, height: 1, data: [1] })],
    ]);
    const frame = blankFrame({
      sprites: [{ slot: 1, x: 42, y: 120, image_strip: 7, frame: 0, perspective: 1 }],
    });
    const pixels = computeLedFramePixels(frame, assets, palette);
    assert.deepEqual(getLedColor(pixels, 42, 7), [1, 2, 3, 255], "perspective=1 should map Y through deepspace");
  }

  {
    const palette = createPalette({ 1: [9, 8, 7] });
    const assets = new Map([
      [3, makeAsset({ width: 1, height: 4, data: [1, 1, 1, 1] })],
    ]);
    const frame = blankFrame({
      sprites: [{ slot: 1, x: 30, y: 255, image_strip: 3, frame: 0, perspective: 0 }],
    });
    const pixels = computeLedFramePixels(frame, assets, palette);
    assert.deepEqual(getLedColor(pixels, 30, 0), [9, 8, 7, 255], "perspective=0 should project onto leading LEDs");
  }

  {
    const palette = createPalette({ 1: [10, 20, 30], 2: [40, 50, 60] });
    const assets = new Map([
      [1, makeAsset({ width: 1, height: 1, data: [1] })],
      [2, makeAsset({ width: 1, height: 1, data: [2] })],
    ]);
    const frame = blankFrame({
      sprites: [
        { slot: 2, x: 88, y: 120, image_strip: 2, frame: 0, perspective: 1 },
        { slot: 1, x: 88, y: 120, image_strip: 1, frame: 0, perspective: 1 },
      ],
    });
    const pixels = computeLedFramePixels(frame, assets, palette);
    assert.deepEqual(getLedColor(pixels, 88, 7), [10, 20, 30, 255], "lower slot should overdraw higher slot like vsdk.render()");
  }

  {
    const palette = createPalette({ 1: [70, 80, 90] });
    const assets = new Map([
      [5, makeAsset({ width: 1, height: 1, data: [1] })],
    ]);
    const frame = blankFrame({
      column_offset: 3,
      sprites: [{ slot: 1, x: 40, y: 120, image_strip: 5, frame: 0, perspective: 1 }],
    });
    const pixels = computeLedFramePixels(frame, assets, palette);
    assert.deepEqual(getLedColor(pixels, 37, 7), [70, 80, 90, 255], "column_offset should rotate the ring output");
  }

  {
    const palette = createPalette({
      1: [10, 20, 30],
      2: [40, 50, 60],
      3: [70, 80, 90],
      4: [100, 110, 120],
    });
    const assets = new Map([
      [1, makeAsset({ width: 4, height: 3, data: [255, 1, 255, 2, 2, 255, 255, 3, 255, 4, 4, 4] })],
      [2, makeAsset({ width: 2, height: 4, data: [1, 2, 3, 4, 4, 3, 2, 1] })],
    ]);
    const frame = blankFrame({
      sprites: [
        { slot: 2, x: 10, y: 100, image_strip: 1, frame: 0, perspective: 1 },
        { slot: 1, x: 11, y: 220, image_strip: 2, frame: 0, perspective: 0 },
      ],
    });
    const pixels = computeLedFramePixels(frame, assets, palette);
    const fixture = {
      10: { 11: [100, 110, 120, 255] },
      11: {
        0: [10, 20, 30, 255],
        1: [40, 50, 60, 255],
        2: [70, 80, 90, 255],
        11: [70, 80, 90, 255],
      },
      12: {
        0: [100, 110, 120, 255],
        1: [70, 80, 90, 255],
        2: [40, 50, 60, 255],
        11: [40, 50, 60, 255],
      },
      13: { 11: [10, 20, 30, 255] },
    };

    for (const [column, leds] of Object.entries(fixture)) {
      for (const [led, rgba] of Object.entries(leds)) {
        assert.deepEqual(
          getLedColor(pixels, Number(column), Number(led)),
          rgba,
          `fixture parity mismatch at column ${column}, led ${led}`
        );
      }
    }
  }

  assert.equal(COLUMNS, 256);
  assert.equal(PIXELS, 54);
  console.log("render parity tests passed");
}

runTests();
