#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { PNG } = require("pngjs");
const romBuilder = require("../web/rom-builder-core.js");

const ROOT_DIR = path.resolve(__dirname, "..");
const GAMES_ROOT = path.join(ROOT_DIR, "games");
const SYSTEM_ROOT = path.join(ROOT_DIR, "system");
const SEARCH_ROOTS = [GAMES_ROOT, SYSTEM_ROOT];
const ROMS_FOLDER = path.join(ROOT_DIR, "apps", "micropython", "roms");
const STRIPEDEF_FILENAME = "__images__.yaml";

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

// Expand `game_menu_strips: true`: one strip per games/<group>/<name>/menu.png,
// frame counts from each game's meta.json ("menu_frames"). Mirrors
// tools/generate_roms.py's _game_menu_strip_items().
function expandGameMenuStrips(folder) {
  const items = [];
  if (!fs.existsSync(GAMES_ROOT)) {
    return items;
  }
  for (const group of fs.readdirSync(GAMES_ROOT).sort()) {
    const groupDir = path.join(GAMES_ROOT, group);
    if (!fs.statSync(groupDir).isDirectory()) {
      continue;
    }
    for (const name of fs.readdirSync(groupDir).sort()) {
      const menuPng = path.join(groupDir, name, "menu.png");
      if (!fs.existsSync(menuPng)) {
        continue;
      }
      let frames = 1;
      const metaPath = path.join(groupDir, name, "meta.json");
      if (fs.existsSync(metaPath)) {
        const meta = JSON.parse(fs.readFileSync(metaPath, "utf8"));
        frames = Number(meta.menu_frames || 1);
      }
      items.push({
        filename: path.relative(folder, menuPng).split(path.sep).join("/"),
        id: `${group}/${name}/menu.png`,
        frames,
      });
    }
  }
  return items;
}

async function generateRomForFolder(folder) {
  const stripedefPath = path.join(folder, STRIPEDEF_FILENAME);
  const romName = romNameForFolder(folder);
  const romFilename = path.join(ROMS_FOLDER, `${romName}.rom`);
  const stripedefsYaml = fs.readFileSync(stripedefPath, "utf8");
  const palettegroups = romBuilder.parseStripedefsYaml(stripedefsYaml);

  const inputFilenames = [stripedefPath];
  for (const group of palettegroups) {
    for (const item of group.items) {
      if (item.kind === "game_menu_strips") {
        for (const expanded of expandGameMenuStrips(folder)) {
          inputFilenames.push(path.join(folder, expanded.filename));
        }
        continue;
      }
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
    expandGameMenuStrips: async () => expandGameMenuStrips(folder),
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

  for (const rootFolder of SEARCH_ROOTS) {
    if (!fs.existsSync(rootFolder)) {
      continue;
    }
    for (const { current, entries } of walkDirectories(rootFolder)) {
      if (entries.some((entry) => entry.isFile() && entry.name === STRIPEDEF_FILENAME)) {
        await generateRomForFolder(current);
      }
    }
  }
}

function romNameForFolder(folder) {
  const normalized = path.resolve(folder);

  if (normalized.startsWith(GAMES_ROOT + path.sep)) {
    const relative = path.relative(GAMES_ROOT, normalized).split(path.sep);
    if (relative[relative.length - 1] === "images") {
      return relative.slice(0, -1).join(".");
    }
  }

  if (normalized.startsWith(SYSTEM_ROOT + path.sep)) {
    const relative = path.relative(SYSTEM_ROOT, normalized).split(path.sep);
    if (relative[relative.length - 1] === "images" && relative.length >= 2) {
      return relative[relative.length - 2];
    }
  }

  return path.basename(normalized);
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exitCode = 1;
});
