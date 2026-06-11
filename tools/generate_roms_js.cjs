#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { PNG } = require("pngjs");
const romBuilder = require("../web/rom-builder-core.js");

const ROOT_FOLDER = path.resolve(__dirname, "../apps/images");
const ROMS_FOLDER = path.resolve(__dirname, "../apps/micropython/roms");
const STRIPEDEF_FILENAME = "stripedefs.yaml";

function walkDirectories(rootFolder) {
  const stack = [rootFolder];
  const results = [];

  while (stack.length) {
    const current = stack.pop();
    const entries = fs.readdirSync(current, { withFileTypes: true });
    results.push({ current, entries });
    for (const entry of entries) {
      if (entry.isDirectory()) {
        stack.push(path.join(current, entry.name));
      }
    }
  }

  return results;
}

function trimAfterPngIend(buffer) {
  const signatureLength = 8;
  let offset = signatureLength;

  while (offset + 12 <= buffer.length) {
    const chunkLength = buffer.readUInt32BE(offset);
    const chunkType = buffer.toString("ascii", offset + 4, offset + 8);
    const chunkEnd = offset + 12 + chunkLength;
    if (chunkEnd > buffer.length) {
      break;
    }
    offset = chunkEnd;
    if (chunkType === "IEND") {
      return buffer.subarray(0, chunkEnd);
    }
  }

  return buffer;
}

function decodePng(filename) {
  const source = fs.readFileSync(filename);
  const png = PNG.sync.read(trimAfterPngIend(source));
  return {
    width: png.width,
    height: png.height,
    data: new Uint8ClampedArray(png.data),
  };
}

async function generateRomForFolder(folder) {
  const stripedefPath = path.join(folder, STRIPEDEF_FILENAME);
  const romName = path.basename(folder);
  const romFilename = path.join(ROMS_FOLDER, `${romName}.rom`);
  const stripedefsYaml = fs.readFileSync(stripedefPath, "utf8");
  const palettegroups = romBuilder.parseStripedefsYaml(stripedefsYaml);

  const inputFilenames = [stripedefPath];
  for (const group of palettegroups) {
    for (const item of group.items) {
      inputFilenames.push(path.join(folder, item.filename));
    }
  }

  if (fs.existsSync(romFilename)) {
    const romTimestamp = fs.statSync(romFilename).mtimeMs;
    const needsRebuild = inputFilenames.some((filename) => fs.statSync(filename).mtimeMs > romTimestamp);
    if (!needsRebuild) {
      return false;
    }
  }

  console.error(`Generating ${romName}`);
  const rom = await romBuilder.buildRom({
    palettegroups,
    loadImage: async (filename) => decodePng(path.join(folder, filename)),
  });
  fs.mkdirSync(ROMS_FOLDER, { recursive: true });
  fs.writeFileSync(romFilename, Buffer.from(rom));
  return true;
}

async function main() {
  const targetFolder = process.argv[2]
    ? path.resolve(process.cwd(), process.argv[2])
    : null;

  if (targetFolder) {
    await generateRomForFolder(targetFolder);
    return;
  }

  for (const { current, entries } of walkDirectories(ROOT_FOLDER)) {
    if (entries.some((entry) => entry.isFile() && entry.name === STRIPEDEF_FILENAME)) {
      await generateRomForFolder(current);
    }
  }
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exitCode = 1;
});
