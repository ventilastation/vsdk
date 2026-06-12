function normalizeWorkspacePath(path) {
  return String(path || "")
    .replace(/\\/g, "/")
    .replace(/^\/+/u, "")
    .replace(/\/+/g, "/")
    .replace(/^\.\//u, "")
    .replace(/\/$/u, "");
}

function resolveWorkspaceRelativePath(basePath, relativePath) {
  const baseParts = normalizeWorkspacePath(basePath).split("/").filter(Boolean);
  const relativeParts = normalizeWorkspacePath(relativePath).split("/").filter(Boolean);
  const combined = [...baseParts];
  for (const part of relativeParts) {
    if (part === ".") {
      continue;
    }
    if (part === "..") {
      combined.pop();
      continue;
    }
    combined.push(part);
  }
  return combined.join("/");
}

const RUNTIME_ROMS_PREFIX = "__runtime_roms__";

function dirname(path) {
  const normalized = normalizeWorkspacePath(path);
  const lastSlashIndex = normalized.lastIndexOf("/");
  if (lastSlashIndex < 0) {
    return "";
  }
  return normalized.slice(0, lastSlashIndex);
}

function base64ToUint8Array(base64) {
  const binary = atob(String(base64 || ""));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function uint8ArrayToBase64(bytes) {
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    const chunk = bytes.subarray(offset, offset + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

async function decodePngBase64(base64) {
  const bytes = base64ToUint8Array(base64);
  const blob = new Blob([bytes], { type: "image/png" });

  if (typeof createImageBitmap === "function") {
    const bitmap = await createImageBitmap(blob);
    const canvas = typeof OffscreenCanvas !== "undefined"
      ? new OffscreenCanvas(bitmap.width, bitmap.height)
      : Object.assign(document.createElement("canvas"), {
        width: bitmap.width,
        height: bitmap.height,
      });
    const context = canvas.getContext("2d");
    context.drawImage(bitmap, 0, 0);
    const imageData = context.getImageData(0, 0, bitmap.width, bitmap.height);
    return {
      width: bitmap.width,
      height: bitmap.height,
      data: imageData.data,
    };
  }

  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob);
    const image = new Image();
    image.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = image.naturalWidth;
        canvas.height = image.naturalHeight;
        const context = canvas.getContext("2d");
        context.drawImage(image, 0, 0);
        const imageData = context.getImageData(0, 0, image.naturalWidth, image.naturalHeight);
        resolve({
          width: image.naturalWidth,
          height: image.naturalHeight,
          data: imageData.data,
        });
      } catch (error) {
        reject(error);
      } finally {
        URL.revokeObjectURL(url);
      }
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Failed to decode PNG image"));
    };
    image.src = url;
  });
}

export function isSpriteAssetPath(path) {
  const normalized = normalizeWorkspacePath(path);
  return (
    (normalized.endsWith(".png") && normalized.includes("/images/")) ||
    isGameMenuAssetPath(normalized)
  );
}

export function isGameMenuAssetPath(path) {
  const normalized = normalizeWorkspacePath(path);
  return /^(?:games\/)?[^/]+\/[^/]+\/menu\.png$/u.test(normalized);
}

export function isSerializedSpritePath(path) {
  return normalizeWorkspacePath(path).endsWith(".png.piskel");
}

export function findImagesRoot(path) {
  const normalized = normalizeWorkspacePath(path);
  if (normalized.endsWith("/images")) {
    return normalized;
  }
  const marker = "/images/";
  const markerIndex = normalized.lastIndexOf(marker);
  if (markerIndex < 0) {
    return null;
  }
  return normalized.slice(0, markerIndex + marker.length - 1);
}

export function getSerializedSpritePath(path) {
  return `${normalizeWorkspacePath(path)}.piskel`;
}

export function getRelativeImagePath(imagesRoot, path) {
  const normalizedRoot = normalizeWorkspacePath(imagesRoot);
  const normalizedPath = normalizeWorkspacePath(path);
  if (normalizedPath === normalizedRoot) {
    return "";
  }
  if (!normalizedPath.startsWith(`${normalizedRoot}/`)) {
    return normalizedPath;
  }
  return normalizedPath.slice(normalizedRoot.length + 1);
}

export function deriveRomOutputPath(imagesRoot) {
  const parts = normalizeWorkspacePath(imagesRoot).split("/").filter(Boolean);
  if (parts.length >= 4 && parts[0] === "games" && parts[3] === "images") {
    return `${RUNTIME_ROMS_PREFIX}/${parts[1]}.${parts[2]}.rom`;
  }
  if (parts.length >= 4 && parts[0] === "system" && parts[1] === "shared" && parts[3] === "images") {
    return `${RUNTIME_ROMS_PREFIX}/${parts[2]}.rom`;
  }
  if (parts.length >= 3 && parts[0] === "system" && parts[2] === "images") {
    return `${RUNTIME_ROMS_PREFIX}/${parts[1]}.rom`;
  }
  if (parts.length >= 3 && parts[2] === "images") {
    return `${RUNTIME_ROMS_PREFIX}/${parts[0]}.${parts[1]}.rom`;
  }
  if (parts.length >= 2 && parts[1] === "images") {
    return `${RUNTIME_ROMS_PREFIX}/${parts[0]}.rom`;
  }
  throw new Error(`Unable to infer ROM output path for ${imagesRoot}`);
}

export async function readStripedefManifest(api, imagesRoot) {
  const manifestPath = `${normalizeWorkspacePath(imagesRoot)}/__images__.yaml`;
  const file = await api.readProjectFile(manifestPath, "utf8");
  const builder = window.VentilastationRomBuilder;
  if (!builder?.parseStripedefsYaml) {
    throw new Error("Ventilastation ROM builder is unavailable");
  }
  return {
    manifestPath,
    sourceText: file.content,
    palettegroups: builder.parseStripedefsYaml(file.content),
  };
}

export async function findStripedefItemForPath(api, path) {
  const imagesRoot = findImagesRoot(path);
  if (!imagesRoot) {
    return null;
  }
  const manifest = await readStripedefManifest(api, imagesRoot);
  const relativePath = getRelativeImagePath(imagesRoot, path);
  for (const group of manifest.palettegroups) {
    for (const item of group.items) {
      if (normalizeWorkspacePath(item.filename) === relativePath) {
        return {
          ...item,
          imagesRoot,
          manifestPath: manifest.manifestPath,
        };
      }
    }
  }
  return {
    kind: "strip",
    frames: 1,
    filename: relativePath,
    imagesRoot,
    manifestPath: manifest.manifestPath,
  };
}

export async function rebuildRomForImagesRoot(api, imagesRoot) {
  const normalizedRoot = normalizeWorkspacePath(imagesRoot);
  const builder = window.VentilastationRomBuilder;
  if (!builder?.buildRom) {
    throw new Error("Ventilastation ROM builder is unavailable");
  }
  const manifest = await readStripedefManifest(api, normalizedRoot);
  const rom = await builder.buildRom({
    palettegroups: manifest.palettegroups,
    loadImage: async (filename) => {
      const imagePath = resolveWorkspaceRelativePath(normalizedRoot, filename);
      const file = await api.readProjectFile(imagePath, "base64");
      return decodePngBase64(file.content);
    },
  });
  const romPath = deriveRomOutputPath(normalizedRoot);
  await api.writeProjectFile(romPath, uint8ArrayToBase64(rom), "base64");
  return {
    imagesRoot: normalizedRoot,
    manifestPath: manifest.manifestPath,
    romPath,
    byteLength: rom.length,
  };
}

export async function maybeRebuildRomForPath(api, path) {
  const normalizedPath = normalizeWorkspacePath(path);
  if (isGameMenuAssetPath(normalizedPath)) {
    return rebuildRomForImagesRoot(api, "system/menu/images");
  }
  if (isSpriteAssetPath(normalizedPath)) {
    return rebuildRomForImagesRoot(api, findImagesRoot(normalizedPath));
  }
  if (normalizedPath.endsWith("/images/__images__.yaml")) {
    return rebuildRomForImagesRoot(api, dirname(normalizedPath));
  }
  return null;
}
