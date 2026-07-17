// GPU scene compositing core: the canonical definition of how a whole POV
// frame is rendered by a fragment shader from raw scene bytes, replacing the
// per-column CPU loop (led-render-core.js computeLedFramePixels, desktop
// povrender.render / gpu.c render/render_vs2).
//
// This module is the single source of truth shared by the web emulator
// (WebGL2, web/led-ring-renderers.js) and the desktop emulator (OpenGL 3.3,
// emulator/scene_shader.py packs byte-identical buffers -- enforced by
// tests/test_scene_shader_pack.py):
//
//   - the *texture layouts* the shader consumes (documented + packers here),
//   - the *GLSL fragment shader* itself (built by buildSceneFragmentSource),
//   - a *software executor* (renderSceneSoftware) that interprets the exact
//     shader algorithm from the packed buffers on the CPU, so the whole
//     pipeline is testable without a GL context
//     (tests/test_scene_shader_core.mjs compares it against
//     computeLedFramePixels on real fixture scenes).
//
// Key inversion versus the CPU compositors: they paint entities in
// descending-slot order and let later writes overwrite earlier ones, so the
// lowest slot ends up on top. Per fragment that is equivalent to probing in
// ASCENDING slot order and keeping the FIRST opaque hit -- which lets the
// shader early-out. Draw order becomes probe order:
//     sprites (slot asc) -> tilemaps (slot asc) -> stars -> black
// Within one tunnel-mode entity the CPU writes rows in ascending y, so the
// highest y that maps to this LED wins: the executor scans that range in
// DESCENDING y and keeps the first opaque pixel.
//
// ## Texture layouts (all texelFetch'd, never filtered)
//
// u_strips    R8UI, ATLAS_WIDTH wide. Every installed strip's pixel bytes
//             (header stripped) concatenated; byte i lives at texel
//             (i % ATLAS_WIDTH, i / ATLAS_WIDTH).
// u_strip_meta RGBA32UI, 256x1. Per strip slot:
//             R=width (255 already widened to 256), G=height,
//             B=frames | (palette << 8), A=byte offset into u_strips.
//             width==0 marks an empty slot.
// u_palette   RGBA8 (normalized), 256 wide x numPalettes tall. Raw wire
//             palette bytes uploaded as-is: each entry is [0xFF, B, G, R],
//             so sampled texel channels are (r=alpha, g=B, b=G, a=R) and the
//             shader swizzles color.rgb = (texel.a, texel.b, texel.g).
// u_scene     RGBA32UI, SCENE_TEXELS_PER_ENTITY x (spriteCount+tilemapCount).
//             One row per entity: sprite rows first (ascending slot), then
//             tilemap rows (ascending slot). Fields per row (u32 lanes):
//             sprite:  [0]=x (int32 bitcast) [1]=y (int32 bitcast)
//                      [2]=strip [3]=frame [4]=mode [5]=flags(1=flipX,2=flipY)
//             tilemap: [0]=x [1]=y [2]=strip [3]=mode [4]=mapColumns
//                      [5]=mapRows [6]=tileWidth [7]=tileHeight
//                      [8..11]=viewport x/y/w/h [12]=cells byte offset
//             mode is canonical: 0=planet/fullscreen, 1=tunnel, 2=HUD
//             (pack time maps every other value the way the CPU renderers
//             treat it: nonzero and not 1 behaves as HUD).
// u_cells     R8UI, ATLAS_WIDTH wide. All tilemaps' frame-id grids
//             concatenated (row-major, EMPTY_TILE=255 skips a cell).
// u_stars     R32UI, STARS x 1. Per star: x | (y << 8) -- positions already
//             animated for this frame (see computeStarPositions / the
//             desktop's live starfield list).
// u_deepspace R32UI, 256 wide x 2 tall.
//             Row 0, texel y:   deepspace[y] (the forward LUT; 54 = off).
//             Row 1, texel led: yLo | (yHi << 8), the inclusive range of y
//             values with deepspace[y]==led (deepspace is monotonic, so the
//             range is contiguous); 255|0<<8 marks an empty range.
//
// Uniforms: u_sprite_count, u_tilemap_count, u_star_count, u_column_offset,
// and u_led_axis selecting the output orientation (0: x=led, y=column --
// the web ledColorTexture; 1: x=column, y=led -- the desktop
// led_color_texture).

(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.VentilastationSceneShaderCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const COLUMNS = 256;
  const PIXELS = 54;
  const ROWS = 256;
  const STARS = COLUMNS / 2;
  const TRANSPARENT_INDEX = 255;
  const EMPTY_TILE = 255;
  const ATLAS_WIDTH = 2048;
  const SCENE_TEXELS_PER_ENTITY = 4;
  const SCENE_LANES_PER_ENTITY = SCENE_TEXELS_PER_ENTITY * 4;
  const MODE_PLANET = 0;
  const MODE_TUNNEL = 1;
  const MODE_HUD = 2;
  const STAR_GRAY = 64;

  const EMPTY_PIXELS = 16;
  const DEEPSPACE_ROWS = ROWS - EMPTY_PIXELS;
  const GAMMA = 0.28;

  // Identical to led-render-core.js DEEPSPACE / emulator/deepspace.py /
  // gpu.c calculate_deepspace().
  const DEEPSPACE = new Uint8Array(ROWS);
  for (let index = 0; index < EMPTY_PIXELS; index += 1) {
    DEEPSPACE[index] = PIXELS;
  }
  for (let index = EMPTY_PIXELS; index < ROWS; index += 1) {
    const n = ROWS - 1 - index;
    DEEPSPACE[index] = Math.floor(PIXELS * Math.pow(n / DEEPSPACE_ROWS, 1 / GAMMA) + 0.5);
  }

  function positiveMod(value, modulo) {
    return ((value % modulo) + modulo) % modulo;
  }

  // ---------------------------------------------------------------------
  // Packers
  // ---------------------------------------------------------------------

  function packDeepspace() {
    const data = new Uint32Array(256 * 2);
    for (let y = 0; y < ROWS; y += 1) {
      data[y] = DEEPSPACE[y];
    }
    const lo = new Array(PIXELS).fill(255);
    const hi = new Array(PIXELS).fill(0);
    for (let y = 0; y < ROWS; y += 1) {
      const led = DEEPSPACE[y];
      if (led >= PIXELS) {
        continue;
      }
      if (y < lo[led]) {
        lo[led] = y;
      }
      if (y > hi[led]) {
        hi[led] = y;
      }
    }
    for (let led = 0; led < PIXELS; led += 1) {
      data[256 + led] = lo[led] | (hi[led] << 8);
    }
    return { data, width: 256, height: 2 };
  }

  // assets: iterable of [slot, asset] where asset has width/height/frames/
  // palette/data (the app's assetIndex entries, or the desktop's decoded
  // all_strips). Slots outside 0..255 or with missing data pack as empty.
  function packStrips(assets) {
    const meta = new Uint32Array(256 * 4);
    const chunks = [];
    let offset = 0;
    const bySlot = new Map();
    for (const [slot, asset] of assets) {
      bySlot.set(Number(slot), asset);
    }
    for (let slot = 0; slot < 256; slot += 1) {
      const asset = bySlot.get(slot);
      if (!asset || !asset.data || !asset.data.length || !asset.height) {
        continue;
      }
      const width = asset.width === 255 ? 256 : asset.width;
      const base = slot * 4;
      meta[base] = width;
      meta[base + 1] = asset.height;
      meta[base + 2] = (Math.max(asset.frames || 1, 1) & 0xff) | ((asset.palette || 0) << 8);
      meta[base + 3] = offset;
      chunks.push(asset.data);
      offset += asset.data.length;
    }
    const height = Math.max(1, Math.ceil(offset / ATLAS_WIDTH));
    const atlas = new Uint8Array(ATLAS_WIDTH * height);
    let cursor = 0;
    for (const chunk of chunks) {
      atlas.set(chunk, cursor);
      cursor += chunk.length;
    }
    return { atlas, width: ATLAS_WIDTH, height, meta, byteLength: offset };
  }

  // paletteBytes: the raw "palette" wire payload (1024 bytes per palette,
  // entries [0xFF, B, G, R]). Uploaded verbatim as an RGBA8 texture.
  function packPalette(paletteBytes) {
    const rows = Math.max(1, Math.floor((paletteBytes?.length || 0) / 1024));
    const data = new Uint8Array(256 * 4 * rows);
    if (paletteBytes) {
      data.set(paletteBytes.subarray(0, data.length));
    }
    return { data, width: 256, height: rows };
  }

  function canonicalMode(mode) {
    if (mode === MODE_PLANET) {
      return MODE_PLANET;
    }
    if (mode === MODE_TUNNEL) {
      return MODE_TUNNEL;
    }
    // The CPU renderers treat every other nonzero mode (including the
    // legacy table's sign-extended -1) as the HUD mapping.
    return MODE_HUD;
  }

  function makeScenePacker() {
    return { sprites: [], tilemaps: [], cells: [] };
  }

  function pushSprite(packer, { x, y, strip, frame, mode, flipX, flipY }) {
    const lanes = new Uint32Array(SCENE_LANES_PER_ENTITY);
    lanes[0] = x >>> 0;
    lanes[1] = y >>> 0;
    lanes[2] = strip & 0xff;
    lanes[3] = frame & 0xff;
    lanes[4] = canonicalMode(mode);
    lanes[5] = (flipX ? 1 : 0) | (flipY ? 2 : 0);
    packer.sprites.push(lanes);
  }

  function pushTilemap(packer, tilemap) {
    const cells = tilemap.frames;
    let offset = 0;
    for (const existing of packer.cells) {
      offset += existing.length;
    }
    packer.cells.push(cells);
    const lanes = new Uint32Array(SCENE_LANES_PER_ENTITY);
    lanes[0] = tilemap.x >>> 0;
    lanes[1] = tilemap.y >>> 0;
    lanes[2] = tilemap.strip & 0xff;
    lanes[3] = canonicalMode(tilemap.mode);
    lanes[4] = tilemap.columns;
    lanes[5] = tilemap.rows;
    lanes[6] = tilemap.tileWidth;
    lanes[7] = tilemap.tileHeight;
    lanes[8] = tilemap.viewport[0];
    lanes[9] = tilemap.viewport[1];
    lanes[10] = tilemap.viewport[2];
    lanes[11] = tilemap.viewport[3];
    lanes[12] = offset;
    packer.tilemaps.push(lanes);
  }

  function finishScene(packer) {
    const entityCount = packer.sprites.length + packer.tilemaps.length;
    const scene = new Uint32Array(Math.max(entityCount, 1) * SCENE_LANES_PER_ENTITY);
    let row = 0;
    for (const lanes of packer.sprites) {
      scene.set(lanes, row * SCENE_LANES_PER_ENTITY);
      row += 1;
    }
    for (const lanes of packer.tilemaps) {
      scene.set(lanes, row * SCENE_LANES_PER_ENTITY);
      row += 1;
    }
    let cellsLength = 0;
    for (const cells of packer.cells) {
      cellsLength += cells.length;
    }
    const cellsHeight = Math.max(1, Math.ceil(cellsLength / ATLAS_WIDTH));
    const cells = new Uint8Array(ATLAS_WIDTH * cellsHeight);
    let cursor = 0;
    for (const chunk of packer.cells) {
      cells.set(chunk, cursor);
      cursor += chunk.length;
    }
    return {
      scene,
      sceneWidth: SCENE_TEXELS_PER_ENTITY,
      sceneHeight: Math.max(entityCount, 1),
      spriteCount: packer.sprites.length,
      tilemapCount: packer.tilemaps.length,
      cells,
      cellsWidth: ATLAS_WIDTH,
      cellsHeight,
    };
  }

  // The pre-VS2 fixed 100-slot table: 5 bytes per sprite
  // (x, y, strip, frame, perspective as a signed byte); frame 0xFF hides.
  function packSceneLegacy(spriteTableBytes) {
    const packer = makeScenePacker();
    if (spriteTableBytes) {
      const count = Math.floor(spriteTableBytes.length / 5);
      for (let slot = 0; slot < count; slot += 1) {
        const base = slot * 5;
        const frame = spriteTableBytes[base + 3];
        if (frame === 0xff) {
          continue;
        }
        const rawMode = spriteTableBytes[base + 4];
        const mode = rawMode & 0x80 ? rawMode - 0x100 : rawMode;
        pushSprite(packer, {
          x: spriteTableBytes[base],
          y: spriteTableBytes[base + 1],
          strip: spriteTableBytes[base + 2],
          frame,
          mode,
          flipX: false,
          flipY: false,
        });
      }
    }
    return finishScene(packer);
  }

  // Raw VS2 wire payload variant. This intentionally decodes only into the
  // fixed-width GPU records, rather than materialising JS sprite/tilemap
  // objects. The browser receives these bytes once per frame from the WASM
  // bridge, so keeping this conversion allocation-light matters as much as
  // moving the actual 256-column composition to the GPU.
  function packSceneVs2Bytes(bytes) {
    const packer = makeScenePacker();
    if (!(bytes instanceof Uint8Array) || bytes.length < 16 ||
        bytes[0] !== 0x56 || bytes[1] !== 0x53 || bytes[2] !== 0x32 || bytes[3] !== 0) {
      return finishScene(packer);
    }
    const version = bytes[4];
    if (version !== 1 && version !== 2) {
      return finishScene(packer);
    }
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const layerCount = bytes[5];
    const spriteCount = bytes[6];
    const tilemapCount = version >= 2 ? bytes[7] : 0;
    const headerSize = view.getUint16(8, true);
    const layerSize = view.getUint16(10, true);
    const spriteSize = view.getUint16(12, true);
    const tilemapSize = version >= 2 ? view.getUint16(14, true) : 0;
    if (headerSize < 16 || layerSize < 3 || spriteSize < 18 ||
        (version >= 2 && tilemapSize < 32) || headerSize > bytes.length) {
      return finishScene(packer);
    }

    const layers = [];
    let offset = headerSize;
    for (let index = 0; index < layerCount; index += 1) {
      if (offset + layerSize > bytes.length) {
        return finishScene(packer);
      }
      layers[bytes[offset]] = {
        mode: bytes[offset + 1],
        visible: Boolean(bytes[offset + 2] & 1),
      };
      offset += layerSize;
    }

    for (let slot = 0; slot < spriteCount; slot += 1) {
      if (offset + spriteSize > bytes.length) {
        return finishScene(packer);
      }
      const recordOffset = offset;
      offset += spriteSize;
      const flags = bytes[recordOffset + 4];
      const layer = layers[bytes[recordOffset]] || null;
      if (!(flags & 1) || (layer && !layer.visible)) {
        continue;
      }
      pushSprite(packer, {
        x: Math.floor(view.getInt32(recordOffset + 10, true) / 256),
        y: Math.floor(view.getInt32(recordOffset + 14, true) / 256),
        strip: bytes[recordOffset + 1],
        frame: bytes[recordOffset + 2],
        mode: layer ? layer.mode : bytes[recordOffset + 3],
        flipX: Boolean(flags & 2),
        flipY: Boolean(flags & 4),
      });
    }

    for (let slot = 0; slot < tilemapCount; slot += 1) {
      if (offset + tilemapSize > bytes.length) {
        return finishScene(packer);
      }
      const recordOffset = offset;
      offset += tilemapSize;
      const flags = bytes[recordOffset + 2];
      const layer = layers[bytes[recordOffset]] || null;
      if (!(flags & 1) || (layer && !layer.visible)) {
        continue;
      }
      const columns = view.getUint16(recordOffset + 4, true);
      const rows = view.getUint16(recordOffset + 6, true);
      const cellsLength = columns * rows;
      const framesOffset = view.getUint32(recordOffset + 28, true);
      if (framesOffset + cellsLength > bytes.length) {
        continue;
      }
      const mode = layer ? layer.mode : bytes[recordOffset + 3];
      if (canonicalMode(mode) === MODE_PLANET) {
        continue; // FULLSCREEN tilemaps are unsupported in every renderer.
      }
      pushTilemap(packer, {
        x: Math.floor(view.getInt32(recordOffset + 20, true) / 256),
        y: Math.floor(view.getInt32(recordOffset + 24, true) / 256),
        strip: bytes[recordOffset + 1],
        mode,
        columns,
        rows,
        tileWidth: view.getUint16(recordOffset + 8, true),
        tileHeight: view.getUint16(recordOffset + 10, true),
        viewport: [
          view.getUint16(recordOffset + 12, true),
          view.getUint16(recordOffset + 14, true),
          view.getUint16(recordOffset + 16, true),
          view.getUint16(recordOffset + 18, true),
        ],
        frames: bytes.subarray(framesOffset, framesOffset + cellsLength),
      });
    }
    return finishScene(packer);
  }

  // scene: a decoded VS2 scene -- led-render-core.js decodeVs2SceneBuffer's
  // shape ({sprites: [{slot, x, y, image_strip, frame, perspective, vs2:
  // {flip_x, flip_y}}], tilemaps: [...]}) or the desktop decode_vs2_scene
  // shape ({sprites: [{slot, x, y, image, frame, perspective, flip_x,
  // flip_y}], tilemaps: [...]}). Both list only visible entities in slot
  // order with layer modes already resolved.
  function packSceneVs2(scene) {
    if (scene instanceof Uint8Array) {
      return packSceneVs2Bytes(scene);
    }
    const packer = makeScenePacker();
    for (const sprite of scene?.sprites || []) {
      pushSprite(packer, {
        x: Math.floor(sprite.x || 0),
        y: Math.floor(sprite.y || 0),
        strip: sprite.image_strip ?? sprite.image,
        frame: sprite.frame || 0,
        mode: sprite.perspective,
        flipX: Boolean(sprite.vs2 ? sprite.vs2.flip_x : sprite.flip_x),
        flipY: Boolean(sprite.vs2 ? sprite.vs2.flip_y : sprite.flip_y),
      });
    }
    for (const tilemap of scene?.tilemaps || []) {
      if (canonicalMode(tilemap.perspective) === MODE_PLANET) {
        continue; // FULLSCREEN tilemaps are unsupported, same as the CPU path
      }
      pushTilemap(packer, {
        x: Math.floor(tilemap.x || 0),
        y: Math.floor(tilemap.y || 0),
        strip: tilemap.image_strip ?? tilemap.image,
        mode: tilemap.perspective,
        columns: tilemap.columns,
        rows: tilemap.rows,
        tileWidth: tilemap.tile_width,
        tileHeight: tilemap.tile_height,
        viewport: tilemap.viewport,
        frames: tilemap.frames,
      });
    }
    return finishScene(packer);
  }

  // The web starfield, animated for a given tick -- identical math to
  // led-render-core.js drawStarfield, but producing (x, wrappedY) pairs so
  // the same packStars() serves the desktop's live (x, y) starfield list.
  function createRng(seed) {
    let state = seed >>> 0;
    return function next() {
      state = (1664525 * state + 1013904223) >>> 0;
      return state / 0x100000000;
    };
  }

  const webStarfield = (() => {
    const random = createRng(0x1badf00d);
    return Array.from({ length: STARS }, () => ({
      x0: Math.floor(random() * COLUMNS),
      y0: Math.floor(random() * ROWS),
      wraps: Array.from({ length: 8 }, () => Math.floor(random() * COLUMNS)),
    }));
  })();

  function computeStarPositions(frameNumber) {
    const ticks = Math.max(0, Number(frameNumber || 0));
    return webStarfield.map((star) => {
      const wrappedY = positiveMod(star.y0 - ticks, ROWS);
      const wrapCount = Math.floor((ticks + (ROWS - 1 - star.y0)) / ROWS);
      const x = wrapCount <= 0
        ? star.x0
        : star.wraps[(wrapCount - 1) % star.wraps.length];
      return { x, y: wrappedY };
    });
  }

  // positions: [{x, y}] with 0 <= x < COLUMNS, 0 <= y < ROWS. The star is
  // rendered at renderColumn == x, led == deepspace[y] (the CPU paths apply
  // the column offset to stars and sprites identically once both are
  // expressed against renderColumn).
  function packStars(positions) {
    const data = new Uint32Array(STARS);
    const count = Math.min(positions.length, STARS);
    for (let index = 0; index < count; index += 1) {
      data[index] = (positions[index].x & 0xff) | ((positions[index].y & 0xff) << 8);
    }
    return { data, width: STARS, height: 1, count };
  }

  // ---------------------------------------------------------------------
  // Software executor: the shader algorithm, interpreted on the CPU from
  // the packed buffers. Mirrors the GLSL below function-for-function; when
  // editing one, edit the other.
  // ---------------------------------------------------------------------

  function makeSoftwareContext(packed) {
    return {
      strips: packed.strips,
      palette: packed.palette,
      scene: packed.sceneData,
      stars: packed.stars,
      deepspace: packed.deepspace,
    };
  }

  function stripByte(strips, globalOffset) {
    return strips.atlas[globalOffset] ?? 0;
  }

  function cellByte(sceneData, globalOffset) {
    return sceneData.cells[globalOffset] ?? 0;
  }

  function sceneLane(sceneData, entityRow, lane) {
    return sceneData.scene[entityRow * SCENE_LANES_PER_ENTITY + lane];
  }

  function asInt32(value) {
    return value | 0;
  }

  function paletteColor(context, paletteIndex, colorIndex) {
    const base = (Math.min(paletteIndex, context.palette.height - 1) * 256 + colorIndex) * 4;
    const bytes = context.palette.data;
    // Wire entry [0xFF, B, G, R] -> output RGBA.
    return [bytes[base + 3] || 0, bytes[base + 2] || 0, bytes[base + 1] || 0, 255];
  }

  function sourceColumnFor(x, width, renderColumn, flipX) {
    const spriteColumn = width - 1 - positiveMod(renderColumn - x, COLUMNS);
    if (spriteColumn < 0 || spriteColumn >= width) {
      return -1;
    }
    return flipX ? width - 1 - spriteColumn : spriteColumn;
  }

  function deepspaceAt(context, y) {
    return context.deepspace.data[y];
  }

  function deepspaceRange(context, led) {
    const packedRange = context.deepspace.data[256 + led];
    return [packedRange & 0xff, (packedRange >> 8) & 0xff];
  }

  function probeSprite(context, entityRow, renderColumn, led) {
    const meta = context.strips.meta;
    const strip = sceneLane(context.scene, entityRow, 2);
    const width = meta[strip * 4];
    const height = meta[strip * 4 + 1];
    if (width === 0 || height === 0) {
      return null;
    }
    const framesAndPalette = meta[strip * 4 + 2];
    const totalFrames = Math.max(framesAndPalette & 0xff, 1);
    const paletteIndex = framesAndPalette >> 8;
    const stripOffset = meta[strip * 4 + 3];

    const x = asInt32(sceneLane(context.scene, entityRow, 0));
    const y = asInt32(sceneLane(context.scene, entityRow, 1));
    const frame = sceneLane(context.scene, entityRow, 3) % totalFrames;
    const mode = sceneLane(context.scene, entityRow, 4);
    const flags = sceneLane(context.scene, entityRow, 5);
    const flipY = (flags & 2) !== 0;

    const sourceColumn = sourceColumnFor(x, width, renderColumn, (flags & 1) !== 0);
    if (sourceColumn === -1) {
      return null;
    }
    const base = stripOffset + sourceColumn * height + frame * width * height;

    if (mode === MODE_PLANET) {
      const zleds = deepspaceAt(context, Math.max(0, Math.min(255 - y, ROWS - 1)));
      if (led >= zleds) {
        return null;
      }
      let sourceRow = Math.floor((led * PIXELS) / zleds);
      if (sourceRow >= height) {
        return null;
      }
      if (!flipY) {
        sourceRow = height - 1 - sourceRow;
      }
      const colorIndex = stripByte(context.strips, base + sourceRow);
      if (colorIndex === TRANSPARENT_INDEX) {
        return null;
      }
      return paletteColor(context, paletteIndex, colorIndex);
    }

    if (mode === MODE_HUD) {
      const destY = PIXELS - 1 - led;
      if (destY < y || destY >= y + height || destY >= ROWS) {
        return null;
      }
      let sourceRow = destY - y;
      if (flipY) {
        sourceRow = height - 1 - sourceRow;
      }
      const colorIndex = stripByte(context.strips, base + sourceRow);
      if (colorIndex === TRANSPARENT_INDEX) {
        return null;
      }
      return paletteColor(context, paletteIndex, colorIndex);
    }

    // Tunnel: several y rows can map to this led; the CPU writes ascending
    // y, so scan descending and keep the first opaque pixel.
    if (led >= PIXELS) {
      return null;
    }
    const [rangeLo, rangeHi] = deepspaceRange(context, led);
    const scanLo = Math.max(rangeLo, y, 0);
    const scanHi = Math.min(rangeHi, y + height - 1, ROWS - 1);
    for (let destY = scanHi; destY >= scanLo; destY -= 1) {
      let sourceRow = destY - y;
      if (flipY) {
        sourceRow = height - 1 - sourceRow;
      }
      const colorIndex = stripByte(context.strips, base + sourceRow);
      if (colorIndex !== TRANSPARENT_INDEX) {
        return paletteColor(context, paletteIndex, colorIndex);
      }
    }
    return null;
  }

  function probeTilemap(context, entityRow, renderColumn, led) {
    const meta = context.strips.meta;
    const strip = sceneLane(context.scene, entityRow, 2);
    const width = meta[strip * 4];
    const height = meta[strip * 4 + 1];
    if (width === 0 || height === 0) {
      return null;
    }
    const framesAndPalette = meta[strip * 4 + 2];
    const totalFrames = Math.max(framesAndPalette & 0xff, 1);
    const paletteIndex = framesAndPalette >> 8;
    const stripOffset = meta[strip * 4 + 3];

    const tileWidth = sceneLane(context.scene, entityRow, 6);
    const tileHeight = sceneLane(context.scene, entityRow, 7);
    if (width !== tileWidth || height !== tileHeight) {
      return null;
    }
    const mapColumns = sceneLane(context.scene, entityRow, 4);
    const mapRows = sceneLane(context.scene, entityRow, 5);
    const mapWidth = mapColumns * tileWidth;
    const mapHeight = mapRows * tileHeight;
    const viewportX = sceneLane(context.scene, entityRow, 8);
    const viewportY = sceneLane(context.scene, entityRow, 9);
    if (viewportX >= mapWidth || viewportY >= mapHeight) {
      return null;
    }
    const viewportW = Math.min(sceneLane(context.scene, entityRow, 10), mapWidth - viewportX);
    const viewportH = Math.min(sceneLane(context.scene, entityRow, 11), mapHeight - viewportY);
    const cellsOffset = sceneLane(context.scene, entityRow, 12);

    const x = asInt32(sceneLane(context.scene, entityRow, 0));
    const y = asInt32(sceneLane(context.scene, entityRow, 1));
    const mode = sceneLane(context.scene, entityRow, 3);

    const delta = positiveMod(renderColumn - x, COLUMNS);
    if (delta >= viewportW) {
      return null;
    }
    const sx = viewportX + delta;
    const tileCol = Math.floor(sx / tileWidth);
    // strip data columns are stored mirrored, same as sprites
    const sourceColumn = tileWidth - 1 - (sx % tileWidth);

    const probeRow = (destY) => {
      if (destY < Math.max(y, 0) || destY >= Math.min(y + viewportH, ROWS)) {
        return null;
      }
      const sy = viewportY + (destY - y);
      let frameId = cellByte(context.scene, cellsOffset + Math.floor(sy / tileHeight) * mapColumns + tileCol);
      if (frameId === EMPTY_TILE) {
        return null;
      }
      frameId %= totalFrames;
      const colorIndex = stripByte(
        context.strips,
        stripOffset + sourceColumn * tileHeight + frameId * tileWidth * tileHeight + (sy % tileHeight),
      );
      if (colorIndex === TRANSPARENT_INDEX) {
        return null;
      }
      return paletteColor(context, paletteIndex, colorIndex);
    };

    if (mode === MODE_HUD) {
      return probeRow(PIXELS - 1 - led);
    }
    if (led >= PIXELS) {
      return null;
    }
    const [rangeLo, rangeHi] = deepspaceRange(context, led);
    for (let destY = rangeHi; destY >= rangeLo; destY -= 1) {
      const color = probeRow(destY);
      if (color) {
        return color;
      }
    }
    return null;
  }

  function probeStars(context, renderColumn, led) {
    for (let index = 0; index < context.stars.count; index += 1) {
      const packedStar = context.stars.data[index];
      if ((packedStar & 0xff) !== renderColumn) {
        continue;
      }
      if (deepspaceAt(context, (packedStar >> 8) & 0xff) === led) {
        return [STAR_GRAY, STAR_GRAY, STAR_GRAY, 255];
      }
    }
    return null;
  }

  function shadeLed(context, sceneData, column, led, columnOffset) {
    const renderColumn = (column + columnOffset) & (COLUMNS - 1);
    for (let row = 0; row < sceneData.spriteCount; row += 1) {
      const color = probeSprite(context, row, renderColumn, led);
      if (color) {
        return color;
      }
    }
    for (let row = 0; row < sceneData.tilemapCount; row += 1) {
      const color = probeTilemap(context, sceneData.spriteCount + row, renderColumn, led);
      if (color) {
        return color;
      }
    }
    const starColor = probeStars(context, renderColumn, led);
    if (starColor) {
      return starColor;
    }
    return [0, 0, 0, 255];
  }

  // Renders the whole frame from packed buffers. Output matches
  // computeLedFramePixels: RGBA, column-major/led-minor.
  function renderSceneSoftware({ strips, palette, sceneData, stars, deepspace, columnOffset = 0 }) {
    const context = makeSoftwareContext({ strips, palette, sceneData, stars, deepspace });
    const offset = positiveMod(Number(columnOffset || 0), COLUMNS);
    const pixels = new Uint8Array(COLUMNS * PIXELS * 4);
    for (let column = 0; column < COLUMNS; column += 1) {
      for (let led = 0; led < PIXELS; led += 1) {
        const color = shadeLed(context, sceneData, column, led, offset);
        const dest = (column * PIXELS + led) * 4;
        pixels[dest] = color[0];
        pixels[dest + 1] = color[1];
        pixels[dest + 2] = color[2];
        pixels[dest + 3] = color[3];
      }
    }
    return pixels;
  }

  // ---------------------------------------------------------------------
  // GLSL: the same algorithm as the software executor above, transcribed.
  // Requires OpenGL 3.3 core (desktop) or OpenGL ES 3.0 / WebGL2 (web).
  // ---------------------------------------------------------------------

  const SCENE_VERTEX_SOURCE_BODY = `
layout(location = 0) in vec2 a_position;
void main() {
  gl_Position = vec4(a_position, 0.0, 1.0);
}
`;

  const SCENE_FRAGMENT_SOURCE_BODY = `
uniform highp usampler2D u_strips;
uniform highp usampler2D u_strip_meta;
uniform sampler2D u_palette;
uniform highp usampler2D u_scene;
uniform highp usampler2D u_cells;
uniform highp usampler2D u_stars;
uniform highp usampler2D u_deepspace;
uniform int u_sprite_count;
uniform int u_tilemap_count;
uniform int u_star_count;
uniform int u_column_offset;
uniform int u_led_axis;
out vec4 out_color;

const int COLUMNS = 256;
const int PIXELS = 54;
const int ROWS = 256;
const int ATLAS_WIDTH = ${ATLAS_WIDTH};
const int TRANSPARENT_INDEX = 255;
const int EMPTY_TILE = 255;
const int MODE_PLANET = 0;
const int MODE_TUNNEL = 1;

int stripByte(int offset) {
  return int(texelFetch(u_strips, ivec2(offset % ATLAS_WIDTH, offset / ATLAS_WIDTH), 0).r);
}

int cellByte(int offset) {
  return int(texelFetch(u_cells, ivec2(offset % ATLAS_WIDTH, offset / ATLAS_WIDTH), 0).r);
}

uvec4 sceneTexel(int row, int texel) {
  return texelFetch(u_scene, ivec2(texel, row), 0);
}

int deepspaceAt(int y) {
  return int(texelFetch(u_deepspace, ivec2(y, 0), 0).r);
}

ivec2 deepspaceRange(int led) {
  uint packedRange = texelFetch(u_deepspace, ivec2(led, 1), 0).r;
  return ivec2(int(packedRange & 255u), int((packedRange >> 8) & 255u));
}

vec4 paletteColor(int paletteIndex, int colorIndex) {
  // Wire entry [0xFF, B, G, R]: texel channels (alpha, B, G, R).
  vec4 texel = texelFetch(u_palette, ivec2(colorIndex, paletteIndex), 0);
  return vec4(texel.a, texel.b, texel.g, 1.0);
}

int positiveMod(int value, int modulo) {
  int wrapped = value % modulo;
  return wrapped < 0 ? wrapped + modulo : wrapped;
}

int sourceColumnFor(int x, int width, int renderColumn, bool flipX) {
  int spriteColumn = width - 1 - positiveMod(renderColumn - x, COLUMNS);
  if (spriteColumn < 0 || spriteColumn >= width) {
    return -1;
  }
  return flipX ? width - 1 - spriteColumn : spriteColumn;
}

bool probeSprite(int row, int renderColumn, int led, out vec4 color) {
  int strip = int(sceneTexel(row, 0).z);
  uvec4 meta = texelFetch(u_strip_meta, ivec2(strip, 0), 0);
  int width = int(meta.r);
  int height = int(meta.g);
  if (width == 0 || height == 0) {
    return false;
  }
  int totalFrames = max(int(meta.b & 255u), 1);
  int paletteIndex = int(meta.b >> 8);
  int stripOffset = int(meta.a);

  uvec4 texel0 = sceneTexel(row, 0);
  uvec4 texel1 = sceneTexel(row, 1);
  int x = int(texel0.x);
  int y = int(texel0.y);
  int frame = int(texel0.w) % totalFrames;
  int mode = int(texel1.x);
  int flags = int(texel1.y);
  bool flipY = (flags & 2) != 0;

  int sourceColumn = sourceColumnFor(x, width, renderColumn, (flags & 1) != 0);
  if (sourceColumn == -1) {
    return false;
  }
  int base = stripOffset + sourceColumn * height + frame * width * height;

  if (mode == MODE_PLANET) {
    int zleds = deepspaceAt(clamp(255 - y, 0, ROWS - 1));
    if (led >= zleds) {
      return false;
    }
    int sourceRow = (led * PIXELS) / zleds;
    if (sourceRow >= height) {
      return false;
    }
    if (!flipY) {
      sourceRow = height - 1 - sourceRow;
    }
    int colorIndex = stripByte(base + sourceRow);
    if (colorIndex == TRANSPARENT_INDEX) {
      return false;
    }
    color = paletteColor(paletteIndex, colorIndex);
    return true;
  }

  if (mode != MODE_TUNNEL) {
    int destY = PIXELS - 1 - led;
    if (destY < y || destY >= y + height || destY >= ROWS) {
      return false;
    }
    int sourceRow = destY - y;
    if (flipY) {
      sourceRow = height - 1 - sourceRow;
    }
    int colorIndex = stripByte(base + sourceRow);
    if (colorIndex == TRANSPARENT_INDEX) {
      return false;
    }
    color = paletteColor(paletteIndex, colorIndex);
    return true;
  }

  // Tunnel: the CPU writes ascending y with overwrite, so scan the y range
  // mapping to this led descending and keep the first opaque pixel.
  if (led >= PIXELS) {
    return false;
  }
  ivec2 range = deepspaceRange(led);
  int scanLo = max(range.x, max(y, 0));
  int scanHi = min(range.y, min(y + height - 1, ROWS - 1));
  for (int destY = scanHi; destY >= scanLo; destY--) {
    int sourceRow = destY - y;
    if (flipY) {
      sourceRow = height - 1 - sourceRow;
    }
    int colorIndex = stripByte(base + sourceRow);
    if (colorIndex != TRANSPARENT_INDEX) {
      color = paletteColor(paletteIndex, colorIndex);
      return true;
    }
  }
  return false;
}

bool probeTilemapRow(int destY, int y, int viewportY, int viewportH, int tileHeight,
                     int mapColumns, int tileCol, int cellsOffset, int totalFrames,
                     int stripOffset, int sourceColumn, int tileWidth, int paletteIndex,
                     out vec4 color) {
  if (destY < max(y, 0) || destY >= min(y + viewportH, ROWS)) {
    return false;
  }
  int sy = viewportY + (destY - y);
  int frameId = cellByte(cellsOffset + (sy / tileHeight) * mapColumns + tileCol);
  if (frameId == EMPTY_TILE) {
    return false;
  }
  frameId = frameId % totalFrames;
  int colorIndex = stripByte(
    stripOffset + sourceColumn * tileHeight + frameId * tileWidth * tileHeight + (sy % tileHeight));
  if (colorIndex == TRANSPARENT_INDEX) {
    return false;
  }
  color = paletteColor(paletteIndex, colorIndex);
  return true;
}

bool probeTilemap(int row, int renderColumn, int led, out vec4 color) {
  int strip = int(sceneTexel(row, 0).z);
  uvec4 meta = texelFetch(u_strip_meta, ivec2(strip, 0), 0);
  int width = int(meta.r);
  int height = int(meta.g);
  if (width == 0 || height == 0) {
    return false;
  }
  int totalFrames = max(int(meta.b & 255u), 1);
  int paletteIndex = int(meta.b >> 8);
  int stripOffset = int(meta.a);

  uvec4 texel0 = sceneTexel(row, 0);
  uvec4 texel1 = sceneTexel(row, 1);
  uvec4 texel2 = sceneTexel(row, 2);
  uvec4 texel3 = sceneTexel(row, 3);
  int tileWidth = int(texel1.z);
  int tileHeight = int(texel1.w);
  if (width != tileWidth || height != tileHeight) {
    return false;
  }
  int mapColumns = int(texel1.x);
  int mapRows = int(texel1.y);
  int mapWidth = mapColumns * tileWidth;
  int mapHeight = mapRows * tileHeight;
  int viewportX = int(texel2.x);
  int viewportY = int(texel2.y);
  if (viewportX >= mapWidth || viewportY >= mapHeight) {
    return false;
  }
  int viewportW = min(int(texel2.z), mapWidth - viewportX);
  int viewportH = min(int(texel2.w), mapHeight - viewportY);
  int cellsOffset = int(texel3.x);

  int x = int(texel0.x);
  int y = int(texel0.y);
  int mode = int(texel0.w);

  int delta = positiveMod(renderColumn - x, COLUMNS);
  if (delta >= viewportW) {
    return false;
  }
  int sx = viewportX + delta;
  int tileCol = sx / tileWidth;
  // strip data columns are stored mirrored, same as sprites
  int sourceColumn = tileWidth - 1 - (sx % tileWidth);

  if (mode != MODE_TUNNEL) {
    return probeTilemapRow(PIXELS - 1 - led, y, viewportY, viewportH, tileHeight,
                           mapColumns, tileCol, cellsOffset, totalFrames,
                           stripOffset, sourceColumn, tileWidth, paletteIndex, color);
  }
  if (led >= PIXELS) {
    return false;
  }
  ivec2 range = deepspaceRange(led);
  for (int destY = range.y; destY >= range.x; destY--) {
    if (probeTilemapRow(destY, y, viewportY, viewportH, tileHeight,
                        mapColumns, tileCol, cellsOffset, totalFrames,
                        stripOffset, sourceColumn, tileWidth, paletteIndex, color)) {
      return true;
    }
  }
  return false;
}

bool probeStars(int renderColumn, int led, out vec4 color) {
  for (int index = 0; index < u_star_count; index++) {
    uint packedStar = texelFetch(u_stars, ivec2(index, 0), 0).r;
    if (int(packedStar & 255u) != renderColumn) {
      continue;
    }
    if (deepspaceAt(int((packedStar >> 8) & 255u)) == led) {
      color = vec4(vec3(64.0 / 255.0), 1.0);
      return true;
    }
  }
  return false;
}

void main() {
  ivec2 fragCoord = ivec2(gl_FragCoord.xy);
  int column = (u_led_axis == 1) ? fragCoord.x : fragCoord.y;
  int led = (u_led_axis == 1) ? fragCoord.y : fragCoord.x;
  int renderColumn = (column + u_column_offset) & (COLUMNS - 1);

  vec4 color;
  for (int row = 0; row < u_sprite_count; row++) {
    if (probeSprite(row, renderColumn, led, color)) {
      out_color = color;
      return;
    }
  }
  for (int row = 0; row < u_tilemap_count; row++) {
    if (probeTilemap(u_sprite_count + row, renderColumn, led, color)) {
      out_color = color;
      return;
    }
  }
  if (probeStars(renderColumn, led, color)) {
    out_color = color;
    return;
  }
  out_color = vec4(0.0, 0.0, 0.0, 1.0);
}
`;

  function buildSceneVertexSource({ es }) {
    return (es ? "#version 300 es\nprecision highp float;\n" : "#version 330 core\n")
      + SCENE_VERTEX_SOURCE_BODY;
  }

  function buildSceneFragmentSource({ es }) {
    return (es
      ? "#version 300 es\nprecision highp float;\nprecision highp int;\n"
      : "#version 330 core\n")
      + SCENE_FRAGMENT_SOURCE_BODY;
  }

  return {
    COLUMNS,
    PIXELS,
    ROWS,
    STARS,
    ATLAS_WIDTH,
    SCENE_TEXELS_PER_ENTITY,
    SCENE_LANES_PER_ENTITY,
    DEEPSPACE,
    packDeepspace,
    packStrips,
    packPalette,
    packSceneLegacy,
    packSceneVs2,
    packSceneVs2Bytes,
    packStars,
    computeStarPositions,
    renderSceneSoftware,
    buildSceneVertexSource,
    buildSceneFragmentSource,
  };
});
