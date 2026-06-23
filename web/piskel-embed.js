function stripExtension(filename) {
  return String(filename || "").replace(/\.[^.]+$/u, "");
}

function parseDataUrl(dataUrl) {
  const match = /^data:([^;,]+)?(?:;base64)?,(.*)$/u.exec(String(dataUrl || ""));
  if (!match) {
    throw new Error("Invalid data URL");
  }
  return {
    mimeType: match[1] || "application/octet-stream",
    base64: match[2],
  };
}

function normalizeSerializedSpriteDocument(serializedSprite) {
  if (serializedSprite && typeof serializedSprite === "object") {
    return serializedSprite;
  }
  if (typeof serializedSprite !== "string") {
    throw new Error("Invalid serialized Piskel document");
  }
  const parsed = JSON.parse(serializedSprite);
  if (typeof parsed === "string") {
    return JSON.parse(parsed);
  }
  return parsed;
}

export class EmbeddedPiskelEditor {
  constructor(container, { onDirtyChange } = {}) {
    this.container = container;
    this.onDirtyChange = typeof onDirtyChange === "function" ? onDirtyChange : null;
    this.frame = null;
    this.readyPromise = null;
    this.suspendDirtyTracking = false;
    this.handleDirtySignal = this.handleDirtySignal.bind(this);
  }

  ensureFrame() {
    if (this.frame) {
      return this.frame;
    }
    const frame = document.createElement("iframe");
    frame.className = "piskel-frame";
    frame.title = "Piskel sprite editor";
    frame.loading = "eager";
    frame.src = "./vendor/piskel/index.html";
    this.container.appendChild(frame);
    this.frame = frame;
    return frame;
  }

  async waitUntilReady() {
    if (this.readyPromise) {
      return this.readyPromise;
    }
    const frame = this.ensureFrame();
    this.readyPromise = new Promise((resolve, reject) => {
      let attempts = 0;
      const maxAttempts = 300;

      const onLoad = () => {
        const poll = () => {
          attempts += 1;
          try {
            const win = frame.contentWindow;
            if (win?.pskl?.app?.piskelController && win.pskl.app.importService) {
              this.bindDirtyTracking(win);
              resolve(win);
              return;
            }
          } catch (_error) {
            // Keep polling until the iframe is fully initialized.
          }
          if (attempts >= maxAttempts) {
            reject(new Error("Piskel did not finish loading"));
            return;
          }
          window.setTimeout(poll, 100);
        };
        poll();
      };

      frame.addEventListener("load", onLoad, { once: true });
      frame.addEventListener("error", () => {
        reject(new Error("Failed to load the embedded Piskel editor"));
      }, { once: true });
    });
    return this.readyPromise;
  }

  bindDirtyTracking(win) {
    const doc = win.document;
    if (!doc.getElementById("ventilastation-piskel-overrides")) {
      const style = doc.createElement("style");
      style.id = "ventilastation-piskel-overrides";
      style.textContent = ".fake-piskelapp-header { display: none !important; }";
      doc.head.appendChild(style);
    }
    doc.removeEventListener("input", this.handleDirtySignal, true);
    doc.removeEventListener("pointerup", this.handleDirtySignal, true);
    doc.removeEventListener("keyup", this.handleDirtySignal, true);
    doc.addEventListener("input", this.handleDirtySignal, true);
    doc.addEventListener("pointerup", this.handleDirtySignal, true);
    doc.addEventListener("keyup", this.handleDirtySignal, true);
  }

  handleDirtySignal() {
    if (this.suspendDirtyTracking || !this.onDirtyChange) {
      return;
    }
    this.onDirtyChange(true);
  }

  async withWindow(callback) {
    const win = await this.waitUntilReady();
    return callback(win);
  }

  async loadSerialized(serializedSprite) {
    return this.withWindow((win) => new Promise((resolve, reject) => {
      this.suspendDirtyTracking = true;
      try {
        win.pskl.utils.serialization.Deserializer.deserialize(
          normalizeSerializedSpriteDocument(serializedSprite),
          (piskel) => {
            win.pskl.app.piskelController.setPiskel(piskel);
            this.suspendDirtyTracking = false;
            resolve();
          },
          () => {
            this.suspendDirtyTracking = false;
            reject(new Error("Failed to deserialize the saved Piskel document"));
          },
        );
      } catch (error) {
        this.suspendDirtyTracking = false;
        reject(error);
      }
    }));
  }

  async importPng({ path, dataUrl, frames = 1 }) {
    return this.withWindow((win) => new Promise((resolve, reject) => {
      this.suspendDirtyTracking = true;
      const image = new win.Image();
      image.onload = () => {
        const frameCount = Math.max(1, Number(frames) || 1);
        const frameWidth = frameCount > 1
          ? Math.max(1, Math.trunc(image.width / frameCount))
          : image.width;
        win.pskl.app.importService.newPiskelFromImage(
          image,
          {
            importType: frameCount > 1 ? "sheet" : "single",
            name: stripExtension(path.split("/").pop()),
            smoothing: false,
            frameSizeX: frameWidth,
            frameSizeY: image.height,
            frameOffsetX: 0,
            frameOffsetY: 0,
          },
          (piskel) => {
            piskel.fps = 3;
            win.pskl.app.piskelController.setPiskel(piskel);
            win.pskl.app.piskelController.setFPS(3);
            this.suspendDirtyTracking = false;
            resolve();
          },
        );
      };
      image.onerror = () => {
        this.suspendDirtyTracking = false;
        reject(new Error(`Failed to import ${path} into Piskel`));
      };
      image.src = dataUrl;
    }));
  }

  async loadSprite({ path, pngBase64, serializedSprite, frames = 1 }) {
    if (serializedSprite) {
      await this.loadSerialized(serializedSprite);
      return;
    }
    await this.importPng({
      path,
      dataUrl: `data:image/png;base64,${pngBase64}`,
      frames,
    });
  }

  async serialize() {
    return this.withWindow((win) => win.pskl.app.piskelController.serialize());
  }

  async setFPS(fps) {
    return this.withWindow((win) => {
      win.pskl.app.piskelController.setFPS(fps);
    });
  }

  async exportPngBase64() {
    const dataUrl = await this.withWindow((win) => win.pskl.app.getFramesheetAsPng());
    return parseDataUrl(dataUrl).base64;
  }

  async focus() {
    return this.withWindow((win) => {
      win.focus();
    });
  }
}
