const BUTTONS = {
  JOY_LEFT: 1,
  JOY_RIGHT: 2,
  JOY_UP: 4,
  JOY_DOWN: 8,
  BUTTON_A: 16,
  BUTTON_B: 32,
  BUTTON_C: 64,
  BUTTON_D: 128,
};

const KEY_TO_BUTTON = new Map([
  ["ArrowLeft", BUTTONS.JOY_LEFT],
  ["ArrowRight", BUTTONS.JOY_RIGHT],
  ["ArrowUp", BUTTONS.JOY_UP],
  ["ArrowDown", BUTTONS.JOY_DOWN],
  ["KeyZ", BUTTONS.BUTTON_A],
  ["KeyX", BUTTONS.BUTTON_B],
  ["KeyC", BUTTONS.BUTTON_C],
  ["KeyV", BUTTONS.BUTTON_D],
]);

class MockRuntimeAdapter {
  constructor() {
    this.name = "Mock Runtime";
    this.buttons = 0;
    this.frame = 0;
    this.angle = 0;
    this.assets = [
      { slot: 1, width: 18, height: 18, frames: 1, palette: 0, data: new Uint8Array(18 * 18) },
      { slot: 2, width: 28, height: 10, frames: 1, palette: 0, data: new Uint8Array(28 * 10) },
    ];
    this.events = [];
  }

  setButtons(buttons) {
    this.buttons = buttons & 0xff;
  }

  exportFrame({ full = false } = {}) {
    this.frame += 1;
    this.angle = (this.angle + 0.02) % (Math.PI * 2);

    const radius = 90;
    const x = 128 + Math.round(Math.cos(this.angle) * radius);
    const y = 128 + Math.round(Math.sin(this.angle) * radius);
    const pressed = [];
    for (const [name, bit] of Object.entries(BUTTONS)) {
      if (this.buttons & bit) {
        pressed.push(name);
      }
    }

    if (pressed.length) {
      this.events = [{ command: "input", args: pressed }];
    } else {
      this.events = [];
    }

    return {
      frame: this.frame,
      buttons: this.buttons,
      column_offset: 0,
      gamma_mode: 1,
      palette: full ? new Uint8Array(0) : undefined,
      assets: full ? this.assets : [],
      events: this.events,
      sprites: [
        { slot: 1, image_strip: 1, x, y, frame: 0, perspective: 1 },
        { slot: 2, image_strip: 2, x: 128, y: 220, frame: 0, perspective: 0 },
      ],
    };
  }
}

class BrowserHostApp {
  constructor(adapter) {
    this.adapter = adapter;
    this.currentButtons = 0;
    this.assetIndex = new Map();
    this.lastFrame = null;
    this.canvas = document.querySelector("#frame-canvas");
    this.ctx = this.canvas.getContext("2d");
    this.elements = {
      adapterName: document.querySelector("#adapter-name"),
      frameCounter: document.querySelector("#frame-counter"),
      buttonMask: document.querySelector("#button-mask"),
      runtimeSummary: document.querySelector("#runtime-summary"),
      eventLog: document.querySelector("#event-log"),
      spriteLog: document.querySelector("#sprite-log"),
      assetLog: document.querySelector("#asset-log"),
    };
  }

  start() {
    this.elements.adapterName.textContent = this.adapter.name;
    this.bindInput();
    this.pollFrame(true);
  }

  bindInput() {
    window.addEventListener("keydown", (event) => {
      const bit = KEY_TO_BUTTON.get(event.code);
      if (!bit) {
        return;
      }
      event.preventDefault();
      this.currentButtons |= bit;
      this.adapter.setButtons(this.currentButtons);
      this.renderStatus();
    });

    window.addEventListener("keyup", (event) => {
      const bit = KEY_TO_BUTTON.get(event.code);
      if (!bit) {
        return;
      }
      event.preventDefault();
      this.currentButtons &= ~bit;
      this.adapter.setButtons(this.currentButtons);
      this.renderStatus();
    });

    window.addEventListener("blur", () => {
      this.currentButtons = 0;
      this.adapter.setButtons(0);
      this.renderStatus();
    });
  }

  pollFrame(full = false) {
    const frame = this.adapter.exportFrame({ full });
    this.lastFrame = frame;
    if (Array.isArray(frame.assets)) {
      for (const asset of frame.assets) {
        this.assetIndex.set(asset.slot, asset);
      }
    }
    this.renderFrame();
    requestAnimationFrame(() => this.pollFrame(false));
  }

  renderFrame() {
    const frame = this.lastFrame;
    if (!frame) {
      return;
    }

    const { width, height } = this.canvas;
    const cx = width / 2;
    const cy = height / 2;

    this.ctx.clearRect(0, 0, width, height);
    this.drawBackdrop(cx, cy, width, height);
    this.drawSprites(cx, cy, frame.sprites);
    this.renderStatus();
    this.renderInspectors(frame);
  }

  drawBackdrop(cx, cy, width, height) {
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = "#07090d";
    ctx.fillRect(0, 0, width, height);

    ctx.strokeStyle = "rgba(83, 209, 182, 0.2)";
    ctx.lineWidth = 1;
    for (let r = 90; r <= 320; r += 60) {
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
    }

    for (let a = 0; a < 16; a += 1) {
      const angle = (a / 16) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(angle) * 340, cy + Math.sin(angle) * 340);
      ctx.stroke();
    }
    ctx.restore();
  }

  drawSprites(cx, cy, sprites) {
    const ctx = this.ctx;
    for (const sprite of sprites) {
      const asset = this.assetIndex.get(sprite.image_strip);
      const width = asset?.width ?? 12;
      const height = asset?.height ?? 12;
      const x = (sprite.x / 255) * this.canvas.width;
      const y = this.canvas.height - (sprite.y / 255) * this.canvas.height;

      ctx.save();
      if (sprite.perspective === 0) {
        ctx.fillStyle = "rgba(255, 209, 102, 0.22)";
        ctx.beginPath();
        ctx.arc(cx, cy, Math.max(width, height) * 6, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "#ffd166";
        ctx.stroke();
      } else {
        ctx.fillStyle = sprite.perspective === 2 ? "#ff6b6b" : "#53d1b6";
        ctx.fillRect(x - width * 2, y - height * 2, width * 4, height * 4);
        ctx.strokeStyle = "rgba(255,255,255,0.35)";
        ctx.strokeRect(x - width * 2, y - height * 2, width * 4, height * 4);
      }
      ctx.restore();
    }
  }

  renderStatus() {
    this.elements.buttonMask.textContent = `Buttons 0x${this.currentButtons.toString(16).padStart(2, "0")}`;
    if (this.lastFrame) {
      this.elements.frameCounter.textContent = `Frame ${this.lastFrame.frame}`;
    }
  }

  renderInspectors(frame) {
    const summary = [
      ["Sprites", frame.sprites.length],
      ["Assets", this.assetIndex.size],
      ["Events", frame.events.length],
      ["Column Offset", frame.column_offset],
      ["Gamma", frame.gamma_mode],
      ["Buttons", `0x${frame.buttons.toString(16).padStart(2, "0")}`],
    ];

    this.elements.runtimeSummary.innerHTML = summary.map(([label, value]) => `
      <div class="summary-card">
        <strong>${label}</strong>
        <span>${value}</span>
      </div>
    `).join("");

    this.elements.eventLog.textContent = JSON.stringify(frame.events, null, 2);
    this.elements.spriteLog.textContent = JSON.stringify(frame.sprites, null, 2);
    this.elements.assetLog.textContent = JSON.stringify([...this.assetIndex.values()].map((asset) => ({
      ...asset,
      data: `[${asset.data?.length ?? 0} bytes]`,
    })), null, 2);
  }
}

async function resolveAdapter() {
  const adapter = window.VentilastationRuntimeAdapter;
  if (adapter && typeof adapter.setButtons === "function" && typeof adapter.exportFrame === "function") {
    return adapter;
  }
  const createWasmAdapter = window.createVentilastationWasmAdapter;
  if (typeof createWasmAdapter === "function") {
    try {
      const wasmAdapter = await createWasmAdapter();
      if (wasmAdapter && typeof wasmAdapter.setButtons === "function" && typeof wasmAdapter.exportFrame === "function") {
        return wasmAdapter;
      }
    } catch (error) {
      console.error("Failed to initialize Ventilastation WASM adapter", error);
    }
  }
  return new MockRuntimeAdapter();
}

resolveAdapter().then((adapter) => {
  new BrowserHostApp(adapter).start();
});
