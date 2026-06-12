(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.VentilastationRomBuilder = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const TRANSPARENT = [255, 0, 255];
  const DEFAULT_FULLSCREEN_RADIUS = 54;
  const MAX_COLORS = 255;
  const TRANSPARENT_INDEX = 255;
  const ANGLES = 256;

  function countIndentation(line) {
    let count = 0;
    while (count < line.length && line[count] === " ") {
      count += 1;
    }
    return count;
  }

  function stripQuotes(value) {
    if (value.length >= 2) {
      const first = value[0];
      const last = value[value.length - 1];
      if ((first === "\"" && last === "\"") || (first === "'" && last === "'")) {
        return value.slice(1, -1);
      }
    }
    return value;
  }

  function parsePositiveInteger(rawValue, context) {
    if (!/^\d+$/.test(rawValue)) {
      throw new Error(`${context} must be a positive integer`);
    }
    const value = Number(rawValue);
    if (!Number.isInteger(value) || value < 1) {
      throw new Error(`${context} must be a positive integer`);
    }
    return value;
  }

  function parseStripedefsYaml(sourceText) {
    const lines = String(sourceText).replace(/\r\n?/g, "\n").split("\n");
    const palettegroups = [];
    let foundRoot = false;
    let currentGroup = null;
    let currentItem = null;

    for (let lineNumber = 0; lineNumber < lines.length; lineNumber += 1) {
      const originalLine = lines[lineNumber];
      const trimmed = originalLine.trim();
      if (!trimmed || trimmed.startsWith("#")) {
        continue;
      }

      const indent = countIndentation(originalLine);
      const content = originalLine.slice(indent);
      const at = `line ${lineNumber + 1}`;

      if (!foundRoot) {
        if (indent !== 0 || content !== "palettegroups:") {
          throw new Error(`${at}: expected top-level 'palettegroups:'`);
        }
        foundRoot = true;
        continue;
      }

      if (indent === 2) {
        const match = content.match(/^([A-Za-z0-9_-]+):\s*$/);
        if (!match) {
          throw new Error(`${at}: expected palette group name like 'palette1:'`);
        }
        currentGroup = {
          name: match[1],
          items: [],
        };
        palettegroups.push(currentGroup);
        currentItem = null;
        continue;
      }

      if (indent === 4) {
        if (!currentGroup) {
          throw new Error(`${at}: item declared before any palette group`);
        }
        const match = content.match(/^- (strip|fullscreen):\s*(.+?)\s*$/);
        if (!match) {
          throw new Error(`${at}: expected '- strip: file.png' or '- fullscreen: file.png'`);
        }
        currentItem = {
          kind: match[1],
          filename: stripQuotes(match[2]),
        };
        if (!currentItem.filename) {
          throw new Error(`${at}: filename cannot be empty`);
        }
        currentGroup.items.push(currentItem);
        continue;
      }

      if (indent === 6) {
        if (!currentItem) {
          throw new Error(`${at}: property declared before any item`);
        }
        const match = content.match(/^(frames|radius|id):\s*(.+?)\s*$/);
        if (!match) {
          throw new Error(`${at}: expected 'frames: N', 'radius: N', or 'id: name'`);
        }
        const key = match[1];
        if (key === "id") {
          currentItem.id = stripQuotes(match[2]);
        } else {
          const value = parsePositiveInteger(match[2], `${at} ${key}`);
          currentItem[key] = value;
        }
        continue;
      }

      throw new Error(`${at}: unsupported indentation level`);
    }

    if (!foundRoot) {
      throw new Error("missing top-level 'palettegroups:'");
    }

    return palettegroups.map((group) => ({
      name: group.name,
      items: group.items.map((item) => normalizeStripedefItem(item, group.name)),
    }));
  }

  function normalizeStripedefItem(item, groupName) {
    if (!item || typeof item !== "object") {
      throw new Error(`palette group ${groupName} contains an invalid item`);
    }

    if (item.kind !== "strip" && item.kind !== "fullscreen") {
      throw new Error(`palette group ${groupName} contains an unknown item kind`);
    }

    const normalized = {
      kind: item.kind,
      filename: String(item.filename || ""),
      id: item.id ? String(item.id) : "",
      frames: item.kind === "strip" ? Number(item.frames || 1) : 1,
      radius: item.kind === "fullscreen"
        ? Number(item.radius || DEFAULT_FULLSCREEN_RADIUS)
        : undefined,
    };

    if (!normalized.filename) {
      throw new Error(`palette group ${groupName} contains an item with an empty filename`);
    }

    if (!Number.isInteger(normalized.frames) || normalized.frames < 1) {
      throw new Error(`item ${normalized.filename} has an invalid frame count`);
    }

    if (
      normalized.kind === "fullscreen" &&
      (!Number.isInteger(normalized.radius) || normalized.radius < 1)
    ) {
      throw new Error(`item ${normalized.filename} has an invalid radius`);
    }

    return normalized;
  }

  function cloneRgbaImage(image) {
    return {
      width: image.width,
      height: image.height,
      data: new Uint8ClampedArray(image.data),
    };
  }

  function createOpaqueBlackImage(width, height) {
    const data = new Uint8ClampedArray(width * height * 4);
    for (let index = 3; index < data.length; index += 4) {
      data[index] = 255;
    }
    return { width, height, data };
  }

  function compositeOverOpaqueBlack(destination, source, offsetY) {
    for (let y = 0; y < source.height; y += 1) {
      for (let x = 0; x < source.width; x += 1) {
        const srcOffset = (y * source.width + x) * 4;
        const dstOffset = ((y + offsetY) * destination.width + x) * 4;
        const alpha = source.data[srcOffset + 3] / 255;
        const inverseAlpha = 1 - alpha;
        destination.data[dstOffset] = Math.round(source.data[srcOffset] * alpha + destination.data[dstOffset] * inverseAlpha);
        destination.data[dstOffset + 1] = Math.round(source.data[srcOffset + 1] * alpha + destination.data[dstOffset + 1] * inverseAlpha);
        destination.data[dstOffset + 2] = Math.round(source.data[srcOffset + 2] * alpha + destination.data[dstOffset + 2] * inverseAlpha);
        destination.data[dstOffset + 3] = 255;
      }
    }
  }

  function rgbaKey(red, green, blue) {
    return (red << 16) | (green << 8) | blue;
  }

  function analyzeBox(colors) {
    let redMin = 255;
    let redMax = 0;
    let greenMin = 255;
    let greenMax = 0;
    let blueMin = 255;
    let blueMax = 0;
    let population = 0;

    for (const color of colors) {
      if (color.r < redMin) redMin = color.r;
      if (color.r > redMax) redMax = color.r;
      if (color.g < greenMin) greenMin = color.g;
      if (color.g > greenMax) greenMax = color.g;
      if (color.b < blueMin) blueMin = color.b;
      if (color.b > blueMax) blueMax = color.b;
      population += color.count;
    }

    return {
      colors,
      population,
      redRange: redMax - redMin,
      greenRange: greenMax - greenMin,
      blueRange: blueMax - blueMin,
    };
  }

  function chooseSplitChannel(box) {
    if (box.greenRange >= box.redRange && box.greenRange >= box.blueRange) {
      return "g";
    }
    if (box.blueRange >= box.redRange && box.blueRange >= box.greenRange) {
      return "b";
    }
    return "r";
  }

  function splitBox(box) {
    if (!box.colors.length || box.colors.length === 1) {
      return null;
    }

    const channel = chooseSplitChannel(box);
    const colors = box.colors.slice().sort((left, right) => left[channel] - right[channel]);
    const total = box.population;
    let running = 0;
    let splitIndex = -1;

    for (let index = 0; index < colors.length - 1; index += 1) {
      running += colors[index].count;
      if (running >= total / 2) {
        splitIndex = index;
        break;
      }
    }

    if (splitIndex < 0) {
      splitIndex = Math.floor(colors.length / 2) - 1;
    }

    const leftColors = colors.slice(0, splitIndex + 1);
    const rightColors = colors.slice(splitIndex + 1);
    if (!leftColors.length || !rightColors.length) {
      return null;
    }

    return [analyzeBox(leftColors), analyzeBox(rightColors)];
  }

  function averageBoxColor(box) {
    let red = 0;
    let green = 0;
    let blue = 0;
    let total = 0;

    for (const color of box.colors) {
      red += color.r * color.count;
      green += color.g * color.count;
      blue += color.b * color.count;
      total += color.count;
    }

    if (!total) {
      return [0, 0, 0];
    }

    return [
      Math.round(red / total),
      Math.round(green / total),
      Math.round(blue / total),
    ];
  }

  function quantizeRgbaImage(image, maxColors) {
    const histogram = new Map();
    const pixelCount = image.width * image.height;

    for (let pixel = 0; pixel < pixelCount; pixel += 1) {
      const offset = pixel * 4;
      const key = rgbaKey(image.data[offset], image.data[offset + 1], image.data[offset + 2]);
      histogram.set(key, (histogram.get(key) || 0) + 1);
    }

    const colors = [];
    for (const [key, count] of histogram.entries()) {
      colors.push({
        key,
        r: (key >> 16) & 0xff,
        g: (key >> 8) & 0xff,
        b: key & 0xff,
        count,
      });
    }

    if (!colors.length) {
      return {
        palette: [[0, 0, 0]],
        indices: new Uint8Array(pixelCount),
      };
    }

    let boxes = [analyzeBox(colors)];
    while (boxes.length < maxColors) {
      let boxIndex = -1;
      let bestScore = -1;

      for (let index = 0; index < boxes.length; index += 1) {
        const box = boxes[index];
        if (box.colors.length < 2) {
          continue;
        }
        const score = Math.max(box.redRange, box.greenRange, box.blueRange) * box.population;
        if (score > bestScore) {
          bestScore = score;
          boxIndex = index;
        }
      }

      if (boxIndex === -1) {
        break;
      }

      const split = splitBox(boxes[boxIndex]);
      if (!split) {
        break;
      }

      boxes.splice(boxIndex, 1, split[0], split[1]);
    }

    const palette = boxes.map(averageBoxColor);
    const colorToIndex = new Map();
    boxes.forEach((box, paletteIndex) => {
      for (const color of box.colors) {
        colorToIndex.set(color.key, paletteIndex);
      }
    });

    const indices = new Uint8Array(pixelCount);
    for (let pixel = 0; pixel < pixelCount; pixel += 1) {
      const offset = pixel * 4;
      const key = rgbaKey(image.data[offset], image.data[offset + 1], image.data[offset + 2]);
      indices[pixel] = colorToIndex.get(key) || 0;
    }

    return { palette, indices };
  }

  function encodePaletteBytes(palette) {
    const bytes = new Uint8Array(256 * 4);
    let offset = 0;

    for (let index = 0; index < palette.length; index += 1) {
      const color = palette[index];
      bytes[offset] = 255;
      bytes[offset + 1] = color[2];
      bytes[offset + 2] = color[1];
      bytes[offset + 3] = color[0];
      offset += 4;
    }

    while (offset < (255 * 4)) {
      bytes[offset] = 255;
      bytes[offset + 1] = 0;
      bytes[offset + 2] = 0;
      bytes[offset + 3] = 0;
      offset += 4;
    }

    bytes[offset] = 255;
    bytes[offset + 1] = TRANSPARENT[2];
    bytes[offset + 2] = TRANSPARENT[1];
    bytes[offset + 3] = TRANSPARENT[0];
    return bytes;
  }

  function rotate270Paletted(indices, width, height) {
    const rotated = new Uint8Array(indices.length);
    let dest = 0;
    for (let y = 0; y < width; y += 1) {
      for (let x = 0; x < height; x += 1) {
        const srcX = y;
        const srcY = height - 1 - x;
        rotated[dest] = indices[srcY * width + srcX];
        dest += 1;
      }
    }
    return rotated;
  }

  function encodePascalString(value) {
    const bytes = [];
    for (let index = 0; index < value.length; index += 1) {
      const code = value.charCodeAt(index);
      if (code <= 0x7f) {
        bytes.push(code);
      } else if (code <= 0x7ff) {
        bytes.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f));
      } else {
        bytes.push(
          0xe0 | (code >> 12),
          0x80 | ((code >> 6) & 0x3f),
          0x80 | (code & 0x3f)
        );
      }
    }
    if (bytes.length > 255) {
      throw new Error(`filename is too long for ROM encoding: ${value}`);
    }
    return Uint8Array.from([bytes.length, ...bytes]);
  }

  function concatArrays(parts) {
    const total = parts.reduce((sum, part) => sum + part.length, 0);
    const result = new Uint8Array(total);
    let offset = 0;
    for (const part of parts) {
      result.set(part, offset);
      offset += part.length;
    }
    return result;
  }

  function writeUint16LE(target, offset, value) {
    target[offset] = value & 0xff;
    target[offset + 1] = (value >> 8) & 0xff;
  }

  function writeUint32LE(target, offset, value) {
    target[offset] = value & 0xff;
    target[offset + 1] = (value >> 8) & 0xff;
    target[offset + 2] = (value >> 16) & 0xff;
    target[offset + 3] = (value >> 24) & 0xff;
  }

  function extractPalettedCrop(indices, workspaceWidth, cropX, cropY, width, height) {
    const result = new Uint8Array(width * height);
    let dest = 0;
    for (let y = 0; y < height; y += 1) {
      const srcBase = (cropY + y) * workspaceWidth + cropX;
      for (let x = 0; x < width; x += 1) {
        result[dest] = indices[srcBase + x];
        dest += 1;
      }
    }
    return result;
  }

  function applyTransparencyMask(indices, image) {
    for (let pixel = 0; pixel < image.width * image.height; pixel += 1) {
      if (image.data[pixel * 4 + 3] < 128) {
        indices[pixel] = TRANSPARENT_INDEX;
      }
    }
    return indices;
  }

  function reprojectRgbaImage(image, nLed, nAng) {
    const srcHeight = image.height;
    const srcWidth = image.width;
    const centerX = Math.trunc((srcHeight - 1) / 2);
    const centerY = Math.trunc((srcWidth - 1) / 2);
    const radius = Math.min(centerX, centerY);
    const result = new Uint8ClampedArray(nLed * nAng * 4);

    for (let angle = 0; angle < nAng; angle += 1) {
      for (let led = 0; led < nLed; led += 1) {
        const sampleRow = centerX + Math.trunc(
          radius * (led + 1) / nLed * Math.cos(angle * 2 * Math.PI / nAng)
        );
        const sampleColumn = centerY + Math.trunc(
          radius * (led + 1) / nLed * Math.sin(angle * 2 * Math.PI / nAng)
        );
        const srcOffset = (sampleRow * srcWidth + sampleColumn) * 4;
        const dstOffset = (led * nAng + angle) * 4;
        result[dstOffset] = image.data[srcOffset];
        result[dstOffset + 1] = image.data[srcOffset + 1];
        result[dstOffset + 2] = image.data[srcOffset + 2];
        result[dstOffset + 3] = image.data[srcOffset + 3];
      }
    }

    return {
      width: nAng,
      height: nLed,
      data: result,
    };
  }

  async function buildRom(options) {
    const palettegroups = Array.isArray(options?.palettegroups)
      ? options.palettegroups
      : parseStripedefsYaml(options?.stripedefsYaml || "");
    const loadImage = options?.loadImage;

    if (typeof loadImage !== "function") {
      throw new Error("buildRom requires an async loadImage(filename, item) function");
    }

    const romStrips = [];
    const palettes = [];

    for (let paletteIndex = 0; paletteIndex < palettegroups.length; paletteIndex += 1) {
      const group = palettegroups[paletteIndex];
      const loadedImages = [];

      for (const item of group.items) {
        const sourceImage = await loadImage(item.filename, item);
        if (
          !sourceImage ||
          !Number.isInteger(sourceImage.width) ||
          !Number.isInteger(sourceImage.height) ||
          !(sourceImage.data instanceof Uint8ClampedArray || sourceImage.data instanceof Uint8Array)
        ) {
          throw new Error(`loadImage('${item.filename}') did not return a valid RGBA image`);
        }

        let image = {
          width: sourceImage.width,
          height: sourceImage.height,
          data: new Uint8ClampedArray(sourceImage.data),
        };

        if (item.kind === "fullscreen") {
          image = reprojectRgbaImage(image, item.radius, ANGLES);
        }

        loadedImages.push({ item, image });
      }

      const workspaceWidth = loadedImages.reduce((max, entry) => Math.max(max, entry.image.width), 0);
      const workspaceHeight = loadedImages.reduce((sum, entry) => sum + entry.image.height, 0);
      const workspace = createOpaqueBlackImage(workspaceWidth, workspaceHeight);

      let cursorY = 0;
      for (const entry of loadedImages) {
        entry.offsetY = cursorY;
        compositeOverOpaqueBlack(workspace, entry.image, cursorY);
        cursorY += entry.image.height;
      }

      const quantized = quantizeRgbaImage(workspace, MAX_COLORS);
      palettes.push(encodePaletteBytes(quantized.palette));

      for (const entry of loadedImages) {
        const frames = Math.min(entry.item.frames, 255);
        const stripWidth = Math.trunc(entry.image.width / frames);
        const encodedWidth = Math.min(stripWidth, 255);
        const encodedHeight = Math.min(entry.image.height, 255);
        const crop = extractPalettedCrop(
          quantized.indices,
          workspaceWidth,
          0,
          entry.offsetY,
          entry.image.width,
          entry.image.height
        );
        applyTransparencyMask(crop, entry.image);
        const rotated = rotate270Paletted(crop, entry.image.width, entry.image.height);
        const attrs = Uint8Array.from([
          encodedWidth,
          encodedHeight,
          frames,
          paletteIndex,
        ]);
        const filename = entry.item.id || entry.item.filename.split("/").pop();
        romStrips.push(concatArrays([
          encodePascalString(filename),
          attrs,
          rotated,
        ]));
      }
    }

    const headerSize = 4 + romStrips.length * 4 + palettes.length * 4;
    let offset = headerSize;
    const outputSize = headerSize
      + romStrips.reduce((sum, part) => sum + part.length, 0)
      + palettes.reduce((sum, part) => sum + part.length, 0);
    const rom = new Uint8Array(outputSize);

    writeUint16LE(rom, 0, romStrips.length);
    writeUint16LE(rom, 2, palettes.length);

    let tableOffset = 4;
    for (const strip of romStrips) {
      writeUint32LE(rom, tableOffset, offset);
      tableOffset += 4;
      offset += strip.length;
    }
    for (const palette of palettes) {
      writeUint32LE(rom, tableOffset, offset);
      tableOffset += 4;
      offset += palette.length;
    }

    let writeOffset = headerSize;
    for (const strip of romStrips) {
      rom.set(strip, writeOffset);
      writeOffset += strip.length;
    }
    for (const palette of palettes) {
      rom.set(palette, writeOffset);
      writeOffset += palette.length;
    }

    return rom;
  }

  return {
    ANGLES,
    DEFAULT_FULLSCREEN_RADIUS,
    MAX_COLORS,
    TRANSPARENT_INDEX,
    buildRom,
    cloneRgbaImage,
    parseStripedefsYaml,
    quantizeRgbaImage,
    reprojectRgbaImage,
  };
});
