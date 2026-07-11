const assert = require("node:assert/strict");
const {
  COLUMNS,
  PIXELS,
  DEEPSPACE,
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
    payload[offset] = sprite.layer || 0;
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

// Mirrors make_tile_strip() in tests/test_emulator_vs2_render.py: 4x4 tiles,
// 3 frames, stored column-mirrored like real strips. Frame 0: screen column 0
// is palette index 1, the rest 2. Frame 1: solid 3. Frame 2: solid 4 with the
// tile's screen pixel (0, 0) transparent.
function makeTileStripAsset() {
  const frame0 = new Array(16).fill(0);
  for (let dx = 0; dx < 4; dx += 1) {
    for (let dy = 0; dy < 4; dy += 1) {
      frame0[(3 - dx) * 4 + dy] = dx === 0 ? 1 : 2;
    }
  }
  const frame1 = new Array(16).fill(3);
  const frame2 = new Array(16).fill(4);
  frame2[3 * 4 + 0] = 255;
  return makeAsset({ width: 4, height: 4, frames: 3, data: [...frame0, ...frame1, ...frame2] });
}

// 2x2 map: top row = frame 0 | frame 1, bottom row = frame 2 | empty cell
const TILEMAP_FRAMES = [0, 1, 2, 255];

function defaultTilemap(overrides = {}) {
  return {
    image_strip: 9,
    frames: TILEMAP_FRAMES,
    columns: 2,
    rows: 2,
    tile_width: 4,
    tile_height: 4,
    viewport: [0, 0, 8, 8],
    mode: 2,
    x: 10,
    y: 40,
    ...overrides,
  };
}

function renderTilemapScene(scene, extraAssets = []) {
  const palette = createPalette({
    1: [10, 0, 0],
    2: [20, 0, 0],
    3: [30, 0, 0],
    4: [40, 0, 0],
  });
  const assets = new Map([[9, makeTileStripAsset()], ...extraAssets]);
  const decoded = decodeVs2SceneBuffer(makeVs2ScenePayload(scene));
  const frame = blankFrame({ sprites: decoded.sprites, tilemaps: decoded.tilemaps });
  return { decoded, pixels: computeLedFramePixels(frame, assets, palette) };
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
    assert.equal(decoded.sprites[0].x, 42.5);
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

  {
    const payload = makeVs2ScenePayload({
      layers: [],
      sprites: [
        { layer: 255, image_strip: 8, frame: 0, mode: 2, flags: 1 | 2 | 4, x: 20, y: 51 },
      ],
    });
    const decoded = decodeVs2SceneBuffer(payload);
    const palette = createPalette({
      1: [10, 0, 0],
      2: [20, 0, 0],
      3: [30, 0, 0],
      4: [40, 0, 0],
    });
    const assets = new Map([
      [8, makeAsset({ width: 2, height: 2, data: [1, 2, 3, 4] })],
    ]);
    const pixels = computeLedFramePixels(blankFrame({ sprites: decoded.sprites }), assets, palette);
    assert.deepEqual(getLedColor(pixels, 20, 2), [20, 0, 0, 255], "VS2 flip_x+flip_y should sample mirrored column/row");
    assert.deepEqual(getLedColor(pixels, 20, 1), [10, 0, 0, 255], "VS2 flip_y should reverse source rows");
    assert.deepEqual(getLedColor(pixels, 21, 2), [40, 0, 0, 255], "VS2 flip_x should mirror source columns");
  }

  {
    const payload = makeVs2ScenePayload({
      layers: [],
      sprites: [
        { layer: 255, image_strip: 8, frame: 0, mode: 2, flags: 1, x: -0.25, y: -0.25 },
      ],
    });
    const decoded = decodeVs2SceneBuffer(payload);
    assert.equal(decoded.sprites[0].x, -0.25);
    assert.equal(decoded.sprites[0].y, -0.25);

    const palette = createPalette({
      1: [10, 0, 0],
      2: [20, 0, 0],
      3: [30, 0, 0],
      4: [40, 0, 0],
    });
    const assets = new Map([
      [8, makeAsset({ width: 2, height: 2, data: [1, 2, 3, 4] })],
    ]);
    const pixels = computeLedFramePixels(blankFrame({ sprites: decoded.sprites }), assets, palette);
    assert.deepEqual(getLedColor(pixels, 0, 53), [20, 0, 0, 255], "VS2 x/y=-0.25 should floor and clip vertically");
    assert.deepEqual(getLedColor(pixels, 1, 53), [0, 0, 0, 255], "VS2 fractional X should occupy only its wrapped sprite columns");
    assert.deepEqual(getLedColor(pixels, 255, 53), [40, 0, 0, 255], "VS2 negative X should wrap around the circular display");
  }

  // VS2 tilemaps (payload v2). HUD mode at y=40: dest rows 40..47 -> leds 13..6.
  {
    const { decoded, pixels } = renderTilemapScene({ layers: [], sprites: [], tilemaps: [defaultTilemap()] });
    assert.equal(decoded.version, 2);
    assert.equal(decoded.tilemaps.length, 1);
    assert.deepEqual(decoded.tilemaps[0].viewport, [0, 0, 8, 8]);
    assert.deepEqual(Array.from(decoded.tilemaps[0].frames), TILEMAP_FRAMES);

    // top-left tile is frame 0: screen column 0 shows index 1 -> red 10
    for (let n = 0; n < 4; n += 1) {
      assert.deepEqual(getLedColor(pixels, 10, 13 - n), [10, 0, 0, 255], `tilemap frame 0 led ${13 - n}`);
    }
    // bottom-left tile is frame 2: pixel (0, 0) transparent, rest 40
    assert.deepEqual(getLedColor(pixels, 10, 9), [0, 0, 0, 255], "tilemap transparent pixel");
    assert.deepEqual(getLedColor(pixels, 10, 8), [40, 0, 0, 255], "tilemap frame 2");
    // tile screen column 1 of frame 0 shows index 2 -> 20 (mirroring check)
    assert.deepEqual(getLedColor(pixels, 11, 13), [20, 0, 0, 255], "tilemap unmirrored column");
    // second map column: top tile frame 1 -> 30, bottom cell 255 is empty
    assert.deepEqual(getLedColor(pixels, 14, 13), [30, 0, 0, 255], "tilemap frame 1");
    assert.deepEqual(getLedColor(pixels, 14, 9), [0, 0, 0, 255], "tilemap empty cell");
    // beyond the map width nothing renders
    assert.deepEqual(getLedColor(pixels, 18, 13), [0, 0, 0, 255], "tilemap width limit");
  }

  {
    const { pixels } = renderTilemapScene({
      layers: [], sprites: [], tilemaps: [defaultTilemap({ viewport: [4, 0, 4, 8] })],
    });
    // panning the viewport shows the second map column at the origin
    assert.deepEqual(getLedColor(pixels, 10, 13), [30, 0, 0, 255], "tilemap viewport pans horizontally");
    assert.deepEqual(getLedColor(pixels, 14, 13), [0, 0, 0, 255], "tilemap viewport window width");
  }

  {
    const { pixels } = renderTilemapScene({
      layers: [], sprites: [], tilemaps: [defaultTilemap({ viewport: [0, 2, 8, 4] })],
    });
    assert.deepEqual(getLedColor(pixels, 10, 13), [10, 0, 0, 255], "tilemap viewport pans vertically");
    assert.deepEqual(getLedColor(pixels, 10, 11), [0, 0, 0, 255], "tilemap vertical pan transparent pixel");
    assert.deepEqual(getLedColor(pixels, 10, 10), [40, 0, 0, 255], "tilemap vertical pan frame 2");
    assert.deepEqual(getLedColor(pixels, 10, 9), [0, 0, 0, 255], "tilemap viewport window height");
  }

  {
    const { pixels } = renderTilemapScene({
      layers: [], sprites: [], tilemaps: [defaultTilemap({ viewport: [6, 0, 8, 8] })],
    });
    assert.deepEqual(getLedColor(pixels, 10, 13), [30, 0, 0, 255], "tilemap viewport clamps to map edge");
    assert.deepEqual(getLedColor(pixels, 12, 13), [0, 0, 0, 255], "tilemap clamped viewport width");
  }

  {
    const { pixels } = renderTilemapScene({
      layers: [], sprites: [], tilemaps: [defaultTilemap({ x: 254 })],
    });
    assert.deepEqual(getLedColor(pixels, 254, 13), [10, 0, 0, 255], "tilemap at wrap origin");
    assert.deepEqual(getLedColor(pixels, 0, 13), [20, 0, 0, 255], "tilemap wraps around column zero");
  }

  {
    const { pixels } = renderTilemapScene({
      layers: [],
      sprites: [{ layer: 255, image_strip: 8, frame: 0, mode: 2, flags: 1, x: 10, y: 40 }],
      tilemaps: [defaultTilemap()],
    }, [[8, makeAsset({ width: 2, height: 2, data: [1, 2, 3, 4] })]]);
    // the sprite pixel (data index 3 -> red 30) covers the tile's 10
    assert.deepEqual(getLedColor(pixels, 10, 13), [30, 0, 0, 255], "tilemap draws behind sprites");
    assert.deepEqual(getLedColor(pixels, 10, 11), [10, 0, 0, 255], "tilemap shows below the sprite");
  }

  {
    const { decoded, pixels } = renderTilemapScene({
      layers: [{ mode: 2, visible: false }], sprites: [], tilemaps: [defaultTilemap({ layer: 0 })],
    });
    assert.equal(decoded.tilemaps.length, 0, "hidden layer drops the tilemap at decode");
    assert.deepEqual(getLedColor(pixels, 10, 13), [0, 0, 0, 255], "tilemap on hidden layer");
  }

  {
    const { pixels } = renderTilemapScene({
      layers: [], sprites: [], tilemaps: [defaultTilemap({ mode: 1 })],
    });
    assert.deepEqual(getLedColor(pixels, 10, DEEPSPACE[40]), [10, 0, 0, 255], "tilemap TUNNEL projection uses deepspace");
  }

  {
    const { pixels } = renderTilemapScene({
      layers: [], sprites: [], tilemaps: [defaultTilemap({ mode: 0 })],
    });
    assert.deepEqual(getLedColor(pixels, 10, 13), [0, 0, 0, 255], "FULLSCREEN tilemap is skipped");
  }

  {
    const { pixels } = renderTilemapScene({
      layers: [], sprites: [], tilemaps: [
        defaultTilemap({ tile_width: 8, tile_height: 8, viewport: [0, 0, 16, 16] }),
      ],
    });
    assert.deepEqual(getLedColor(pixels, 10, 13), [0, 0, 0, 255], "mismatched tile dims are skipped");
  }

  {
    const decoded = decodeVs2SceneBuffer(makeVs2ScenePayload({ layers: [], sprites: [] }));
    assert.equal(decoded.version, 1);
    assert.deepEqual(decoded.tilemaps, [], "v1 payloads decode with no tilemaps");
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
