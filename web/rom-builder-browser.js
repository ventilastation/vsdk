(function (root, factory) {
  const core = root.VentilastationRomBuilder;
  const api = factory(core);
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.VentilastationBrowserRomBuilder = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (core) {
  if (!core) {
    throw new Error("Missing VentilastationRomBuilder");
  }

  function createCanvas(width, height) {
    if (typeof OffscreenCanvas !== "undefined") {
      return new OffscreenCanvas(width, height);
    }
    if (typeof document !== "undefined" && document.createElement) {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      return canvas;
    }
    throw new Error("This environment cannot create a canvas");
  }

  async function decodeImageFromBlob(blob) {
    if (typeof createImageBitmap === "function") {
      const bitmap = await createImageBitmap(blob);
      const canvas = createCanvas(bitmap.width, bitmap.height);
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
          const canvas = createCanvas(image.naturalWidth, image.naturalHeight);
          const context = canvas.getContext("2d");
          context.drawImage(image, 0, 0);
          const imageData = context.getImageData(0, 0, image.naturalWidth, image.naturalHeight);
          resolve({
            width: image.naturalWidth,
            height: image.naturalHeight,
            data: imageData.data,
          });
        } finally {
          URL.revokeObjectURL(url);
        }
      };
      image.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error(`Failed to decode image: ${blob.type || "unknown"}`));
      };
      image.src = url;
    });
  }

  async function loadRgbaImage(url, { fetchImpl = fetch } = {}) {
    const response = await fetchImpl(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch ${url}: ${response.status}`);
    }
    return decodeImageFromBlob(await response.blob());
  }

  async function buildRomFromFolder(folderUrl, options = {}) {
    const baseUrl = new URL(folderUrl, options.baseUrl || window.location.href);
    const stripedefsUrl = new URL(options.stripedefsFilename || "stripedefs.yaml", baseUrl);
    const fetchImpl = options.fetchImpl || fetch;
    const stripedefsResponse = await fetchImpl(stripedefsUrl.href);
    if (!stripedefsResponse.ok) {
      throw new Error(`Failed to fetch ${stripedefsUrl.href}: ${stripedefsResponse.status}`);
    }
    const stripedefsYaml = await stripedefsResponse.text();
    const palettegroups = core.parseStripedefsYaml(stripedefsYaml);

    return core.buildRom({
      palettegroups,
      loadImage: (filename) => loadRgbaImage(new URL(filename, baseUrl).href, { fetchImpl }),
    });
  }

  return {
    buildRomFromFolder,
    loadRgbaImage,
  };
});
