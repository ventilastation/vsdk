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
  const LED_SIZE = 100;
  const EMPTY_PIXELS = 16;
  const ROWS = 256 - EMPTY_PIXELS;
  const GAMMA = 0.28;
  const DEEPSPACE = new Uint8Array([
    ...new Array(EMPTY_PIXELS).fill(PIXELS),
    ...Array.from({ length: ROWS }, (_, index) => {
      const n = ROWS - 1 - index;
      return Math.round(PIXELS * Math.pow(n / ROWS, 1 / GAMMA));
    }),
  ]);

  function positiveMod(value, modulo) {
    return ((value % modulo) + modulo) % modulo;
  }

  function getVisibleColumn(spriteX, spriteWidth, renderColumn) {
    const spriteColumn = spriteWidth - 1 - positiveMod(renderColumn - spriteX, COLUMNS);
    if (spriteColumn >= 0 && spriteColumn < spriteWidth) {
      return spriteColumn;
    }
    return -1;
  }

  function getPaletteColor(palette, paletteIndex, colorIndex) {
    const base = (paletteIndex * 256 + colorIndex) * 4;
    return [
      palette[base + 3] || 0,
      palette[base + 2] || 0,
      palette[base + 1] || 0,
      255,
    ];
  }

  function setLedColor(buffer, column, led, rgba) {
    if (column < 0 || column >= COLUMNS || led < 0 || led >= PIXELS) {
      return;
    }
    const offset = (column * PIXELS + led) * 4;
    buffer[offset] = rgba[0];
    buffer[offset + 1] = rgba[1];
    buffer[offset + 2] = rgba[2];
    buffer[offset + 3] = rgba[3];
  }

  function getFrameIndex(frame, totalFrames) {
    if (!totalFrames || totalFrames <= 0) {
      return 0;
    }
    return positiveMod(frame, totalFrames);
  }

  function computeLedFramePixels(frame, assetIndex, palette) {
    const pixels = new Uint8Array(COLUMNS * PIXELS * 4);
    for (let index = 3; index < pixels.length; index += 4) {
      pixels[index] = 255;
    }

    if (!(palette instanceof Uint8Array) || !Array.isArray(frame?.sprites)) {
      return pixels;
    }

    const sprites = [...frame.sprites].sort((left, right) => (right.slot || 0) - (left.slot || 0));
    const columnOffset = positiveMod(Number(frame?.column_offset || 0), COLUMNS);

    for (let column = 0; column < COLUMNS; column += 1) {
      const renderColumn = positiveMod(column + columnOffset, COLUMNS);

      for (const sprite of sprites) {
        const asset = assetIndex.get(sprite.image_strip);
        if (!asset || !(asset.data instanceof Uint8Array) || asset.loadedBytes < asset.dataLength) {
          continue;
        }

        const width = asset.width === 255 ? 256 : asset.width;
        const height = asset.height || 0;
        const totalFrames = Math.max(asset.frames || 1, 1);
        const visibleColumn = getVisibleColumn(sprite.x || 0, width, renderColumn);
        if (visibleColumn === -1 || height <= 0) {
          continue;
        }

        const frameIndex = getFrameIndex(sprite.frame || 0, totalFrames);
        const base = visibleColumn * height + frameIndex * width * height;

        if (sprite.perspective) {
          const desde = Math.max(sprite.y || 0, 0);
          const hasta = Math.min((sprite.y || 0) + height, 255);
          let src = base + Math.max(-(sprite.y || 0), 0);

          for (let y = desde; y < hasta; y += 1, src += 1) {
            const colorIndex = asset.data[src];
            if (colorIndex === TRANSPARENT_INDEX) {
              continue;
            }
            const led = sprite.perspective === 1 ? DEEPSPACE[y] : PIXELS - 1 - y;
            if (led < PIXELS) {
              setLedColor(pixels, column, led, getPaletteColor(palette, asset.palette || 0, colorIndex));
            }
          }
          continue;
        }

        const zleds = DEEPSPACE[255 - (sprite.y || 0)];
        for (let led = 0; led < zleds; led += 1) {
          const src = Math.floor((led * PIXELS) / zleds);
          if (src >= height) {
            break;
          }
          const colorIndex = asset.data[base + height - 1 - src];
          if (colorIndex === TRANSPARENT_INDEX) {
            continue;
          }
          setLedColor(pixels, column, led, getPaletteColor(palette, asset.palette || 0, colorIndex));
        }
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
        x1 = x3;
        x2 = x4;
      }
    }

    return {
      positions: new Float32Array(positions),
      texCoords: new Float32Array(texCoords),
      centers: new Float32Array(centers),
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
    computeLedFramePixels,
    createLedRingGeometry,
    repeatLedColors,
    getLedColor,
  };
});
