(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.VentilastationLedRenderCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const COLUMNS = 256;
  const PIXELS = 54;
  const TRANSPARENT_INDEX = 255;
  const EMPTY_TILE = 255;
  const VS2_MAGIC = "VS2\0";
  const VS2_VERSION = 1;
  const VS2_VERSION_TILEMAPS = 2;
  const VS2_FLAG_VISIBLE = 0x01;
  const VS2_FLAG_FLIP_X = 0x02;
  const VS2_FLAG_FLIP_Y = 0x04;
  const ROWS = 256;
  const STARS = COLUMNS / 2;
  const STAR_COLOR = [64, 64, 64, 255];
  const LED_SIZE = 100;
  const EMPTY_PIXELS = 16;
  const DEEPSPACE_ROWS = ROWS - EMPTY_PIXELS;
  const GAMMA = 0.28;
  const DEEPSPACE = new Uint8Array([
    ...new Array(EMPTY_PIXELS).fill(PIXELS),
    ...Array.from({ length: DEEPSPACE_ROWS }, (_, index) => {
      const n = DEEPSPACE_ROWS - 1 - index;
      return Math.round(PIXELS * Math.pow(n / DEEPSPACE_ROWS, 1 / GAMMA));
    }),
  ]);

  function createRng(seed) {
    let state = seed >>> 0;
    return function next() {
      state = (1664525 * state + 1013904223) >>> 0;
      return state / 0x100000000;
    };
  }

  const starfield = (() => {
    const random = createRng(0x1badf00d);
    return Array.from({ length: STARS }, () => ({
      x0: Math.floor(random() * COLUMNS),
      y0: Math.floor(random() * ROWS),
      wraps: Array.from({ length: 8 }, () => Math.floor(random() * COLUMNS)),
    }));
  })();

  function positiveMod(value, modulo) {
    return ((value % modulo) + modulo) % modulo;
  }

  function readAscii(bytes, offset, length) {
    let value = "";
    for (let index = 0; index < length; index += 1) {
      value += String.fromCharCode(bytes[offset + index] || 0);
    }
    return value;
  }

  function decodeVs2SceneBuffer(buffer) {
    if (!(buffer instanceof Uint8Array) || buffer.length < 16) {
      return { version: 0, layers: [], sprites: [], tilemaps: [] };
    }
    if (readAscii(buffer, 0, 4) !== VS2_MAGIC) {
      return { version: 0, layers: [], sprites: [], tilemaps: [] };
    }
    const view = new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength);
    const version = buffer[4];
    if (version !== VS2_VERSION && version !== VS2_VERSION_TILEMAPS) {
      return { version, layers: [], sprites: [], tilemaps: [] };
    }
    const layerCount = buffer[5];
    const spriteCount = buffer[6];
    const tilemapCount = version >= VS2_VERSION_TILEMAPS ? buffer[7] : 0;
    const headerSize = view.getUint16(8, true);
    const layerSize = view.getUint16(10, true);
    const spriteSize = view.getUint16(12, true);
    const tilemapSize = version >= VS2_VERSION_TILEMAPS ? view.getUint16(14, true) : 0;
    const layers = [];
    let offset = headerSize;
    for (let index = 0; index < layerCount; index += 1) {
      if (offset + layerSize > buffer.length) {
        return { version, layers: [], sprites: [], tilemaps: [] };
      }
      layers.push({
        id: buffer[offset],
        mode: buffer[offset + 1],
        visible: Boolean(buffer[offset + 2] & VS2_FLAG_VISIBLE),
      });
      offset += layerSize;
    }

    const sprites = [];
    const tilemaps = [];
    for (let slot = 0; slot < spriteCount; slot += 1) {
      if (offset + spriteSize > buffer.length) {
        return { version, layers, sprites, tilemaps };
      }
      const layerId = buffer[offset];
      const strip = buffer[offset + 1];
      const frame = buffer[offset + 2];
      let mode = buffer[offset + 3];
      const flags = buffer[offset + 4];
      const layer = layers[layerId] || null;
      offset += spriteSize;
      if (!(flags & VS2_FLAG_VISIBLE)) {
        continue;
      }
      if (layer && !layer.visible) {
        continue;
      }
      if (layer) {
        mode = layer.mode;
      }
      const xFixed = view.getInt32(offset - spriteSize + 10, true);
      const yFixed = view.getInt32(offset - spriteSize + 14, true);
      const x = xFixed / 256;
      const y = yFixed / 256;
      sprites.push({
        slot,
        x,
        y,
        image_strip: strip,
        frame,
        perspective: mode,
        vs2: {
          layer: layerId,
          x,
          y,
          flags,
          flip_x: Boolean(flags & VS2_FLAG_FLIP_X),
          flip_y: Boolean(flags & VS2_FLAG_FLIP_Y),
        },
      });
    }

    for (let slot = 0; slot < tilemapCount; slot += 1) {
      if (offset + tilemapSize > buffer.length) {
        return { version, layers, sprites, tilemaps };
      }
      const layerId = buffer[offset];
      const strip = buffer[offset + 1];
      const flags = buffer[offset + 2];
      let mode = buffer[offset + 3];
      const mapColumns = view.getUint16(offset + 4, true);
      const mapRows = view.getUint16(offset + 6, true);
      const tileWidth = view.getUint16(offset + 8, true);
      const tileHeight = view.getUint16(offset + 10, true);
      const viewport = [
        view.getUint16(offset + 12, true),
        view.getUint16(offset + 14, true),
        view.getUint16(offset + 16, true),
        view.getUint16(offset + 18, true),
      ];
      const x = view.getInt32(offset + 20, true) / 256;
      const y = view.getInt32(offset + 24, true) / 256;
      const framesOffset = view.getUint32(offset + 28, true);
      const layer = layers[layerId] || null;
      offset += tilemapSize;
      const cells = mapColumns * mapRows;
      if (framesOffset + cells > buffer.length) {
        continue;
      }
      if (!(flags & VS2_FLAG_VISIBLE)) {
        continue;
      }
      if (layer && !layer.visible) {
        continue;
      }
      if (layer) {
        mode = layer.mode;
      }
      tilemaps.push({
        slot,
        x,
        y,
        image_strip: strip,
        // copy the frame ids: the transport buffer is reused between frames
        frames: buffer.slice(framesOffset, framesOffset + cells),
        columns: mapColumns,
        rows: mapRows,
        tile_width: tileWidth,
        tile_height: tileHeight,
        viewport,
        perspective: mode,
      });
    }
    return { version, layers, sprites, tilemaps };
  }

  function getVisibleColumn(spriteX, spriteWidth, renderColumn) {
    const spriteColumn = spriteWidth - 1 - positiveMod(renderColumn - spriteX, COLUMNS);
    if (spriteColumn >= 0 && spriteColumn < spriteWidth) {
      return spriteColumn;
    }
    return -1;
  }

  function getSourceColumn(sprite, spriteWidth, renderColumn) {
    const spriteX = sprite?.vs2 ? Math.floor(sprite.x || 0) : sprite.x || 0;
    const spriteColumn = getVisibleColumn(spriteX, spriteWidth, renderColumn);
    if (spriteColumn === -1) {
      return -1;
    }
    if (sprite?.vs2?.flip_x) {
      return spriteWidth - 1 - spriteColumn;
    }
    return spriteColumn;
  }

  function getSourceRow(sprite, sourceRow, spriteHeight) {
    if (sprite?.vs2?.flip_y) {
      return spriteHeight - 1 - sourceRow;
    }
    return sourceRow;
  }

  function getLedOffset(column, led) {
    if (column < 0 || column >= COLUMNS || led < 0 || led >= PIXELS) {
      return -1;
    }
    return (column * PIXELS + led) * 4;
  }

  function setLedColor(buffer, column, led, red, green, blue, alpha) {
    const offset = getLedOffset(column, led);
    if (offset === -1) {
      return;
    }
    buffer[offset] = red;
    buffer[offset + 1] = green;
    buffer[offset + 2] = blue;
    buffer[offset + 3] = alpha;
  }

  function setLedColorFromPalette(buffer, palette, paletteIndex, colorIndex, column, led) {
    const offset = getLedOffset(column, led);
    if (offset === -1) {
      return;
    }
    const paletteOffset = (paletteIndex * 256 + colorIndex) * 4;
    buffer[offset] = palette[paletteOffset + 3] || 0;
    buffer[offset + 1] = palette[paletteOffset + 2] || 0;
    buffer[offset + 2] = palette[paletteOffset + 1] || 0;
    buffer[offset + 3] = 255;
  }

  function clamp(value, minimum, maximum) {
    if (value < minimum) {
      return minimum;
    }
    if (value > maximum) {
      return maximum;
    }
    return value;
  }

  function spritePixelY(sprite) {
    return sprite?.vs2 ? Math.floor(sprite.y || 0) : Math.trunc(sprite.y || 0);
  }

  function getFrameIndex(frame, totalFrames) {
    if (!totalFrames || totalFrames <= 0) {
      return 0;
    }
    return positiveMod(frame, totalFrames);
  }

  function drawStarfield(pixels, frameNumber, columnOffset) {
    const ticks = Math.max(0, Number(frameNumber || 0));
    for (const star of starfield) {
      const total = star.y0 - ticks;
      const wrappedY = positiveMod(total, ROWS);
      const wrapCount = Math.floor((ticks + (ROWS - 1 - star.y0)) / ROWS);
      const x = wrapCount <= 0
        ? star.x0
        : star.wraps[(wrapCount - 1) % star.wraps.length];
      const renderColumn = positiveMod(x - columnOffset, COLUMNS);
      const led = DEEPSPACE[wrappedY];
      if (led < PIXELS) {
        setLedColor(pixels, renderColumn, led, STAR_COLOR[0], STAR_COLOR[1], STAR_COLOR[2], STAR_COLOR[3]);
      }
    }
  }

  function drawTilemapColumn(pixels, tilemap, assetIndex, palette, column, renderColumn) {
    // FULLSCREEN tilemaps are unsupported; only TUNNEL (1) and HUD (2) render.
    const perspective = tilemap.perspective;
    if (!perspective) {
      return;
    }
    const asset = assetIndex.get(tilemap.image_strip);
    if (!asset || !(asset.data instanceof Uint8Array) || asset.loadedBytes < asset.dataLength) {
      return;
    }
    const width = asset.width === 255 ? 256 : asset.width;
    const height = asset.height || 0;
    const tileWidth = tilemap.tile_width;
    const tileHeight = tilemap.tile_height;
    if (width !== tileWidth || height !== tileHeight) {
      return;
    }
    const totalFrames = Math.max(asset.frames || 1, 1);
    const mapColumns = tilemap.columns;
    const mapWidth = mapColumns * tileWidth;
    const mapHeight = tilemap.rows * tileHeight;
    let [viewportX, viewportY, viewportW, viewportH] = tilemap.viewport;
    if (viewportX >= mapWidth || viewportY >= mapHeight) {
      return;
    }
    viewportW = Math.min(viewportW, mapWidth - viewportX);
    viewportH = Math.min(viewportH, mapHeight - viewportY);

    const x0 = Math.floor(tilemap.x || 0);
    const delta = positiveMod(renderColumn - x0, COLUMNS);
    if (delta >= viewportW) {
      return;
    }
    const sx = viewportX + delta;
    const tileCol = Math.floor(sx / tileWidth);
    // strip data columns are stored mirrored, same as sprites
    const sourceColumn = tileWidth - 1 - (sx % tileWidth);

    const frames = tilemap.frames;
    const paletteIndex = asset.palette || 0;
    const y0 = Math.floor(tilemap.y || 0);
    const desde = Math.max(y0, 0);
    const hasta = Math.min(y0 + viewportH, ROWS);
    for (let y = desde; y < hasta; y += 1) {
      const sy = viewportY + (y - y0);
      let frameId = frames[Math.floor(sy / tileHeight) * mapColumns + tileCol];
      if (frameId === EMPTY_TILE) {
        continue;
      }
      frameId %= totalFrames;
      const colorIndex = asset.data[
        sourceColumn * tileHeight + frameId * tileWidth * tileHeight + (sy % tileHeight)
      ];
      if (colorIndex === TRANSPARENT_INDEX) {
        continue;
      }
      const led = perspective === 1 ? DEEPSPACE[y] : PIXELS - 1 - y;
      if (led < PIXELS) {
        setLedColorFromPalette(pixels, palette, paletteIndex, colorIndex, column, led);
      }
    }
  }

  function computeLedFramePixels(frame, assetIndex, palette) {
    const pixels = new Uint8Array(COLUMNS * PIXELS * 4);
    for (let index = 3; index < pixels.length; index += 4) {
      pixels[index] = 255;
    }

    const columnOffset = positiveMod(Number(frame?.column_offset || 0), COLUMNS);
    drawStarfield(pixels, frame?.frame || 0, columnOffset);

    if (!(palette instanceof Uint8Array) || !Array.isArray(frame?.sprites)) {
      return pixels;
    }

    const sprites = [...frame.sprites].sort((left, right) => (right.slot || 0) - (left.slot || 0));
    // first slice: all tilemaps draw behind all sprites
    const tilemaps = Array.isArray(frame?.tilemaps)
      ? [...frame.tilemaps].sort((left, right) => (right.slot || 0) - (left.slot || 0))
      : [];

    for (let column = 0; column < COLUMNS; column += 1) {
      const renderColumn = positiveMod(column + columnOffset, COLUMNS);

      for (const tilemap of tilemaps) {
        drawTilemapColumn(pixels, tilemap, assetIndex, palette, column, renderColumn);
      }

      for (const sprite of sprites) {
        const asset = assetIndex.get(sprite.image_strip);
        if (!asset || !(asset.data instanceof Uint8Array) || asset.loadedBytes < asset.dataLength) {
          continue;
        }

        const width = asset.width === 255 ? 256 : asset.width;
        const height = asset.height || 0;
        const totalFrames = Math.max(asset.frames || 1, 1);
        const visibleColumn = getSourceColumn(sprite, width, renderColumn);
        if (visibleColumn === -1 || height <= 0) {
          continue;
        }

        const frameIndex = getFrameIndex(sprite.frame || 0, totalFrames);
        const base = visibleColumn * height + frameIndex * width * height;
        const paletteIndex = asset.palette || 0;

        if (sprite.perspective) {
          const spriteY = spritePixelY(sprite);
          const desde = Math.max(spriteY, 0);
          const hasta = Math.min(spriteY + height, ROWS);

          for (let y = desde; y < hasta; y += 1) {
            const sourceRow = getSourceRow(sprite, y - spriteY, height);
            const colorIndex = asset.data[base + sourceRow];
            if (colorIndex === TRANSPARENT_INDEX) {
              continue;
            }
            const led = sprite.perspective === 1 ? DEEPSPACE[y] : PIXELS - 1 - y;
            if (led < PIXELS) {
              setLedColorFromPalette(pixels, palette, paletteIndex, colorIndex, column, led);
            }
          }
          continue;
        }

        const spriteY = spritePixelY(sprite);
        const zleds = DEEPSPACE[clamp(255 - spriteY, 0, ROWS - 1)];
        for (let led = 0; led < zleds; led += 1) {
          let sourceRow = Math.floor((led * PIXELS) / zleds);
          if (sourceRow >= height) {
            break;
          }
          if (!sprite?.vs2?.flip_y) {
            sourceRow = height - 1 - sourceRow;
          }
          const colorIndex = asset.data[base + sourceRow];
          if (colorIndex === TRANSPARENT_INDEX) {
            continue;
          }
          setLedColorFromPalette(pixels, palette, paletteIndex, colorIndex, column, led);
        }
      }
    }

    return pixels;
  }

  function computeLedFramePixelsFromRgb(rgb) {
    // Convert a raw 256-column x PIXELS polar framebuffer (R,G,B per LED, as sent by
    // Super Ventilagon / Voom via the "frame_rgb" command) into the RGBA ledPixels
    // array the ring renderers consume. Layout in / out is column-major, led-minor.
    const pixels = new Uint8Array(COLUMNS * PIXELS * 4);
    const count = COLUMNS * PIXELS;
    const usable = rgb instanceof Uint8Array ? Math.min(count, (rgb.length / 3) | 0) : 0;
    for (let i = 0; i < count; i += 1) {
      const d = i * 4;
      pixels[d + 3] = 255;
      if (i < usable) {
        const s = i * 3;
        pixels[d] = rgb[s];
        pixels[d + 1] = rgb[s + 1];
        pixels[d + 2] = rgb[s + 2];
      }
    }
    return pixels;
  }

  function repeatLedColors(ledPixels, multiplier) {
    const repeated = new Uint8Array(ledPixels.length * multiplier);
    let dest = 0;
    for (let src = 0; src < ledPixels.length; src += 4) {
      for (let index = 0; index < multiplier; index += 1) {
        repeated[dest] = ledPixels[src];
        repeated[dest + 1] = ledPixels[src + 1];
        repeated[dest + 2] = ledPixels[src + 2];
        repeated[dest + 3] = ledPixels[src + 3];
        dest += 4;
      }
    }
    return repeated;
  }

  function createLedRingGeometry() {
    const ledStep = LED_SIZE / PIXELS;
    const theta = (Math.PI * 2) / COLUMNS;
    const positions = [];
    const texCoords = [];
    const centers = [];
    // Texel center for this LED in a PIXELS-wide x COLUMNS-tall color
    // texture (see LedRingWebGLRenderer): identical for all 6 vertices of a
    // LED's quad -- it's which LED this is, not a per-corner value. PIXELS
    // is the texture width (not COLUMNS) so the ledPixels array -- already
    // column-major/led-minor, i.e. row-major for a (COLUMNS rows x PIXELS
    // cols) image -- can be uploaded to the texture with no reshaping.
    const ledUVs = [];

    function arcChord(radius) {
      return 2 * radius * Math.sin(theta / 2);
    }

    for (let column = 0; column < COLUMNS; column += 1) {
      let x1 = 0;
      let x2 = 0;
      for (let led = 0; led < PIXELS; led += 1) {
        const y1 = ledStep * led - ledStep * 2.5;
        const y2 = y1 + ledStep * 5;
        const x3 = arcChord(y2) * 3.5;
        const x4 = -x3;
        const angle = -theta * column + Math.PI;
        const cos = Math.cos(angle);
        const sin = Math.sin(angle);

        function rotate(x, y) {
          return {
            x: x * cos - y * sin,
            y: x * sin + y * cos,
          };
        }

        const v1 = rotate(x1, y1);
        const v2 = rotate(x2, y1);
        const v3 = rotate(x4, y2);
        const v4 = rotate(x3, y2);
        const center = rotate(0, (y1 + y2) * 0.5);

        positions.push(
          v1.x, v1.y,
          v2.x, v2.y,
          v3.x, v3.y,
          v1.x, v1.y,
          v3.x, v3.y,
          v4.x, v4.y
        );

        texCoords.push(
          0, 0,
          1, 0,
          1, 1,
          0, 0,
          1, 1,
          0, 1
        );

        centers.push(center.x, center.y);

        const u = (led + 0.5) / PIXELS;
        const v = (column + 0.5) / COLUMNS;
        for (let corner = 0; corner < 6; corner += 1) {
          ledUVs.push(u, v);
        }

        x1 = x3;
        x2 = x4;
      }
    }

    return {
      positions: new Float32Array(positions),
      texCoords: new Float32Array(texCoords),
      centers: new Float32Array(centers),
      ledUVs: new Float32Array(ledUVs),
      ledCount: COLUMNS * PIXELS,
      vertexCount: COLUMNS * PIXELS * 6,
      worldRadius: LED_SIZE * 1.9,
    };
  }

  function getLedColor(pixels, column, led) {
    const offset = (column * PIXELS + led) * 4;
    return [
      pixels[offset],
      pixels[offset + 1],
      pixels[offset + 2],
      pixels[offset + 3],
    ];
  }

  return {
    COLUMNS,
    PIXELS,
    TRANSPARENT_INDEX,
    DEEPSPACE,
    getVisibleColumn,
    decodeVs2SceneBuffer,
    computeLedFramePixels,
    computeLedFramePixelsFromRgb,
    createLedRingGeometry,
    repeatLedColors,
    getLedColor,
  };
});
