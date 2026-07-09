const assert = require("node:assert/strict");
const {
  COLUMNS,
  PIXELS,
  computeLedFramePixels,
  computeLedFramePixelsFromRgb,
  decodeVs2SceneBuffer,
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

function makeVs2ScenePayload({ layers, sprites }) {
  const headerSize = 16;
  const layerSize = 8;
  const spriteSize = 24;
  const payload = new Uint8Array(headerSize + layers.length * layerSize + sprites.length * spriteSize);
  const view = new DataView(payload.buffer);
  payload[0] = "V".charCodeAt(0);
  payload[1] = "S".charCodeAt(0);
  payload[2] = "2".charCodeAt(0);
  payload[3] = 0;
  payload[4] = 1;
  payload[5] = layers.length;
  payload[6] = sprites.length;
  view.setUint16(8, headerSize, true);
  view.setUint16(10, layerSize, true);
  view.setUint16(12, spriteSize, true);

  let offset = headerSize;
  for (let index = 0; index < layers.length; index += 1) {
    const layer = layers[index];
    payload[offset] = index;
    payload[offset + 1] = layer.mode;
    payload[offset + 2] = layer.visible === false ? 0 : 1;
    offset += layerSize;
  }
  for (const sprite of sprites) {
    payload[offset] = sprite.layer || 0;
    payload[offset + 1] = sprite.image_strip;
    payload[offset + 2] = sprite.frame || 0;
    payload[offset + 3] = sprite.mode ?? 1;
    payload[offset + 4] = sprite.flags ?? 1;
    view.setInt32(offset + 10, Math.trunc((sprite.x || 0) * 256), true);
    view.setInt32(offset + 14, Math.trunc((sprite.y || 0) * 256), true);
    offset += spriteSize;
  }
  return payload;
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

  {
    const payload = makeVs2ScenePayload({
      layers: [{ mode: 1, visible: true }, { mode: 2, visible: false }],
      sprites: [
        { layer: 0, image_strip: 7, frame: 0, mode: 1, flags: 1 | 2, x: 42.5, y: 120 },
        { layer: 1, image_strip: 7, frame: 0, mode: 2, flags: 1, x: 10, y: 0 },
        { layer: 0, image_strip: 7, frame: 0, mode: 1, flags: 0, x: 11, y: 0 },
      ],
    });
    const decoded = decodeVs2SceneBuffer(payload);
    assert.equal(decoded.version, 1);
    assert.equal(decoded.layers.length, 2);
    assert.equal(decoded.sprites.length, 1);
    assert.equal(decoded.sprites[0].x, 42);
    assert.equal(decoded.sprites[0].vs2.x, 42.5);
    assert.equal(decoded.sprites[0].vs2.flip_x, true);

    const palette = createPalette({ 1: [1, 2, 3] });
    const assets = new Map([
      [7, makeAsset({ width: 1, height: 1, data: [1] })],
    ]);
    const pixels = computeLedFramePixels(blankFrame({ sprites: decoded.sprites }), assets, palette);
    assert.deepEqual(getLedColor(pixels, 42, 7), [1, 2, 3, 255], "VS2 decoded sprite should render through LED core");
    assert.deepEqual(getLedColor(pixels, 10, 53), [0, 0, 0, 255], "hidden VS2 layer should not render");
  }

  {
    const payload = makeVs2ScenePayload({
      layers: [],
      sprites: [
        { layer: 255, image_strip: 3, frame: 0, mode: 0, flags: 1, x: 30, y: 255 },
        { layer: 255, image_strip: 7, frame: 0, mode: 2, flags: 1, x: 42, y: 0 },
      ],
    });
    const decoded = decodeVs2SceneBuffer(payload);
    assert.equal(decoded.layers.length, 0);
    assert.equal(decoded.sprites.length, 2);
    assert.equal(decoded.sprites[0].perspective, 0, "unlayered VS2 sprite must preserve FULLSCREEN mode");
    assert.equal(decoded.sprites[1].perspective, 2, "unlayered VS2 sprite must preserve HUD mode");

    const palette = createPalette({ 1: [9, 8, 7] });
    const assets = new Map([
      [3, makeAsset({ width: 1, height: 4, data: [1, 1, 1, 1] })],
      [7, makeAsset({ width: 1, height: 1, data: [1] })],
    ]);
    const pixels = computeLedFramePixels(blankFrame({ sprites: decoded.sprites }), assets, palette);
    assert.deepEqual(getLedColor(pixels, 30, 0), [9, 8, 7, 255], "unlayered VS2 FULLSCREEN sprite should use fullscreen projection");
    assert.deepEqual(getLedColor(pixels, 42, 53), [9, 8, 7, 255], "unlayered VS2 HUD sprite should use HUD projection");
  }

  // Raw polar framebuffer path (Super Ventilagon / Voom "frame_rgb").
  {
    const rgb = new Uint8Array(COLUMNS * PIXELS * 3);
    const set = (col, led, r, g, b) => {
      const s = (col * PIXELS + led) * 3;
      rgb[s] = r;
      rgb[s + 1] = g;
      rgb[s + 2] = b;
    };
    set(0, 0, 255, 0, 0);
    set(5, 3, 10, 20, 30);
    set(255, 53, 1, 2, 3);
    const pixels = computeLedFramePixelsFromRgb(rgb);
    assert.equal(pixels.length, COLUMNS * PIXELS * 4);
    assert.deepEqual(getLedColor(pixels, 0, 0), [255, 0, 0, 255]);
    assert.deepEqual(getLedColor(pixels, 5, 3), [10, 20, 30, 255]);
    assert.deepEqual(getLedColor(pixels, 255, 53), [1, 2, 3, 255]);
    assert.deepEqual(getLedColor(pixels, 1, 1), [0, 0, 0, 255]); // unset stays black, opaque
    // A short buffer must not throw and leaves the remainder black/opaque.
    const shortPixels = computeLedFramePixelsFromRgb(new Uint8Array(9));
    assert.equal(shortPixels.length, COLUMNS * PIXELS * 4);
    assert.deepEqual(getLedColor(shortPixels, 100, 0), [0, 0, 0, 255]);
  }

  console.log("render parity tests passed");
}

runTests();
