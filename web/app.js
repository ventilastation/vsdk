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
const SCENE_STEP_MS = 30;
const MAX_CATCH_UP_STEPS = 6;
const MAX_TICK_BACKLOG_MS = SCENE_STEP_MS * MAX_CATCH_UP_STEPS;

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

class BrowserAudioHost {
  constructor() {
    this.enabled = false;
    this.musicPlayer = null;
    this.soundCache = new Map();
    this.pendingMusic = null;
  }

  enable() {
    this.enabled = true;
    if (this.pendingMusic !== null) {
      const name = this.pendingMusic;
      this.pendingMusic = null;
      this.playMusic(name);
    }
  }

  async resolveUrl(name) {
    const normalized = String(name).replace(/^\/+/, "");
    if (this.soundCache.has(normalized)) {
      return this.soundCache.get(normalized);
    }
    const candidates = [
      `../apps/sounds/${normalized}.mp3`,
      `../apps/sounds/${normalized}.mp3.wav`,
      `../apps/sounds/${normalized}.wav`,
      `../apps/sounds/${normalized}.ogg`,
    ];
    for (const candidate of candidates) {
      try {
        const response = await fetch(candidate, { method: "HEAD", credentials: "same-origin" });
        if (response.ok) {
          this.soundCache.set(normalized, candidate);
          return candidate;
        }
      } catch (_error) {
        // Try next candidate.
      }
    }
    this.soundCache.set(normalized, null);
    return null;
  }

  async playSound(name) {
    if (!this.enabled) {
      return;
    }
    const url = await this.resolveUrl(name);
    if (!url) {
      return;
    }
    const audio = new Audio(url);
    audio.preload = "auto";
    try {
      await audio.play();
    } catch (_error) {
      return;
    }
  }

  async playMusic(name) {
    if (name === "off") {
      this.stopMusic();
      return;
    }
    if (!this.enabled) {
      this.pendingMusic = name;
      return;
    }
    const url = await this.resolveUrl(name);
    if (!url) {
      return;
    }
    this.stopMusic();
    const audio = new Audio(url);
    audio.preload = "auto";
    this.musicPlayer = audio;
    try {
      await audio.play();
    } catch (_error) {
      if (this.musicPlayer === audio) {
        this.pendingMusic = name;
      }
    }
  }

  async playNotes(folder, notes) {
    if (!this.enabled) {
      return;
    }
    for (const note of notes.split(";")) {
      if (!note) {
        continue;
      }
      this.playSound(`${folder}/${note}`);
    }
  }

  stopMusic() {
    this.pendingMusic = null;
    if (!this.musicPlayer) {
      return;
    }
    this.musicPlayer.pause();
    this.musicPlayer.currentTime = 0;
    this.musicPlayer = null;
  }
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
        const p0x = positions[vertexOffset];
        const p0y = positions[vertexOffset + 1];
        const p1x = positions[vertexOffset + 2];
        const p1y = positions[vertexOffset + 3];
        const p2x = positions[vertexOffset + 4];
        const p2y = positions[vertexOffset + 5];
        const p3x = positions[vertexOffset + 10];
        const p3y = positions[vertexOffset + 11];

        const centerX = (p0x + p1x + p2x + p3x) * 0.25;
        const centerY = (p0y + p1y + p2y + p3y) * 0.25;
        const angle = Math.atan2(-(p1y - p0y), p1x - p0x);
        const radius = Math.hypot(centerX, centerY);
        const circumference = 2 * Math.PI * radius;
        const ledWidth = Math.max(0.35, (circumference / COLUMNS) * scale);
        let rowSpacing = 0;
        if (led + 1 < PIXELS) {
          const nextVertexOffset = (column * PIXELS + led + 1) * 12;
          const np0x = positions[nextVertexOffset];
          const np0y = positions[nextVertexOffset + 1];
          const np1x = positions[nextVertexOffset + 2];
          const np1y = positions[nextVertexOffset + 3];
          const np2x = positions[nextVertexOffset + 4];
          const np2y = positions[nextVertexOffset + 5];
          const np3x = positions[nextVertexOffset + 10];
          const np3y = positions[nextVertexOffset + 11];
          const nextCenterX = (np0x + np1x + np2x + np3x) * 0.25;
          const nextCenterY = (np0y + np1y + np2y + np3y) * 0.25;
          rowSpacing = Math.hypot(nextCenterX - centerX, nextCenterY - centerY) * scale;
        } else if (led > 0) {
          const prevVertexOffset = (column * PIXELS + led - 1) * 12;
          const pp0x = positions[prevVertexOffset];
          const pp0y = positions[prevVertexOffset + 1];
          const pp1x = positions[prevVertexOffset + 2];
          const pp1y = positions[prevVertexOffset + 3];
          const pp2x = positions[prevVertexOffset + 4];
          const pp2y = positions[prevVertexOffset + 5];
          const pp3x = positions[prevVertexOffset + 10];
          const pp3y = positions[prevVertexOffset + 11];
          const prevCenterX = (pp0x + pp1x + pp2x + pp3x) * 0.25;
          const prevCenterY = (pp0y + pp1y + pp2y + pp3y) * 0.25;
          rowSpacing = Math.hypot(centerX - prevCenterX, centerY - prevCenterY) * scale;
        }
        const ledHeight = Math.max(0.16, rowSpacing * (2 / 3));
        const drawX = width * 0.5 + centerX * scale;
        const drawY = height * 0.5 - centerY * scale;

        ctx.save();
        ctx.translate(drawX, drawY);
        ctx.rotate(angle);
        ctx.fillStyle = `rgba(${red}, ${green}, ${blue}, ${Math.max(alpha, 208) / 255})`;
        ctx.fillRect(-ledWidth * 0.5, -ledHeight * 0.5, ledWidth, ledHeight);
        ctx.restore();
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
    this.executionError = this.extractProminentError(runtime.error);
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
    this.audio = new BrowserAudioHost();
    this.force2dFallback = this.readForce2dPreference();
    this.inspectorOpen = this.readInspectorPreference();
    this.lastSceneTickAt = null;
    this.pollRequestId = null;
    this.pollingHalted = false;
    this.renderingPaused = false;
    this.canvas = document.querySelector("#frame-canvas-gl");
    this.fallbackCanvas = document.querySelector("#frame-canvas-2d");
    this.renderer = new LedRingWebGLRenderer(this.canvas);
    this.fallbackRenderer = new LedRingCanvasRenderer(this.fallbackCanvas, this.renderer.geometry);
    this.elements = {
      adapterName: document.querySelector("#adapter-name"),
      adapterSource: document.querySelector("#adapter-source"),
      frameCounter: document.querySelector("#frame-counter"),
      buttonMask: document.querySelector("#button-mask"),
      sceneErrorBanner: document.querySelector("#scene-error-banner"),
      sceneErrorTitle: document.querySelector("#scene-error-title"),
      sceneErrorMessage: document.querySelector("#scene-error-message"),
      sceneErrorDebugButton: document.querySelector("#scene-error-debug-button"),
      toggleRenderingButton: document.querySelector("#toggle-rendering-button"),
      runtimeBanner: document.querySelector("#runtime-banner"),
      runtimeMessage: document.querySelector("#runtime-message"),
      inspectorPanel: document.querySelector("#inspector-panel"),
      toggleInspectorButton: document.querySelector("#toggle-inspector-button"),
      copyDiagnostics: document.querySelector("#copy-diagnostics"),
      copyDiagnosticsButton: document.querySelector("#copy-diagnostics-button"),
      copyDiagnosticsStatus: document.querySelector("#copy-diagnostics-status"),
      runtimeSummary: document.querySelector("#runtime-summary"),
      force2dFallback: document.querySelector("#force-2d-fallback"),
    };
    this.copyStatusTimer = null;
    this.refreshCopyDiagnostics();
  }

  extractProminentError(error) {
    if (!error) {
      return null;
    }

    const sourceText = String(error.message || error.stack || error).trim();
    if (!sourceText) {
      return null;
    }

    const isSceneLifecycleError =
      sourceText.startsWith("Scene lifecycle error") ||
      /Scene\.(step|on_enter|on_exit) failed/u.test(sourceText);
    if (!isSceneLifecycleError) {
      return null;
    }

    return {
      title: "Scene lifecycle error",
      message: sourceText.replace(/^Scene lifecycle error\s*/u, "").trim(),
      isSceneLifecycleError: true,
    };
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
      if (event.command === "sound") {
        this.audio.playSound((event.args || []).join(" "));
        continue;
      }
      if (event.command === "music") {
        this.audio.playMusic((event.args || []).join(" "));
        continue;
      }
      if (event.command === "notes") {
        const folder = event.args?.[0] || "";
        const notes = event.args?.[1] || "";
        this.audio.playNotes(folder, notes);
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
    this.bindVisibility();
    this.bindCopyDiagnostics();
    this.bindDebugControls();
    this.bindRenderingToggle();
    this.bindInspectorToggle();
    this.bindSceneErrorControls();
    this.renderRenderingToggle();
    this.renderInspectorVisibility();
    this.renderCanvasVisibility();
    this.renderSceneError();
    this.schedulePoll(true);
  }

  schedulePoll(full = false) {
    if (this.pollRequestId !== null || this.pollingHalted || this.renderingPaused) {
      return;
    }
    this.pollRequestId = window.requestAnimationFrame(() => {
      this.pollRequestId = null;
      this.pollFrame(full);
    });
  }

  bindInput() {
    const enableAudio = () => this.audio.enable();
    window.addEventListener("pointerdown", enableAudio, { once: true });
    window.addEventListener("keydown", (event) => {
      this.audio.enable();
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

  bindVisibility() {
    document.addEventListener("visibilitychange", () => {
      const now = performance.now();
      if (document.hidden) {
        this.lastSceneTickAt = now;
        this.addDiagnostic("timing.pause", { reason: "hidden" });
        return;
      }
      this.lastSceneTickAt = now - SCENE_STEP_MS;
      this.addDiagnostic("timing.resume", { reason: "visible" });
      this.schedulePoll(false);
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
      this.renderCanvasVisibility();
      this.renderStatus();
      this.renderFrame();
    });
  }

  renderCanvasVisibility() {
    if (!this.canvas || !this.fallbackCanvas) {
      return;
    }
    const use2d = this.force2dFallback || !this.renderer.available;
    this.canvas.hidden = use2d;
    this.fallbackCanvas.hidden = !use2d;
  }

  bindInspectorToggle() {
    if (!this.elements.toggleInspectorButton || !this.elements.inspectorPanel) {
      return;
    }
    this.elements.toggleInspectorButton.addEventListener("click", () => {
      this.setInspectorOpen(!this.inspectorOpen);
    });
  }

  bindRenderingToggle() {
    if (!this.elements.toggleRenderingButton) {
      return;
    }
    this.elements.toggleRenderingButton.addEventListener("click", () => {
      this.setRenderingPaused(!this.renderingPaused);
    });
  }

  bindSceneErrorControls() {
    if (!this.elements.sceneErrorDebugButton) {
      return;
    }
    this.elements.sceneErrorDebugButton.addEventListener("click", () => {
      this.setInspectorOpen(true);
    });
  }

  setInspectorOpen(open) {
    this.inspectorOpen = Boolean(open);
    this.writeInspectorPreference(this.inspectorOpen);
    this.renderInspectorVisibility();
    if (this.inspectorOpen && this.lastFrame) {
      this.renderInspectors(this.lastFrame);
    }
  }

  setRenderingPaused(paused) {
    this.renderingPaused = Boolean(paused);
    if (this.renderingPaused) {
      if (this.pollRequestId !== null) {
        window.cancelAnimationFrame(this.pollRequestId);
        this.pollRequestId = null;
      }
      this.addDiagnostic("timing.pause", { reason: "manual" });
    } else {
      this.lastSceneTickAt = performance.now() - SCENE_STEP_MS;
      this.addDiagnostic("timing.resume", { reason: "manual" });
      this.schedulePoll(false);
    }
    this.renderRenderingToggle();
  }

  renderRenderingToggle() {
    const button = this.elements.toggleRenderingButton;
    if (!button) {
      return;
    }
    button.textContent = this.renderingPaused ? "Resume rendering" : "Stop rendering";
    button.setAttribute("aria-pressed", this.renderingPaused ? "true" : "false");
  }

  renderInspectorVisibility() {
    if (!this.elements.toggleInspectorButton || !this.elements.inspectorPanel) {
      return;
    }
    this.elements.inspectorPanel.hidden = !this.inspectorOpen;
    this.elements.toggleInspectorButton.textContent = this.inspectorOpen ? "Hide debug" : "Show debug";
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
      const now = performance.now();
      let stepsDue = 0;
      if (this.lastSceneTickAt === null) {
        this.lastSceneTickAt = now;
        stepsDue = 1;
      } else {
        const elapsed = now - this.lastSceneTickAt;
        if (elapsed > MAX_TICK_BACKLOG_MS) {
          this.addDiagnostic("timing.resync", {
            elapsedMs: Math.round(elapsed),
            maxBacklogMs: MAX_TICK_BACKLOG_MS,
          });
          this.lastSceneTickAt = now - SCENE_STEP_MS;
          stepsDue = 1;
        } else {
          stepsDue = Math.floor(elapsed / SCENE_STEP_MS);
        }
      }

      if (stepsDue > MAX_CATCH_UP_STEPS) {
        this.addDiagnostic("timing.catchup", {
          requestedSteps: stepsDue,
          appliedSteps: MAX_CATCH_UP_STEPS,
        });
        stepsDue = MAX_CATCH_UP_STEPS;
      }

      if (stepsDue > 0 && typeof this.adapter.tick === "function") {
        await Promise.resolve(this.adapter.tick(stepsDue));
        this.lastSceneTickAt += stepsDue * SCENE_STEP_MS;
      }

      if (!full && stepsDue === 0 && this.lastFrame) {
        this.renderFrame();
        return;
      }

      const frame = await Promise.resolve(this.adapter.exportFrame({ full }));
      if (!frame || typeof frame !== "object") {
        throw new Error(`Invalid frame payload: ${String(frame)}`);
      }
      if (this.usesEventStreamProtocol(frame)) {
        this.processFrameEvents(frame);
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
      this.runtime.error = null;
      if (this.executionError && this.runtime.source === "wasm") {
        this.executionError = null;
        this.pollingHalted = false;
        this.renderSceneError();
        this.renderRuntimeStatus();
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
      this.executionError = this.extractProminentError(error);
      this.runtime.error = this.executionError ? null : error;
      this.pollingHalted = Boolean(this.executionError?.isSceneLifecycleError);
      this.addDiagnostic("frame.error", {
        message: error.message || String(error),
        stack: error.stack || null,
      });
      this.renderSceneError();
      this.renderRuntimeStatus();
      console.error("Frame polling failed", error);
    } finally {
      if (!this.pollingHalted) {
        this.schedulePoll(false);
      }
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
    this.renderCanvasVisibility();
    const rendered = !this.force2dFallback && this.renderer.render(ledPixels);
    if ((!rendered || this.force2dFallback) && this.fallbackRenderer) {
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

    if (this.executionError) {
      runtimeBanner.classList.add("is-error");
      runtimeMessage.textContent = `${this.executionError.title}\n\n${this.executionError.message}`;
      return;
    }

    if (this.runtime.error) {
      runtimeBanner.classList.add("is-error");
      runtimeMessage.textContent = this.runtime.error.stack || this.runtime.error.message || String(this.runtime.error);
      return;
    }

    if (this.runtime.source === "wasm") {
      runtimeMessage.textContent = "Using real MicroPython WASM runtime.";
      return;
    }

    runtimeBanner.classList.add("is-warning");
    runtimeMessage.textContent = "Using mock runtime.";
  }

  renderSceneError() {
    const { sceneErrorBanner, sceneErrorTitle, sceneErrorMessage } = this.elements;
    if (!sceneErrorBanner || !sceneErrorTitle || !sceneErrorMessage) {
      return;
    }

    if (!this.executionError) {
      sceneErrorBanner.hidden = true;
      sceneErrorTitle.textContent = "Scene lifecycle error";
      sceneErrorMessage.textContent = "";
      return;
    }

    sceneErrorBanner.hidden = false;
    sceneErrorTitle.textContent = this.executionError.title;
    sceneErrorMessage.textContent = this.executionError.message;
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

    const frameShape = this.describeFrame(frame);
    this.lastFrameShape = frameShape;
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
      executionError: this.executionError ? {
        title: this.executionError.title,
        message: this.executionError.message,
        isSceneLifecycleError: this.executionError.isSceneLifecycleError,
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
