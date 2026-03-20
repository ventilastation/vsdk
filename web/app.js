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
  ["Space", BUTTONS.BUTTON_A],
  ["KeyO", BUTTONS.BUTTON_B],
  ["KeyP", BUTTONS.BUTTON_C],
  ["Escape", BUTTONS.BUTTON_D],
]);

const LedRenderCore = globalThis.VentilastationLedRenderCore;
if (!LedRenderCore) {
  throw new Error("Missing VentilastationLedRenderCore");
}

const {
  COLUMNS,
  PIXELS,
  computeLedFramePixels,
  createLedRingGeometry,
  repeatLedColors,
} = LedRenderCore;

const FORCE_2D_STORAGE_KEY = "ventilastation.force2dFallback";
const INSPECTOR_OPEN_STORAGE_KEY = "ventilastation.inspectorOpen.v2";

function decodeSigned16(low, high) {
  let value = low | (high << 8);
  if (value & 0x8000) {
    value -= 0x10000;
  }
  return value;
}

function decodeLegacySpriteBuffer(buffer) {
  if (!(buffer instanceof Uint8Array)) {
    return [];
  }
  const stride = 9;
  const sprites = [];
  for (let offset = 0; offset + stride <= buffer.length; offset += stride) {
    sprites.push({
      slot: buffer[offset],
      frame: buffer[offset + 1],
      image_strip: buffer[offset + 2] | (buffer[offset + 3] << 8),
      x: decodeSigned16(buffer[offset + 4], buffer[offset + 5]),
      y: decodeSigned16(buffer[offset + 6], buffer[offset + 7]),
      perspective: (buffer[offset + 8] & 0x80) ? buffer[offset + 8] - 0x100 : buffer[offset + 8],
    });
  }
  return sprites;
}

function decodePerspective(value) {
  return (value & 0x80) ? value - 0x100 : value;
}

function decodeSpriteStateBuffer(buffer) {
  if (!(buffer instanceof Uint8Array)) {
    return [];
  }
  const stride = 5;
  const sprites = [];
  for (let slot = 0; slot * stride + stride <= buffer.length; slot += 1) {
    const offset = slot * stride;
    const frame = buffer[offset + 3];
    if (frame === 0xff) {
      continue;
    }
    sprites.push({
      slot,
      x: buffer[offset],
      y: buffer[offset + 1],
      image_strip: buffer[offset + 2],
      frame,
      perspective: decodePerspective(buffer[offset + 4]),
    });
  }
  return sprites;
}

function decodeImageStripPayload(slot, payload) {
  if (!(payload instanceof Uint8Array) || payload.length < 4) {
    return null;
  }
  let width = payload[0];
  if (width === 255) {
    width = 256;
  }
  const height = payload[1];
  const frames = payload[2] || 1;
  const palette = payload[3] || 0;
  const data = payload.slice(4);
  return {
    slot,
    width,
    height,
    frames,
    palette,
    dataLength: data.length,
    loadedBytes: data.length,
    data,
  };
}

class LedRingWebGLRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.geometry = createLedRingGeometry();
    this.gl = canvas.getContext("webgl", {
      alpha: true,
      antialias: true,
      premultipliedAlpha: false,
    });
    this.available = Boolean(this.gl);
    if (!this.available) {
      this.fallbackCtx = canvas.getContext("2d");
      return;
    }

    const gl = this.gl;
    this.blendMinMax = gl.getExtension("EXT_blend_minmax");
    this.program = this.createProgram(
      `
        attribute vec2 a_position;
        attribute vec2 a_texCoord;
        attribute vec4 a_color;
        uniform vec2 u_resolution;
        uniform vec2 u_center;
        uniform float u_scale;
        varying vec2 v_texCoord;
        varying vec4 v_color;

        void main() {
          vec2 pos = u_center + (a_position * vec2(1.0, -1.0) * u_scale);
          vec2 zeroToOne = pos / u_resolution;
          vec2 clip = zeroToOne * 2.0 - 1.0;
          gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
          v_texCoord = a_texCoord;
          v_color = a_color;
        }
      `,
      `
        precision mediump float;
        varying vec2 v_texCoord;
        varying vec4 v_color;

        void main() {
          vec2 center = vec2(0.5, 0.5);
          vec2 p = v_texCoord - center;
          float width = 0.1;
          float height = 0.05;
          float radius = height;
          vec2 q = abs(p) - vec2(width - radius, height - radius);
          float dist = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - radius;
          float pill = smoothstep(0.01, -0.01, dist);
          float glow = exp(-dist * dist * 10.0) * 0.3;
          gl_FragColor = v_color * (pill + glow);
        }
      `
    );

    this.positionBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.positionBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, this.geometry.positions, gl.STATIC_DRAW);

    this.texCoordBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.texCoordBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, this.geometry.texCoords, gl.STATIC_DRAW);

    this.colorBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.colorBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, this.geometry.vertexCount * 4, gl.DYNAMIC_DRAW);

    this.attribs = {
      position: gl.getAttribLocation(this.program, "a_position"),
      texCoord: gl.getAttribLocation(this.program, "a_texCoord"),
      color: gl.getAttribLocation(this.program, "a_color"),
    };
    this.uniforms = {
      resolution: gl.getUniformLocation(this.program, "u_resolution"),
      center: gl.getUniformLocation(this.program, "u_center"),
      scale: gl.getUniformLocation(this.program, "u_scale"),
    };

    gl.enable(gl.BLEND);
    if (this.blendMinMax) {
      gl.blendFunc(gl.SRC_COLOR, gl.SRC_COLOR);
      gl.blendEquation(this.blendMinMax.MAX_EXT);
    } else {
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
    }
  }

  createShader(type, source) {
    const gl = this.gl;
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(shader) || "WebGL shader compile failed");
    }
    return shader;
  }

  createProgram(vertexSource, fragmentSource) {
    const gl = this.gl;
    const program = gl.createProgram();
    gl.attachShader(program, this.createShader(gl.VERTEX_SHADER, vertexSource));
    gl.attachShader(program, this.createShader(gl.FRAGMENT_SHADER, fragmentSource));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program) || "WebGL program link failed");
    }
    return program;
  }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(this.canvas.clientWidth * dpr));
    const height = Math.max(1, Math.round(this.canvas.clientHeight * dpr));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    if (this.gl) {
      this.gl.viewport(0, 0, width, height);
    }
    return { width, height };
  }

  clear() {
    if (!this.gl) {
      return;
    }
    this.gl.clearColor(0.02, 0.03, 0.05, 1.0);
    this.gl.clear(this.gl.COLOR_BUFFER_BIT);
  }

  render(ledPixels) {
    if (!this.available) {
      return false;
    }

    const { width, height } = this.resize();
    const gl = this.gl;
    this.clear();
    gl.useProgram(this.program);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.positionBuffer);
    gl.enableVertexAttribArray(this.attribs.position);
    gl.vertexAttribPointer(this.attribs.position, 2, gl.FLOAT, false, 0, 0);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.texCoordBuffer);
    gl.enableVertexAttribArray(this.attribs.texCoord);
    gl.vertexAttribPointer(this.attribs.texCoord, 2, gl.FLOAT, false, 0, 0);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.colorBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, repeatLedColors(ledPixels, 6), gl.DYNAMIC_DRAW);
    gl.enableVertexAttribArray(this.attribs.color);
    gl.vertexAttribPointer(this.attribs.color, 4, gl.UNSIGNED_BYTE, true, 0, 0);

    gl.uniform2f(this.uniforms.resolution, width, height);
    gl.uniform2f(this.uniforms.center, width * 0.5, height * 0.5);
    gl.uniform1f(this.uniforms.scale, Math.min(width, height) / 200);
    gl.drawArrays(gl.TRIANGLES, 0, this.geometry.vertexCount);
    return true;
  }
}

class LedRingCanvasRenderer {
  constructor(canvas, geometry) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.geometry = geometry;
  }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(this.canvas.clientWidth * dpr));
    const height = Math.max(1, Math.round(this.canvas.clientHeight * dpr));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    return { width, height };
  }

  render(ledPixels) {
    if (!this.ctx) {
      return;
    }
    const { width, height } = this.resize();
    const scale = Math.min(width, height) / 200;
    const ctx = this.ctx;
    const positions = this.geometry.positions;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#05070b";
    ctx.fillRect(0, 0, width, height);

    for (let column = 0; column < COLUMNS; column += 1) {
      for (let led = 0; led < PIXELS; led += 1) {
        const colorOffset = (column * PIXELS + led) * 4;
        const red = ledPixels[colorOffset];
        const green = ledPixels[colorOffset + 1];
        const blue = ledPixels[colorOffset + 2];
        const alpha = ledPixels[colorOffset + 3];
        if (!red && !green && !blue) {
          continue;
        }

        const vertexOffset = (column * PIXELS + led) * 12;
        const x1 = width * 0.5 + positions[vertexOffset] * scale;
        const y1 = height * 0.5 + positions[vertexOffset + 1] * scale;
        const x2 = width * 0.5 + positions[vertexOffset + 2] * scale;
        const y2 = height * 0.5 + positions[vertexOffset + 3] * scale;
        const x3 = width * 0.5 + positions[vertexOffset + 4] * scale;
        const y3 = height * 0.5 + positions[vertexOffset + 5] * scale;
        const x4 = width * 0.5 + positions[vertexOffset + 10] * scale;
        const y4 = height * 0.5 + positions[vertexOffset + 11] * scale;

        ctx.fillStyle = `rgba(${red}, ${green}, ${blue}, ${Math.max(alpha, 192) / 255})`;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.lineTo(x3, y3);
        ctx.lineTo(x4, y4);
        ctx.closePath();
        ctx.fill();

        ctx.fillStyle = `rgba(${red}, ${green}, ${blue}, 0.18)`;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.lineTo(x3, y3);
        ctx.lineTo(x4, y4);
        ctx.closePath();
        ctx.fill();
      }
    }
  }
}

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
    this.palette = new Uint8Array(256 * 4);
    this.events = [];

    this.palette[1 * 4 + 1] = 160;
    this.palette[1 * 4 + 2] = 220;
    this.palette[1 * 4 + 3] = 64;
    this.palette[2 * 4 + 1] = 80;
    this.palette[2 * 4 + 2] = 160;
    this.palette[2 * 4 + 3] = 255;

    this.assets[0].data.fill(255);
    this.assets[1].data.fill(255);
    for (let x = 0; x < 18; x += 1) {
      for (let y = 0; y < 18; y += 1) {
        const dx = x - 9;
        const dy = y - 9;
        if (dx * dx + dy * dy < 56) {
          this.assets[0].data[x * 18 + y] = 1;
        }
      }
    }
    for (let x = 0; x < 28; x += 1) {
      for (let y = 0; y < 10; y += 1) {
        if (Math.abs(y - 5) < 3) {
          this.assets[1].data[x * 10 + y] = 2;
        }
      }
    }
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
      palette_length: this.palette.length,
      palette_version: 1,
      palette_dirty: Boolean(full),
      palette: full ? this.palette : undefined,
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
  constructor(runtime) {
    this.adapter = runtime.adapter;
    this.runtime = runtime;
    this.currentButtons = 0;
    this.assetIndex = new Map();
    this.assetRenderCache = new Map();
    this.visibleStripSlots = [];
    this.palette = null;
    this.paletteVersion = 0;
    this.paletteLoadedBytes = 0;
    this.lastFrame = null;
    this.lastFrameShape = null;
    this.lastRenderedLedPixels = null;
    this.diagnostics = [];
    this.force2dFallback = this.readForce2dPreference();
    this.inspectorOpen = this.readInspectorPreference();
    this.canvas = document.querySelector("#frame-canvas");
    this.renderer = new LedRingWebGLRenderer(this.canvas);
    this.fallbackRenderer = new LedRingCanvasRenderer(this.canvas, this.renderer.geometry);
    this.elements = {
      adapterName: document.querySelector("#adapter-name"),
      adapterSource: document.querySelector("#adapter-source"),
      frameCounter: document.querySelector("#frame-counter"),
      buttonMask: document.querySelector("#button-mask"),
      runtimeBanner: document.querySelector("#runtime-banner"),
      runtimeMessage: document.querySelector("#runtime-message"),
      inspectorPanel: document.querySelector("#inspector-panel"),
      toggleInspectorButton: document.querySelector("#toggle-inspector-button"),
      copyDiagnostics: document.querySelector("#copy-diagnostics"),
      copyDiagnosticsButton: document.querySelector("#copy-diagnostics-button"),
      copyDiagnosticsStatus: document.querySelector("#copy-diagnostics-status"),
      runtimeSummary: document.querySelector("#runtime-summary"),
      force2dFallback: document.querySelector("#force-2d-fallback"),
      diagnosticLog: document.querySelector("#diagnostic-log"),
      frameShape: document.querySelector("#frame-shape"),
      eventLog: document.querySelector("#event-log"),
      spriteLog: document.querySelector("#sprite-log"),
      assetLog: document.querySelector("#asset-log"),
    };
    this.copyStatusTimer = null;
    this.refreshCopyDiagnostics();
  }

  usesEventStreamProtocol(frame) {
    return Array.isArray(frame?.events) && frame.events.some((event) => (
      event &&
      typeof event === "object" &&
      (event.command === "palette" || event.command === "imagestrip" || event.command === "sprites")
    ));
  }

  processFrameEvents(frame) {
    if (!Array.isArray(frame.events) || !frame.events.length) {
      if (!Array.isArray(frame.sprites)) {
        frame.sprites = [];
      }
      if (!Array.isArray(frame.assets)) {
        frame.assets = [];
      }
      return;
    }

    let decodedSprites = null;
    const remainingEvents = [];

    for (const event of frame.events) {
      if (!event || typeof event !== "object") {
        continue;
      }
      if (event.command === "palette" && event.data instanceof Uint8Array) {
        this.palette = event.data;
        this.paletteLoadedBytes = event.data.length;
        this.paletteVersion += 1;
        this.assetRenderCache.clear();
        continue;
      }
      if (event.command === "imagestrip" && event.data instanceof Uint8Array) {
        const slot = Number(event.args?.[0] ?? -1);
        const asset = decodeImageStripPayload(slot, event.data);
        if (asset) {
          this.assetIndex.set(slot, asset);
          this.assetRenderCache.delete(slot);
        }
        continue;
      }
      if (event.command === "sprites" && event.data instanceof Uint8Array) {
        decodedSprites = decodeSpriteStateBuffer(event.data);
        continue;
      }
      remainingEvents.push(event);
    }

    frame.sprites = decodedSprites || [];
    frame.assets = [];
    frame.events = remainingEvents;
  }

  start() {
    this.elements.adapterName.textContent = this.adapter.name;
    this.elements.adapterSource.textContent = this.runtime.source;
    this.addDiagnostic("adapter.start", {
      name: this.adapter.name,
      source: this.runtime.source,
      hasTick: typeof this.adapter.tick === "function",
      hasExportFrame: typeof this.adapter.exportFrame === "function",
      hasWebGL: this.renderer.available,
    });
    this.renderRuntimeStatus();
    this.bindInput();
    this.bindCopyDiagnostics();
    this.bindDebugControls();
    this.bindInspectorToggle();
    this.renderInspectorVisibility();
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
      this.addDiagnostic("input.keydown", { code: event.code, buttons: this.currentButtons });
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
      this.addDiagnostic("input.keyup", { code: event.code, buttons: this.currentButtons });
      this.renderStatus();
    });

    window.addEventListener("blur", () => {
      this.currentButtons = 0;
      this.adapter.setButtons(0);
      this.addDiagnostic("input.blur", { buttons: 0 });
      this.renderStatus();
    });
  }

  bindCopyDiagnostics() {
    if (!this.elements.copyDiagnosticsButton) {
      return;
    }
    this.elements.copyDiagnosticsButton.addEventListener("click", async () => {
      const text = this.refreshCopyDiagnostics();
      if (!text) {
        this.setCopyDiagnosticsStatus("Empty");
        return;
      }
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(text);
        } else {
          this.copyViaSelection(text);
        }
        this.setCopyDiagnosticsStatus("Copied");
      } catch (error) {
        console.error("Copy diagnostics failed", error);
        this.setCopyDiagnosticsStatus("Copy failed");
      }
    });
  }

  bindDebugControls() {
    if (!this.elements.force2dFallback) {
      return;
    }
    this.elements.force2dFallback.checked = this.force2dFallback;
    this.elements.force2dFallback.addEventListener("change", () => {
      this.force2dFallback = Boolean(this.elements.force2dFallback.checked);
      this.writeForce2dPreference(this.force2dFallback);
      this.addDiagnostic("renderer.mode", {
        forced2d: this.force2dFallback,
        webglAvailable: this.renderer.available,
      });
      this.renderStatus();
      this.renderFrame();
    });
  }

  bindInspectorToggle() {
    if (!this.elements.toggleInspectorButton || !this.elements.inspectorPanel) {
      return;
    }
    this.elements.toggleInspectorButton.addEventListener("click", () => {
      this.inspectorOpen = !this.inspectorOpen;
      this.writeInspectorPreference(this.inspectorOpen);
      this.renderInspectorVisibility();
      if (this.inspectorOpen && this.lastFrame) {
        this.renderInspectors(this.lastFrame);
      }
    });
  }

  renderInspectorVisibility() {
    if (!this.elements.toggleInspectorButton || !this.elements.inspectorPanel) {
      return;
    }
    this.elements.inspectorPanel.hidden = !this.inspectorOpen;
    this.elements.toggleInspectorButton.textContent = this.inspectorOpen ? "Hide" : "Show";
    this.elements.toggleInspectorButton.setAttribute("aria-expanded", this.inspectorOpen ? "true" : "false");
  }

  readForce2dPreference() {
    try {
      return localStorage.getItem(FORCE_2D_STORAGE_KEY) === "1";
    } catch (_error) {
      return false;
    }
  }

  writeForce2dPreference(enabled) {
    try {
      if (enabled) {
        localStorage.setItem(FORCE_2D_STORAGE_KEY, "1");
      } else {
        localStorage.removeItem(FORCE_2D_STORAGE_KEY);
      }
    } catch (_error) {
      return;
    }
  }

  readInspectorPreference() {
    try {
      return localStorage.getItem(INSPECTOR_OPEN_STORAGE_KEY) === "1";
    } catch (_error) {
      return false;
    }
  }

  writeInspectorPreference(enabled) {
    try {
      if (enabled) {
        localStorage.setItem(INSPECTOR_OPEN_STORAGE_KEY, "1");
      } else {
        localStorage.removeItem(INSPECTOR_OPEN_STORAGE_KEY);
      }
    } catch (_error) {
      return;
    }
  }

  copyViaSelection(text) {
    const textarea = this.elements.copyDiagnostics;
    const previousSelectionStart = textarea.selectionStart;
    const previousSelectionEnd = textarea.selectionEnd;
    textarea.focus();
    textarea.select();
    document.execCommand("copy");
    textarea.setSelectionRange(previousSelectionStart, previousSelectionEnd);
  }

  setCopyDiagnosticsStatus(message) {
    if (!this.elements.copyDiagnosticsStatus) {
      return;
    }
    this.elements.copyDiagnosticsStatus.textContent = message;
    if (this.copyStatusTimer) {
      clearTimeout(this.copyStatusTimer);
    }
    this.copyStatusTimer = window.setTimeout(() => {
      this.elements.copyDiagnosticsStatus.textContent = "";
      this.copyStatusTimer = null;
    }, 1500);
  }

  refreshCopyDiagnostics() {
    const diagnostics = this.diagnostics.slice();
    const frameShape = this.lastFrameShape || this.describeFrame(this.lastFrame || {});
    const text = this.buildDiagnosticBundle(frameShape, diagnostics);
    if (this.elements.copyDiagnostics) {
      this.elements.copyDiagnostics.value = text;
    }
    return text;
  }

  async pollFrame(full = false) {
    try {
      if (typeof this.adapter.tick === "function") {
        await Promise.resolve(this.adapter.tick(1));
      }
      const frame = await Promise.resolve(this.adapter.exportFrame({ full }));
      if (!frame || typeof frame !== "object") {
        throw new Error(`Invalid frame payload: ${String(frame)}`);
      }
      if (this.usesEventStreamProtocol(frame)) {
        this.processFrameEvents(frame);
      } else if (frame.sprites instanceof Uint8Array) {
        frame.sprites = decodeLegacySpriteBuffer(frame.sprites);
      } else if (!Array.isArray(frame.sprites)) {
        frame.sprites = [];
      }
      if (!(this.palette instanceof Uint8Array) && frame.palette instanceof Uint8Array) {
        this.palette = frame.palette;
        this.paletteVersion = Number(frame.palette_version || 0);
        this.paletteLoadedBytes = frame.palette.length;
      }
      if (Array.isArray(frame.assets) && frame.assets.length) {
        for (const asset of frame.assets) {
          this.assetIndex.set(asset.slot, {
            ...asset,
            dataLength: asset.data?.length ?? 0,
            loadedBytes: asset.data?.length ?? 0,
            data: asset.data ?? null,
          });
        }
      }
      this.lastFrame = frame;
      this.visibleStripSlots = Array.isArray(frame.sprites)
        ? [...new Set(frame.sprites.map((sprite) => sprite.image_strip).filter((slot) => Number.isInteger(slot) && slot > 0))]
        : [];
      this.addDiagnostic("frame.ok", {
        frame: frame.frame,
        sprites: Array.isArray(frame.sprites) ? frame.sprites.length : -1,
        assets: this.assetIndex.size,
        hasPalette: this.palette instanceof Uint8Array,
      });
      this.renderFrame();
    } catch (error) {
      this.runtime.error = error;
      this.addDiagnostic("frame.error", {
        message: error.message || String(error),
        stack: error.stack || null,
      });
      this.renderRuntimeStatus();
      console.error("Frame polling failed", error);
    } finally {
      window.setTimeout(() => this.pollFrame(false), 33);
    }
  }

  async drainPaletteUpdates(frame) {
    if (!(this.palette instanceof Uint8Array) && frame.palette instanceof Uint8Array) {
      this.palette = frame.palette;
      this.paletteVersion = Number(frame.palette_version || 0);
      this.paletteLoadedBytes = frame.palette.length;
    }
    if (typeof this.adapter.exportPaletteChunk !== "function") {
      return;
    }
    const paletteLength = Number(frame.palette_length || 0);
    const paletteVersion = Number(frame.palette_version || 0);
    const paletteDirty = Boolean(frame.palette_dirty);
    if (!paletteLength) {
      return;
    }
    if (!(this.palette instanceof Uint8Array) || this.palette.length !== paletteLength || this.paletteVersion !== paletteVersion) {
      this.palette = new Uint8Array(paletteLength);
      this.paletteVersion = paletteVersion;
      this.paletteLoadedBytes = 0;
      this.assetChunkQueue = [];
      this.assetChunkInFlight = false;
      this.assetRenderCache.clear();
    }
    if (!paletteDirty && this.paletteLoadedBytes >= paletteLength) {
      return;
    }
    if (this.paletteLoadInFlight) {
      return;
    }
    this.paletteLoadInFlight = true;
    try {
      let iterations = 0;
      while (this.paletteLoadedBytes < paletteLength && iterations < 4) {
        const chunk = await Promise.resolve(
          this.adapter.exportPaletteChunk({ offset: this.paletteLoadedBytes, chunkSize: 2048 })
        );
        if (!chunk || !(chunk.data instanceof Uint8Array)) {
          return;
        }
        this.palette.set(chunk.data, chunk.offset);
        this.paletteLoadedBytes = chunk.offset + chunk.data.length;
        iterations += 1;
      }
    } finally {
      this.paletteLoadInFlight = false;
    }
  }

  async drainAssetUpdates(full = false) {
    if (typeof this.adapter.exportAssets !== "function" && Array.isArray(this.lastFrame?.assets) && this.lastFrame.assets.length) {
      for (const asset of this.lastFrame.assets) {
        this.assetIndex.set(asset.slot, {
          ...asset,
          dataLength: asset.data?.length ?? 0,
          data: asset.data ?? null,
          loadedBytes: asset.data?.length ?? 0,
        });
      }
      return;
    }
    if (typeof this.adapter.exportAssets !== "function") {
      return;
    }
    const needsVisibleAsset = this.visibleStripSlots.some((slot) => {
      const asset = this.assetIndex.get(slot);
      return !asset || !(asset.data instanceof Uint8Array) || asset.loadedBytes < asset.dataLength;
    });
    if (!full && !needsVisibleAsset && this.assetChunkQueue.length === 0 && (this.assetMetadataPollFrame % 12) !== 0) {
      return;
    }
    const maxItems = full ? 1 : 2;
    for (;;) {
      const assets = await Promise.resolve(this.adapter.exportAssets({ full: false, maxItems }));
      if (!Array.isArray(assets) || assets.length === 0) {
        return;
      }
      for (const asset of assets) {
        const existing = this.assetIndex.get(asset.slot);
        const dataLength = asset.data_length ?? existing?.dataLength ?? 0;
        const metadataChanged = !existing ||
          existing.width !== asset.width ||
          existing.height !== asset.height ||
          existing.frames !== asset.frames ||
          existing.palette !== asset.palette ||
          existing.dataLength !== dataLength;
        const normalized = {
          ...existing,
          ...asset,
          dataLength,
          data: metadataChanged ? null : (existing?.data ?? null),
          loadedBytes: metadataChanged ? 0 : (existing?.loadedBytes ?? 0),
        };
        if (metadataChanged || !(normalized.data instanceof Uint8Array) || normalized.data.length !== normalized.dataLength) {
          normalized.data = new Uint8Array(normalized.dataLength);
          normalized.loadedBytes = 0;
        }
        this.assetIndex.set(asset.slot, normalized);
        this.assetRenderCache.delete(asset.slot);
        this.queueAssetForLoading(asset.slot);
      }
      await this.drainAssetChunks();
      if (assets.length < maxItems) {
        return;
      }
    }
  }

  queueAssetForLoading(slot) {
    if (this.assetChunkQueue.includes(slot)) {
      return;
    }
    const asset = this.assetIndex.get(slot);
    if (!asset || !asset.dataLength || asset.loadedBytes >= asset.dataLength) {
      return;
    }
    this.assetChunkQueue.push(slot);
  }

  prioritizeVisibleAssetChunks() {
    if (!this.visibleStripSlots.length || !this.assetChunkQueue.length) {
      return;
    }
    const priority = [];
    const remaining = [];
    for (const slot of this.assetChunkQueue) {
      if (this.visibleStripSlots.includes(slot)) {
        priority.push(slot);
      } else {
        remaining.push(slot);
      }
    }
    for (const slot of this.visibleStripSlots) {
      if (!priority.includes(slot)) {
        const asset = this.assetIndex.get(slot);
        if (asset && asset.dataLength && asset.loadedBytes < asset.dataLength) {
          priority.push(slot);
        }
      }
    }
    this.assetChunkQueue = [...priority, ...remaining];
  }

  async drainAssetChunks() {
    if (this.assetChunkInFlight || typeof this.adapter.exportAssetChunk !== "function") {
      return;
    }
    this.assetChunkInFlight = true;
    try {
      this.prioritizeVisibleAssetChunks();
      const hasPendingVisibleAsset = this.visibleStripSlots.some((slot) => {
        const asset = this.assetIndex.get(slot);
        return asset && asset.dataLength && asset.loadedBytes < asset.dataLength;
      });
      const maxIterations = hasPendingVisibleAsset ? 12 : 6;
      let iterations = 0;
      while (this.assetChunkQueue.length && iterations < maxIterations) {
        const slot = this.assetChunkQueue.shift();
        const asset = this.assetIndex.get(slot);
        if (!asset || !asset.dataLength || asset.loadedBytes >= asset.dataLength) {
          iterations += 1;
          continue;
        }
        const chunk = await Promise.resolve(
          this.adapter.exportAssetChunk(slot, { offset: asset.loadedBytes, chunkSize: 2048 })
        );
        if (!chunk || !(chunk.data instanceof Uint8Array)) {
          iterations += 1;
          continue;
        }
        if (!(asset.data instanceof Uint8Array) || chunk.total_length !== asset.dataLength) {
          asset.dataLength = chunk.total_length;
          asset.data = new Uint8Array(asset.dataLength);
          asset.loadedBytes = 0;
        }
        if (chunk.offset < 0 || chunk.offset + chunk.data.length > asset.data.length) {
          this.addDiagnostic("asset.chunk_bounds", {
            slot,
            offset: chunk.offset,
            chunkLength: chunk.data.length,
            dataLength: asset.data.length,
            totalLength: chunk.total_length,
          });
          iterations += 1;
          continue;
        }
        asset.data.set(chunk.data, chunk.offset);
        asset.loadedBytes = chunk.offset + chunk.data.length;
        this.assetIndex.set(slot, asset);
        this.assetRenderCache.delete(slot);
        if (asset.loadedBytes < asset.dataLength) {
          this.assetChunkQueue.push(slot);
        }
        iterations += 1;
      }
    } finally {
      this.assetChunkInFlight = false;
    }
  }

  renderFrame() {
    const frame = this.lastFrame;
    if (!frame) {
      return;
    }

    const hasPendingVisibleAsset = this.visibleStripSlots.some((slot) => {
      const asset = this.assetIndex.get(slot);
      return !asset || !(asset.data instanceof Uint8Array) || asset.loadedBytes < asset.dataLength;
    });
    const ledPixels = hasPendingVisibleAsset && this.lastRenderedLedPixels
      ? this.lastRenderedLedPixels
      : computeLedFramePixels(frame, this.assetIndex, this.palette);
    if (!hasPendingVisibleAsset) {
      this.lastRenderedLedPixels = ledPixels;
    }
    const rendered = !this.force2dFallback && this.renderer.render(ledPixels);
    if (!rendered && this.fallbackRenderer) {
      this.fallbackRenderer.render(ledPixels);
    }
    this.renderStatus();
    this.renderInspectors(frame);
  }

  getAssetFrameImage(asset, frameNumber) {
    if (!asset || !(asset.data instanceof Uint8Array) || asset.loadedBytes < asset.dataLength || !(this.palette instanceof Uint8Array)) {
      return null;
    }

    const cached = this.assetRenderCache.get(asset.slot);
    if (cached && cached.asset === asset && cached.paletteVersion === this.paletteVersion) {
      return cached.frames[frameNumber % cached.frames.length] || null;
    }

    const frames = this.decodeAssetFrames(asset);
    this.assetRenderCache.set(asset.slot, {
      asset,
      frames,
      paletteVersion: this.paletteVersion,
    });
    return frames[frameNumber % frames.length] || null;
  }

  decodeAssetFrames(asset) {
    const frames = [];
    const totalFrames = Math.max(asset.frames || 1, 1);
    const bytesPerFrame = asset.width * asset.height;
    const paletteBase = (asset.palette || 0) * 256 * 4;

    for (let frameIndex = 0; frameIndex < totalFrames; frameIndex += 1) {
      const canvas = document.createElement("canvas");
      canvas.width = asset.width;
      canvas.height = asset.height;
      const context = canvas.getContext("2d");
      const imageData = context.createImageData(asset.width, asset.height);
      const frameOffset = frameIndex * bytesPerFrame;

      for (let x = 0; x < asset.width; x += 1) {
        for (let y = 0; y < asset.height; y += 1) {
          const colorIndex = asset.data[frameOffset + x * asset.height + y];
          const dest = (y * asset.width + x) * 4;
          if (colorIndex === 255) {
            imageData.data[dest + 3] = 0;
            continue;
          }
          const paletteOffset = paletteBase + colorIndex * 4;
          imageData.data[dest] = this.palette[paletteOffset + 3] || 0;
          imageData.data[dest + 1] = this.palette[paletteOffset + 2] || 0;
          imageData.data[dest + 2] = this.palette[paletteOffset + 1] || 0;
          imageData.data[dest + 3] = 255;
        }
      }

      context.putImageData(imageData, 0, 0);
      frames.push(canvas);
    }

    return frames;
  }

  renderStatus() {
    this.elements.buttonMask.textContent = `Buttons 0x${this.currentButtons.toString(16).padStart(2, "0")}`;
    if (this.lastFrame) {
      this.elements.frameCounter.textContent = `Frame ${this.lastFrame.frame}`;
    }
  }

  renderRuntimeStatus() {
    const { runtimeBanner, runtimeMessage } = this.elements;
    runtimeBanner.hidden = false;
    runtimeBanner.classList.remove("is-error", "is-warning");

    if (this.runtime.source === "wasm") {
      runtimeMessage.textContent = "Using real MicroPython WASM runtime.";
      return;
    }

    if (this.runtime.error) {
      runtimeBanner.classList.add("is-warning");
      runtimeMessage.textContent =
        `Fell back to mock runtime.\n\nReason:\n${this.runtime.error.stack || this.runtime.error.message || String(this.runtime.error)}`;
      return;
    }

    runtimeBanner.classList.add("is-warning");
    runtimeMessage.textContent = "Using mock runtime.";
  }

  renderInspectors(frame) {
    if (!this.inspectorOpen) {
      return;
    }
    const summary = [
      ["Sprites", frame.sprites.length],
      ["Assets", this.assetIndex.size],
      ["Events", frame.events.length],
      ["Column Offset", frame.column_offset],
      ["Gamma", frame.gamma_mode],
      ["Buttons", `0x${frame.buttons.toString(16).padStart(2, "0")}`],
      ["Renderer", this.force2dFallback ? "2D fallback" : this.renderer.available ? "WebGL" : "2D fallback"],
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
    const frameShape = this.describeFrame(frame);
    this.lastFrameShape = frameShape;
    const diagnostics = this.diagnostics.slice();
    this.elements.frameShape.textContent = JSON.stringify(frameShape, null, 2);
    this.elements.diagnosticLog.textContent = JSON.stringify(diagnostics, null, 2);
    this.refreshCopyDiagnostics();
  }

  describeFrame(frame) {
    const firstAsset = this.assetIndex.size ? this.assetIndex.values().next().value : null;
    return {
      frameType: typeof frame,
      keys: Object.keys(frame || {}),
      paletteType: frame.palette?.constructor?.name,
      paletteLength: frame.palette_length ?? this.palette?.length,
      paletteVersion: frame.palette_version ?? this.paletteVersion,
      paletteLoadedBytes: this.paletteLoadedBytes,
      spriteCount: Array.isArray(frame.sprites) ? frame.sprites.length : null,
      assetCount: this.assetIndex.size,
      eventCount: Array.isArray(frame.events) ? frame.events.length : null,
      firstSprite: Array.isArray(frame.sprites) && frame.sprites.length ? frame.sprites[0] : null,
      firstAsset: firstAsset ? {
        ...firstAsset,
        data: `[${firstAsset.data?.length ?? 0} bytes]`,
      } : null,
    };
  }

  addDiagnostic(type, payload) {
    this.diagnostics.push({
      at: new Date().toISOString(),
      type,
      payload,
    });
    if (this.diagnostics.length > 30) {
      this.diagnostics.shift();
    }
  }

  buildDiagnosticBundle(frameShape, diagnostics) {
    const bundle = {
      generatedAt: new Date().toISOString(),
      runtimeStatus: this.elements.runtimeMessage.textContent,
      adapterName: this.adapter.name,
      adapterSource: this.runtime.source,
      currentButtons: this.currentButtons,
      runtimeError: this.runtime.error ? {
        message: this.runtime.error.message || String(this.runtime.error),
        stack: this.runtime.error.stack || null,
      } : null,
      frameShape,
      diagnostics,
    };
    return JSON.stringify(bundle, null, 2);
  }
}

async function resolveRuntime() {
  const adapter = window.VentilastationRuntimeAdapter;
  if (adapter && typeof adapter.setButtons === "function" && typeof adapter.exportFrame === "function") {
    return { adapter, source: "preloaded" };
  }
  const createWasmAdapter = window.createVentilastationWasmAdapter;
  if (typeof createWasmAdapter === "function") {
    try {
      const wasmAdapter = await createWasmAdapter();
      if (wasmAdapter && typeof wasmAdapter.setButtons === "function" && typeof wasmAdapter.exportFrame === "function") {
        return { adapter: wasmAdapter, source: "wasm" };
      }
    } catch (error) {
      console.error("Failed to initialize Ventilastation WASM adapter", error);
      return { adapter: new MockRuntimeAdapter(), source: "mock", error };
    }
  }
  return { adapter: new MockRuntimeAdapter(), source: "mock" };
}

resolveRuntime().then((runtime) => {
  new BrowserHostApp(runtime).start();
});
