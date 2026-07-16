// Build .vs2 game packages from the editor workspace and push them to the
// Ventilastation base for installation on the console.
//
// The editor must be served by the base itself (emulator/upgrade_server.py
// serves this web/ tree) so every request here is same-origin: uploads POST
// to /packages/<slug>.vs2, installs POST to /packages/<slug>/install, and
// progress is polled from /packages/<slug>/status. On any other origin
// (GitHub Pages, file://) probePackageServer() fails and the UI hides the
// push button.
//
// The zip writer is local and dependency-free: STORE for mp3s (already
// compressed), raw-deflate via the browser's native CompressionStream for
// everything else. Package layout matches tools/package_game.py:
//   meta.json, menu.png, code/**.py, roms/<slug>.rom, menu-icon.rom,
//   sounds/*.mp3

import { rebuildRomForImagesRoot } from "./workspace-rom-builder.js";

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(bytes) {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i += 1) {
    crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

async function deflateRaw(bytes) {
  const stream = new Blob([bytes]).stream()
    .pipeThrough(new CompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

function putUint16(view, offset, value) {
  view.setUint16(offset, value, true);
}

function putUint32(view, offset, value) {
  view.setUint32(offset, value, true);
}

// members: [{ name, data: Uint8Array, store?: boolean }] in archive order.
// Timestamps are pinned to the zip epoch so identical input produces an
// identical archive, mirroring tools/package_game.py.
export async function buildZip(members) {
  const encoder = new TextEncoder();
  const localParts = [];
  const centralParts = [];
  let offset = 0;

  for (const member of members) {
    const nameBytes = encoder.encode(member.name);
    const crc = crc32(member.data);
    const method = member.store ? 0 : 8;
    const payload = member.store ? member.data : await deflateRaw(member.data);

    const local = new Uint8Array(30 + nameBytes.length);
    const view = new DataView(local.buffer);
    putUint32(view, 0, 0x04034b50);
    putUint16(view, 4, 20);            // version needed
    putUint16(view, 6, 0);             // flags
    putUint16(view, 8, method);
    putUint16(view, 10, 0);            // dos time (fixed)
    putUint16(view, 12, 0x21);         // dos date: 1980-01-01
    putUint32(view, 14, crc);
    putUint32(view, 18, payload.length);
    putUint32(view, 22, member.data.length);
    putUint16(view, 26, nameBytes.length);
    putUint16(view, 28, 0);            // extra length
    local.set(nameBytes, 30);
    localParts.push(local, payload);

    const central = new Uint8Array(46 + nameBytes.length);
    const cview = new DataView(central.buffer);
    putUint32(cview, 0, 0x02014b50);
    putUint16(cview, 4, 20);           // version made by
    putUint16(cview, 6, 20);           // version needed
    putUint16(cview, 8, 0);            // flags
    putUint16(cview, 10, method);
    putUint16(cview, 12, 0);           // dos time
    putUint16(cview, 14, 0x21);        // dos date
    putUint32(cview, 16, crc);
    putUint32(cview, 20, payload.length);
    putUint32(cview, 24, member.data.length);
    putUint16(cview, 28, nameBytes.length);
    putUint32(cview, 38, 0o644 << 16); // external attributes
    putUint32(cview, 42, offset);      // local header offset
    central.set(nameBytes, 46);
    centralParts.push(central);

    offset += local.length + payload.length;
  }

  const centralSize = centralParts.reduce((sum, part) => sum + part.length, 0);
  const eocd = new Uint8Array(22);
  const eview = new DataView(eocd.buffer);
  putUint32(eview, 0, 0x06054b50);
  putUint16(eview, 8, members.length);
  putUint16(eview, 10, members.length);
  putUint32(eview, 12, centralSize);
  putUint32(eview, 16, offset);

  const blob = new Blob([...localParts, ...centralParts, eocd]);
  return new Uint8Array(await blob.arrayBuffer());
}

function base64ToUint8Array(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

async function readWorkspaceBytes(api, path) {
  const file = await api.readProjectFile(path, "base64");
  return base64ToUint8Array(file.content);
}

async function tryReadWorkspaceBytes(api, path) {
  try {
    return await readWorkspaceBytes(api, path);
  } catch (error) {
    return null;
  }
}

function decodePngBase64ToImage(base64) {
  // Reuses rom-builder-browser's PNG decoding through an offscreen canvas.
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      context.drawImage(image, 0, 0);
      const data = context.getImageData(0, 0, canvas.width, canvas.height);
      resolve({ width: data.width, height: data.height, data: data.data });
    };
    image.onerror = () => reject(new Error("cannot decode menu.png"));
    image.src = `data:image/png;base64,${base64}`;
  });
}

async function buildMenuIconRom(api, gameRoot, iconId, frames) {
  const builder = window.VentilastationRomBuilder;
  if (!builder?.buildRom) {
    throw new Error("Ventilastation ROM builder is unavailable");
  }
  const pngFile = await api.readProjectFile(`${gameRoot}/menu.png`, "base64");
  return builder.buildRom({
    palettegroups: [{
      name: "palette1",
      items: [{ kind: "strip", filename: "menu.png", id: iconId, frames }],
    }],
    loadImage: () => decodePngBase64ToImage(pngFile.content),
  });
}

async function listTreeSounds(gameRoot) {
  // Sounds usually live only in the base's checkout (the runtime bundle
  // excludes them); the base exposes the tree listing + files over HTTP.
  try {
    const listing = await fetch(`api/listdir?path=${encodeURIComponent(`${gameRoot}/sounds`)}`);
    if (!listing.ok) {
      return [];
    }
    const payload = await listing.json();
    return (payload.entries || [])
      .filter((entry) => !entry.dir && entry.name.endsWith(".mp3"))
      .map((entry) => entry.name);
  } catch (error) {
    return [];
  }
}

export async function probePackageServer() {
  try {
    const response = await fetch("packages", { cache: "no-store" });
    if (!response.ok) {
      return false;
    }
    const payload = await response.json();
    return Array.isArray(payload.packages);
  } catch (error) {
    return false;
  }
}

// gameKey is the editor's "<group>/<name>"; returns { slug, bytes }.
export async function buildPackageForGame(api, gameKey, onStatus = () => {}) {
  const [group, name] = String(gameKey).split("/");
  if (!group || !name) {
    throw new Error(`not a game: ${gameKey}`);
  }
  const slug = `${group}.${name}`;
  const gameRoot = `games/${group}/${name}`;
  const members = [];

  const metaBytes = await tryReadWorkspaceBytes(api, `${gameRoot}/meta.json`);
  let meta = {};
  if (metaBytes) {
    try {
      meta = JSON.parse(new TextDecoder().decode(metaBytes));
    } catch (error) {
      throw new Error(`${gameRoot}/meta.json is not valid JSON`);
    }
  }
  members.push({ name: "meta.json", data: metaBytes || new TextEncoder().encode("{}") });

  const menuPng = await tryReadWorkspaceBytes(api, `${gameRoot}/menu.png`);
  if (menuPng) {
    members.push({ name: "menu.png", data: menuPng });
  }

  const allPaths = (await api.listProjectFiles("."))
    .map((path) => String(path).replace(/^\/+/u, ""));
  const codePaths = allPaths
    .filter((path) => path.startsWith(`${gameRoot}/code/`) && path.endsWith(".py"))
    .sort();
  if (!codePaths.length) {
    throw new Error(`${gameRoot} has no code/*.py files`);
  }
  for (const path of codePaths) {
    members.push({
      name: path.slice(gameRoot.length + 1),
      data: await readWorkspaceBytes(api, path),
    });
  }

  if (allPaths.includes(`${gameRoot}/images/__images__.yaml`)) {
    onStatus(`Building ${slug}.rom`);
    const rebuild = await rebuildRomForImagesRoot(api, `${gameRoot}/images`);
    members.push({
      name: `roms/${slug}.rom`,
      data: await readWorkspaceBytes(api, rebuild.romPath),
    });
  }

  // A meta.json "menu_strip" override points at a strip that already exists
  // in the system menu rom; shipping an icon under that id would clobber it
  // at merge time (see tools/package_game.py).
  if (menuPng && !("menu_strip" in meta)) {
    onStatus("Building menu icon");
    const frames = Number(meta.menu_frames || 1);
    const icon = await buildMenuIconRom(
      api, gameRoot, `${group}/${name}/menu.png`, frames);
    members.push({ name: "menu-icon.rom", data: icon });
  }

  onStatus("Collecting sounds");
  const soundNames = new Map();
  for (const soundName of await listTreeSounds(gameRoot)) {
    soundNames.set(soundName, { tree: true });
  }
  for (const path of allPaths) {
    if (path.startsWith(`${gameRoot}/sounds/`) && path.endsWith(".mp3")) {
      soundNames.set(path.slice(`${gameRoot}/sounds/`.length), { tree: false });
    }
  }
  for (const [soundName, source] of [...soundNames.entries()].sort()) {
    let data = null;
    if (!source.tree) {
      data = await tryReadWorkspaceBytes(api, `${gameRoot}/sounds/${soundName}`);
    }
    if (!data) {
      const response = await fetch(`${gameRoot}/sounds/${soundName}`);
      if (!response.ok) {
        continue;
      }
      data = new Uint8Array(await response.arrayBuffer());
    }
    members.push({ name: `sounds/${soundName}`, data, store: true });
  }

  onStatus("Packing");
  return { slug, bytes: await buildZip(members) };
}

const INSTALL_POLL_INTERVAL_MS = 1000;
const INSTALL_TIMEOUT_MS = 180000;

export async function pushPackage(slug, bytes, onStatus = () => {}) {
  onStatus(`Uploading ${slug} (${(bytes.length / 1024).toFixed(0)} KiB)`);
  const upload = await fetch(`packages/${slug}.vs2`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: bytes,
  });
  if (!upload.ok) {
    let detail = `${upload.status}`;
    try {
      detail = (await upload.json()).error || detail;
    } catch (error) { /* non-JSON error body */ }
    throw new Error(`upload failed: ${detail}`);
  }

  onStatus("Asking the console to install");
  const install = await fetch(`packages/${slug}/install`, { method: "POST" });
  if (!install.ok) {
    let detail = `${install.status}`;
    try {
      detail = (await install.json()).error || detail;
    } catch (error) { /* non-JSON error body */ }
    throw new Error(`install trigger failed: ${detail}`);
  }

  const deadline = Date.now() + INSTALL_TIMEOUT_MS;
  let lastText = "";
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, INSTALL_POLL_INTERVAL_MS));
    let record;
    try {
      record = await (await fetch(`packages/${slug}/status`, { cache: "no-store" })).json();
    } catch (error) {
      continue;
    }
    if (record.state === "done") {
      onStatus(`Installed ${slug}`);
      return record;
    }
    if (record.state === "error") {
      throw new Error(`console reported: ${record.message || "install error"}`);
    }
    const text = record.state === "installing"
      ? `Installing on console: ${record.stage || ""} ${record.pct || ""}%`
      : `Console: ${record.state} (the board reboots to fetch the package)`;
    if (text !== lastText) {
      onStatus(text);
      lastText = text;
    }
  }
  throw new Error("timed out waiting for the console to finish installing");
}
