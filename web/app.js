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

const GAMEPAD_FACE_BUTTONS = new Map([
  [0, BUTTONS.BUTTON_A],
  [2, BUTTONS.BUTTON_B],
  [3, BUTTONS.BUTTON_C],
  [1, BUTTONS.BUTTON_D],
  [8, BUTTONS.BUTTON_D],
  [16, BUTTONS.BUTTON_D],
]);

const GAMEPAD_DPAD_BUTTONS = new Map([
  [14, BUTTONS.JOY_LEFT],
  [15, BUTTONS.JOY_RIGHT],
  [12, BUTTONS.JOY_UP],
  [13, BUTTONS.JOY_DOWN],
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
const INVERT_GAMEPAD_Y_STORAGE_KEY = "ventilastation.invertGamepadY.v1";
const INSPECTOR_OPEN_STORAGE_KEY = "ventilastation.inspectorOpen.v2";
const RENDERER_PROFILING_STORAGE_KEY = "ventilastation.rendererProfiling.v1";
const WEBGL_RESOLUTION_SCALE_STORAGE_KEY = "ventilastation.webglResolutionScale.v1";
const SCENE_STEP_MS = 30;
const MAX_CATCH_UP_STEPS = 6;
const MAX_TICK_BACKLOG_MS = SCENE_STEP_MS * MAX_CATCH_UP_STEPS;
const TOUCH_STICK_DEAD_ZONE = 0.26;
const GAMEPAD_AXIS_DEAD_ZONE = 0.35;
const FPS_DISPLAY_INTERVAL_MS = 500;
const RENDER_PROFILE_SAMPLE_LIMIT = 60;
const DEFAULT_WEBGL_RESOLUTION_SCALE = 1;
const WEBGL_RESOLUTION_SCALES = [1, 0.75, 0.5, 0.375, 0.25];
const WEBGL_AUTO_SCALE_MIN_FPS = 20;
const WEBGL_AUTO_SCALE_WAIT_MS = 3000;
const EMULATOR_BASE_URL = new URL(".", window.location.href);
const PROJECT_ROOT_CANDIDATES = [
  EMULATOR_BASE_URL,
  new URL("../", EMULATOR_BASE_URL),
];

function decodePerspective(value) {
  return (value & 0x80) ? value - 0x100 : value;
}

function formatProfileMs(value) {
  return value === null || value === undefined ? "--" : `${value.toFixed(2)} ms`;
}

function getNestedValue(source, path) {
  return path.split(".").reduce((value, key) => (value == null ? value : value[key]), source);
}

function summarizeProfileValues(samples, key) {
  const values = samples
    .map((sample) => getNestedValue(sample, key))
    .filter((value) => typeof value === "number" && Number.isFinite(value));
  if (!values.length) {
    return null;
  }
  const total = values.reduce((sum, value) => sum + value, 0);
  return {
    avg: total / values.length,
    max: Math.max(...values),
  };
}

async function resolveFirstAvailableUrl(paths, { method = "HEAD" } = {}) {
  for (const baseUrl of PROJECT_ROOT_CANDIDATES) {
    for (const path of paths) {
      const url = new URL(path.replace(/^\/+/, ""), baseUrl);
      try {
        const response = await fetch(url, { method, credentials: "same-origin" });
        if (response.ok) {
          return url.href;
        }
      } catch (_error) {
        // Try the next candidate URL.
      }
    }
  }
  return null;
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
      `apps/sounds/${normalized}.mp3`,
      `apps/sounds/${normalized}.mp3.wav`,
      `apps/sounds/${normalized}.wav`,
      `apps/sounds/${normalized}.ogg`,
    ];
    const resolved = await resolveFirstAvailableUrl(candidates, { method: "HEAD" });
    if (resolved) {
      this.soundCache.set(normalized, resolved);
      return resolved;
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
    this.lastProfile = null;
    this.resolutionScale = DEFAULT_WEBGL_RESOLUTION_SCALE;
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
    const scale = Number.isFinite(this.resolutionScale) && this.resolutionScale > 0
      ? this.resolutionScale
      : DEFAULT_WEBGL_RESOLUTION_SCALE;
    const width = Math.max(1, Math.round(this.canvas.clientWidth * dpr * scale));
    const height = Math.max(1, Math.round(this.canvas.clientHeight * dpr * scale));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    if (this.gl) {
      this.gl.viewport(0, 0, width, height);
    }
    return { width, height, scale };
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
      this.lastProfile = null;
      return false;
    }

    const startedAt = performance.now();
    const { width, height, scale } = this.resize();
    const afterResizeAt = performance.now();
    const gl = this.gl;
    this.clear();
    const afterClearAt = performance.now();
    gl.useProgram(this.program);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.positionBuffer);
    gl.enableVertexAttribArray(this.attribs.position);
    gl.vertexAttribPointer(this.attribs.position, 2, gl.FLOAT, false, 0, 0);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.texCoordBuffer);
    gl.enableVertexAttribArray(this.attribs.texCoord);
    gl.vertexAttribPointer(this.attribs.texCoord, 2, gl.FLOAT, false, 0, 0);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.colorBuffer);
    const colorBytes = repeatLedColors(ledPixels, 6);
    const afterColorExpandAt = performance.now();
    gl.bufferData(gl.ARRAY_BUFFER, colorBytes, gl.DYNAMIC_DRAW);
    const afterUploadAt = performance.now();
    gl.enableVertexAttribArray(this.attribs.color);
    gl.vertexAttribPointer(this.attribs.color, 4, gl.UNSIGNED_BYTE, true, 0, 0);

    gl.uniform2f(this.uniforms.resolution, width, height);
    gl.uniform2f(this.uniforms.center, width * 0.5, height * 0.5);
    gl.uniform1f(this.uniforms.scale, Math.min(width, height) / 200);
    gl.drawArrays(gl.TRIANGLES, 0, this.geometry.vertexCount);
    const finishedAt = performance.now();
    this.lastProfile = {
      resizeMs: afterResizeAt - startedAt,
      clearMs: afterClearAt - afterResizeAt,
      colorExpandMs: afterColorExpandAt - afterClearAt,
      uploadMs: afterUploadAt - afterColorExpandAt,
      drawSubmitMs: finishedAt - afterUploadAt,
      totalMs: finishedAt - startedAt,
      resolutionScale: scale,
      vertexCount: this.geometry.vertexCount,
      colorBytes: colorBytes.length,
    };
    return true;
  }
}

class LedRingCanvasRenderer {
  constructor(canvas, geometry) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.geometry = geometry;
    this.ledLayout = this.buildLedLayout();
    this.lastProfile = null;
  }

  buildLedLayout() {
    const positions = this.geometry.positions;
    const layout = new Array(COLUMNS * PIXELS);

    for (let column = 0; column < COLUMNS; column += 1) {
      for (let led = 0; led < PIXELS; led += 1) {
        const index = column * PIXELS + led;
        const vertexOffset = index * 12;
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
        const widthWorld = (2 * Math.PI * radius) / COLUMNS;

        let rowSpacingWorld = 0;
        if (led + 1 < PIXELS) {
          const nextIndex = index + 1;
          const nextVertexOffset = nextIndex * 12;
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
          rowSpacingWorld = Math.hypot(nextCenterX - centerX, nextCenterY - centerY);
        } else if (led > 0) {
          const prevIndex = index - 1;
          const prevVertexOffset = prevIndex * 12;
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
          rowSpacingWorld = Math.hypot(centerX - prevCenterX, centerY - prevCenterY);
        }

        layout[index] = {
          centerX,
          centerY,
          angle,
          widthWorld,
          heightWorld: rowSpacingWorld * (2 / 3),
        };
      }
    }

    return layout;
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
      this.lastProfile = null;
      return;
    }
    const startedAt = performance.now();
    const { width, height } = this.resize();
    const afterResizeAt = performance.now();
    const scale = Math.min(width, height) / 200;
    const ctx = this.ctx;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#05070b";
    ctx.fillRect(0, 0, width, height);

    let drawnLedCount = 0;

    for (let index = 0; index < this.ledLayout.length; index += 1) {
      const colorOffset = index * 4;
      const red = ledPixels[colorOffset];
      const green = ledPixels[colorOffset + 1];
      const blue = ledPixels[colorOffset + 2];
      const alpha = ledPixels[colorOffset + 3];
      if (!red && !green && !blue) {
        continue;
      }
      drawnLedCount += 1;

      const layout = this.ledLayout[index];
      const ledWidth = Math.max(0.35, layout.widthWorld * scale);
      const ledHeight = Math.max(0.16, layout.heightWorld * scale);
      const drawX = width * 0.5 + layout.centerX * scale;
      const drawY = height * 0.5 - layout.centerY * scale;

      ctx.save();
      ctx.translate(drawX, drawY);
      ctx.rotate(layout.angle);
      ctx.fillStyle = `rgba(${red}, ${green}, ${blue}, ${Math.max(alpha, 208) / 255})`;
      ctx.fillRect(-ledWidth * 0.5, -ledHeight * 0.5, ledWidth, ledHeight);
      ctx.restore();
    }

    const finishedAt = performance.now();
    this.lastProfile = {
      resizeMs: afterResizeAt - startedAt,
      drawMs: finishedAt - afterResizeAt,
      totalMs: finishedAt - startedAt,
      drawnLedCount,
    };
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
    this.keyboardButtons = 0;
    this.touchButtons = 0;
    this.gamepadButtons = 0;
    this.activeGamepadIndex = null;
    this.assetIndex = new Map();
    this.assetRenderCache = new Map();
    this.visibleStripSlots = [];
    this.palette = null;
    this.paletteVersion = 0;
    this.paletteLoadedBytes = 0;
    this.lastFrame = null;
    this.lastFrameShape = null;
    this.lastRenderedLedPixels = null;
    this.lastRenderAt = null;
    this.displayedFps = null;
    this.pendingMinFps = null;
    this.lastFpsDisplayUpdateAt = null;
    this.renderProfileSamples = [];
    this.executionProfileSamples = [];
    this.lastCanvasClientSize = null;
    this.lowFpsSinceAt = null;
    this.diagnostics = [];
    this.audio = new BrowserAudioHost();
    this.force2dFallback = this.readForce2dPreference();
    this.invertGamepadY = this.readInvertGamepadYPreference();
    this.rendererProfiling = this.readRendererProfilingPreference();
    this.webglResolutionScale = this.readWebglResolutionScalePreference();
    this.inspectorOpen = this.readInspectorPreference();
    this.lastSceneTickAt = null;
    this.pollRequestId = null;
    this.pollingHalted = false;
    this.renderingPaused = false;
    this.touchStickPointerId = null;
    this.canvas = document.querySelector("#frame-canvas-gl");
    this.fallbackCanvas = document.querySelector("#frame-canvas-2d");
    this.renderer = new LedRingWebGLRenderer(this.canvas);
    this.renderer.resolutionScale = this.webglResolutionScale;
    this.fallbackRenderer = new LedRingCanvasRenderer(this.fallbackCanvas, this.renderer.geometry);
    this.elements = {
      adapterName: document.querySelector("#adapter-name"),
      adapterSource: document.querySelector("#adapter-source"),
      frameCounter: document.querySelector("#frame-counter"),
      buttonMask: document.querySelector("#button-mask"),
      gamepadStatus: document.querySelector("#gamepad-status"),
      sceneErrorBanner: document.querySelector("#scene-error-banner"),
      sceneErrorTitle: document.querySelector("#scene-error-title"),
      sceneErrorMessage: document.querySelector("#scene-error-message"),
      sceneErrorDebugButton: document.querySelector("#scene-error-debug-button"),
      toggleRenderingButton: document.querySelector("#toggle-rendering-button"),
      touchStick: document.querySelector("#touch-stick"),
      touchStickKnob: document.querySelector("#touch-stick-knob"),
      touchButtons: Array.from(document.querySelectorAll("[data-touch-button]")),
      runtimeBanner: document.querySelector("#runtime-banner"),
      runtimeMessage: document.querySelector("#runtime-message"),
      inspectorPanel: document.querySelector("#inspector-panel"),
      toggleInspectorButton: document.querySelector("#toggle-inspector-button"),
      copyDiagnostics: document.querySelector("#copy-diagnostics"),
      copyDiagnosticsButton: document.querySelector("#copy-diagnostics-button"),
      copyDiagnosticsStatus: document.querySelector("#copy-diagnostics-status"),
      runtimeSummary: document.querySelector("#runtime-summary"),
      force2dFallback: document.querySelector("#force-2d-fallback"),
      invertGamepadY: document.querySelector("#invert-gamepad-y"),
      enableRendererProfiling: document.querySelector("#enable-renderer-profiling"),
      webglResolutionScale: document.querySelector("#webgl-resolution-scale"),
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
      this.keyboardButtons |= bit;
      this.syncButtons();
      this.addDiagnostic("input.keydown", { code: event.code, buttons: this.currentButtons });
      this.renderStatus();
    });

    window.addEventListener("keyup", (event) => {
      const bit = KEY_TO_BUTTON.get(event.code);
      if (!bit) {
        return;
      }
      event.preventDefault();
      this.keyboardButtons &= ~bit;
      this.syncButtons();
      this.addDiagnostic("input.keyup", { code: event.code, buttons: this.currentButtons });
      this.renderStatus();
    });

    window.addEventListener("blur", () => {
      this.keyboardButtons = 0;
      this.touchButtons = 0;
      this.gamepadButtons = 0;
      this.touchStickPointerId = null;
      this.syncButtons();
      this.addDiagnostic("input.blur", { buttons: 0 });
      this.renderStatus();
    });

    this.bindGamepadControls();
    this.bindTouchControls();
  }

  bindGamepadControls() {
    window.addEventListener("gamepadconnected", (event) => {
      const gamepad = event.gamepad;
      this.selectActiveGamepad();
      this.addDiagnostic("input.gamepad.connected", {
        index: gamepad.index,
        id: gamepad.id,
        mapping: gamepad.mapping || "unknown",
      });
      this.renderStatus();
    });

    window.addEventListener("gamepaddisconnected", (event) => {
      const gamepad = event.gamepad;
      const wasActive = gamepad.index === this.activeGamepadIndex;
      if (wasActive) {
        this.activeGamepadIndex = null;
        this.gamepadButtons = 0;
      }
      this.selectActiveGamepad();
      this.addDiagnostic("input.gamepad.disconnected", {
        index: gamepad.index,
        id: gamepad.id,
        wasActive,
      });
      this.syncButtons();
      this.renderStatus();
    });

    this.selectActiveGamepad();
  }

  getConnectedGamepads() {
    if (typeof navigator.getGamepads !== "function") {
      return [];
    }
    return Array.from(navigator.getGamepads()).filter(Boolean);
  }

  selectActiveGamepad() {
    const gamepads = this.getConnectedGamepads();
    const activeGamepad = gamepads.find((gamepad) => gamepad.index === this.activeGamepadIndex);
    if (activeGamepad) {
      return activeGamepad;
    }
    const nextGamepad = gamepads[0] || null;
    const previousIndex = this.activeGamepadIndex;
    this.activeGamepadIndex = nextGamepad ? nextGamepad.index : null;
    if (previousIndex !== this.activeGamepadIndex) {
      this.addDiagnostic("input.gamepad.active", {
        index: this.activeGamepadIndex,
        id: nextGamepad?.id || null,
      });
    }
    return nextGamepad;
  }

  readGamepadButtons() {
    const gamepad = this.selectActiveGamepad();
    if (!gamepad) {
      return 0;
    }

    let buttons = 0;

    for (const [index, bit] of GAMEPAD_FACE_BUTTONS) {
      if (gamepad.buttons[index]?.pressed) {
        buttons |= bit;
      }
    }

    for (const [index, bit] of GAMEPAD_DPAD_BUTTONS) {
      if (gamepad.buttons[index]?.pressed) {
        buttons |= bit;
      }
    }

    const axisX = gamepad.axes[0] || 0;
    const rawAxisY = gamepad.axes[1] || 0;
    const axisY = this.invertGamepadY ? -rawAxisY : rawAxisY;
    if (axisX <= -GAMEPAD_AXIS_DEAD_ZONE) {
      buttons |= BUTTONS.JOY_LEFT;
    }
    if (axisX >= GAMEPAD_AXIS_DEAD_ZONE) {
      buttons |= BUTTONS.JOY_RIGHT;
    }
    if (axisY <= -GAMEPAD_AXIS_DEAD_ZONE) {
      buttons |= BUTTONS.JOY_UP;
    }
    if (axisY >= GAMEPAD_AXIS_DEAD_ZONE) {
      buttons |= BUTTONS.JOY_DOWN;
    }

    return buttons & 0xff;
  }

  updateGamepadButtons() {
    const nextButtons = this.readGamepadButtons();
    if (nextButtons === this.gamepadButtons) {
      return false;
    }
    this.gamepadButtons = nextButtons;
    this.syncButtons();
    this.addDiagnostic("input.gamepad.state", {
      activeIndex: this.activeGamepadIndex,
      buttons: this.gamepadButtons,
    });
    return true;
  }

  bindTouchControls() {
    this.bindTouchStick();
    this.bindTouchButtons();
  }

  bindTouchStick() {
    const stick = this.elements.touchStick;
    if (!stick) {
      return;
    }
    stick.addEventListener("pointerdown", (event) => {
      if (event.pointerType === "mouse") {
        return;
      }
      event.preventDefault();
      this.audio.enable();
      this.touchStickPointerId = event.pointerId;
      stick.setPointerCapture(event.pointerId);
      this.updateTouchStickFromPoint(event.clientX, event.clientY);
    });
    stick.addEventListener("pointermove", (event) => {
      if (event.pointerId !== this.touchStickPointerId) {
        return;
      }
      event.preventDefault();
      this.updateTouchStickFromPoint(event.clientX, event.clientY);
    });
    const releaseStick = (event) => {
      if (event.pointerId !== this.touchStickPointerId) {
        return;
      }
      event.preventDefault();
      this.touchStickPointerId = null;
      this.setTouchDirection(0, 0, 0);
    };
    stick.addEventListener("pointerup", releaseStick);
    stick.addEventListener("pointercancel", releaseStick);
  }

  bindTouchButtons() {
    for (const button of this.elements.touchButtons) {
      const buttonName = button.dataset.touchButton;
      const bit = BUTTONS[buttonName];
      if (!bit) {
        continue;
      }
      const setPressed = (pressed) => {
        if (pressed) {
          this.touchButtons |= bit;
        } else {
          this.touchButtons &= ~bit;
        }
        this.syncButtons();
        this.renderStatus();
      };
      button.addEventListener("pointerdown", (event) => {
        if (event.pointerType === "mouse") {
          return;
        }
        event.preventDefault();
        this.audio.enable();
        button.setPointerCapture(event.pointerId);
        setPressed(true);
      });
      const release = (event) => {
        event.preventDefault();
        setPressed(false);
      };
      button.addEventListener("pointerup", release);
      button.addEventListener("pointercancel", release);
    }
  }

  updateTouchStickFromPoint(clientX, clientY) {
    const stick = this.elements.touchStick;
    if (!stick) {
      return;
    }
    const rect = stick.getBoundingClientRect();
    const centerX = rect.left + rect.width * 0.5;
    const centerY = rect.top + rect.height * 0.5;
    const dx = clientX - centerX;
    const dy = clientY - centerY;
    const radius = rect.width * 0.34;
    const distance = Math.hypot(dx, dy);
    const clampedDistance = Math.min(distance, radius);
    const angle = distance > 0 ? Math.atan2(dy, dx) : 0;
    const knobX = Math.cos(angle) * clampedDistance;
    const knobY = Math.sin(angle) * clampedDistance;
    this.setTouchDirection(knobX, knobY, radius);
  }

  setTouchDirection(knobX, knobY, radius) {
    const magnitude = radius > 0 ? Math.min(1, Math.hypot(knobX, knobY) / radius) : 0;
    let directionMask = 0;
    if (magnitude >= TOUCH_STICK_DEAD_ZONE) {
      const normalizedX = knobX / radius;
      const normalizedY = knobY / radius;
      if (normalizedX <= -0.35) {
        directionMask |= BUTTONS.JOY_LEFT;
      }
      if (normalizedX >= 0.35) {
        directionMask |= BUTTONS.JOY_RIGHT;
      }
      if (normalizedY <= -0.35) {
        directionMask |= BUTTONS.JOY_UP;
      }
      if (normalizedY >= 0.35) {
        directionMask |= BUTTONS.JOY_DOWN;
      }
    }
    this.touchButtons &= ~(BUTTONS.JOY_LEFT | BUTTONS.JOY_RIGHT | BUTTONS.JOY_UP | BUTTONS.JOY_DOWN);
    this.touchButtons |= directionMask;
    this.renderTouchStick(knobX, knobY);
    this.syncButtons();
    this.renderStatus();
  }

  renderTouchStick(x, y) {
    const knob = this.elements.touchStickKnob;
    if (!knob) {
      return;
    }
    knob.style.setProperty("--stick-x", `${Math.round(x)}px`);
    knob.style.setProperty("--stick-y", `${Math.round(y)}px`);
  }

  renderTouchButtons() {
    for (const button of this.elements.touchButtons) {
      const buttonName = button.dataset.touchButton;
      const bit = BUTTONS[buttonName];
      if (!bit) {
        continue;
      }
      button.classList.toggle("is-pressed", Boolean(this.currentButtons & bit));
    }
  }

  renderTouchStickFromButtons() {
    const stick = this.elements.touchStick;
    if (!stick) {
      return;
    }
    let x = 0;
    let y = 0;
    if (this.currentButtons & BUTTONS.JOY_LEFT) {
      x -= 1;
    }
    if (this.currentButtons & BUTTONS.JOY_RIGHT) {
      x += 1;
    }
    if (this.currentButtons & BUTTONS.JOY_UP) {
      y -= 1;
    }
    if (this.currentButtons & BUTTONS.JOY_DOWN) {
      y += 1;
    }
    if (!x && !y) {
      this.renderTouchStick(0, 0);
      return;
    }
    const magnitude = Math.hypot(x, y) || 1;
    const visualRadius = stick.getBoundingClientRect().width * 0.2;
    this.renderTouchStick(
      (x / magnitude) * visualRadius,
      (y / magnitude) * visualRadius,
    );
  }

  syncButtons() {
    this.currentButtons = (this.keyboardButtons | this.touchButtons | this.gamepadButtons) & 0xff;
    this.adapter.setButtons(this.currentButtons);
    this.renderTouchButtons();
    this.renderTouchStickFromButtons();
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
    if (this.elements.force2dFallback) {
      this.elements.force2dFallback.checked = this.force2dFallback;
      this.elements.force2dFallback.addEventListener("change", () => {
        this.force2dFallback = Boolean(this.elements.force2dFallback.checked);
        this.writeForce2dPreference(this.force2dFallback);
        this.renderProfileSamples = [];
        this.executionProfileSamples = [];
        this.addDiagnostic("renderer.mode", {
          forced2d: this.force2dFallback,
          webglAvailable: this.renderer.available,
        });
        this.renderCanvasVisibility();
        this.renderStatus();
        this.renderFrame();
      });
    }

    if (this.elements.invertGamepadY) {
      this.elements.invertGamepadY.checked = this.invertGamepadY;
      this.elements.invertGamepadY.addEventListener("change", () => {
        this.invertGamepadY = Boolean(this.elements.invertGamepadY.checked);
        this.writeInvertGamepadYPreference(this.invertGamepadY);
        this.addDiagnostic("input.gamepad.invert_y", {
          enabled: this.invertGamepadY,
        });
        if (this.updateGamepadButtons()) {
          this.renderStatus();
        }
      });
    }

    if (this.elements.enableRendererProfiling) {
      this.elements.enableRendererProfiling.checked = this.rendererProfiling;
      this.elements.enableRendererProfiling.addEventListener("change", () => {
        this.rendererProfiling = Boolean(this.elements.enableRendererProfiling.checked);
        this.writeRendererProfilingPreference(this.rendererProfiling);
        this.renderProfileSamples = [];
        this.executionProfileSamples = [];
        this.addDiagnostic("renderer.profiling", {
          enabled: this.rendererProfiling,
        });
        if (this.lastFrame) {
          this.renderInspectors(this.lastFrame);
        } else {
          this.refreshCopyDiagnostics();
        }
      });
    }

    if (this.elements.webglResolutionScale) {
      this.elements.webglResolutionScale.value = String(this.webglResolutionScale);
      this.elements.webglResolutionScale.addEventListener("change", () => {
        const nextScale = Number.parseFloat(this.elements.webglResolutionScale.value);
        const resolvedScale = Number.isFinite(nextScale) && nextScale > 0
          ? nextScale
          : DEFAULT_WEBGL_RESOLUTION_SCALE;
        this.applyWebglResolutionScale(resolvedScale, { reason: "manual", persist: true });
        if (this.lastFrame) {
          this.renderFrame();
        } else {
          this.renderStatus();
          this.refreshCopyDiagnostics();
        }
      });
    }
  }

  applyWebglResolutionScale(scale, { reason = "manual", persist = true } = {}) {
    const resolvedScale = WEBGL_RESOLUTION_SCALES.includes(scale)
      ? scale
      : DEFAULT_WEBGL_RESOLUTION_SCALE;
    this.webglResolutionScale = resolvedScale;
    this.renderer.resolutionScale = resolvedScale;
    this.lowFpsSinceAt = null;
    this.renderProfileSamples = [];
    this.executionProfileSamples = [];
    if (persist) {
      this.writeWebglResolutionScalePreference(resolvedScale);
    }
    if (this.elements.webglResolutionScale) {
      this.elements.webglResolutionScale.value = String(resolvedScale);
    }
    this.addDiagnostic("renderer.resolution_scale", {
      scale: resolvedScale,
      reason,
      persist,
    });
  }

  getNextLowerWebglResolutionScale() {
    const currentIndex = WEBGL_RESOLUTION_SCALES.indexOf(this.webglResolutionScale);
    if (currentIndex === -1) {
      return null;
    }
    return WEBGL_RESOLUTION_SCALES[currentIndex + 1] || null;
  }

  syncAdaptiveWebglResolution(now = performance.now()) {
    if (!this.canvas || this.force2dFallback || !this.renderer.available) {
      this.lowFpsSinceAt = null;
      return;
    }

    const clientWidth = this.canvas.clientWidth;
    const clientHeight = this.canvas.clientHeight;
    const currentSize = `${clientWidth}x${clientHeight}`;
    if (this.lastCanvasClientSize !== currentSize) {
      this.lastCanvasClientSize = currentSize;
      this.applyWebglResolutionScale(DEFAULT_WEBGL_RESOLUTION_SCALE, {
        reason: "display_change",
        persist: true,
      });
      return;
    }

    if (this.displayedFps === null || this.displayedFps >= WEBGL_AUTO_SCALE_MIN_FPS) {
      this.lowFpsSinceAt = null;
      return;
    }

    if (this.lowFpsSinceAt === null) {
      this.lowFpsSinceAt = now;
      return;
    }

    if (now - this.lowFpsSinceAt < WEBGL_AUTO_SCALE_WAIT_MS) {
      return;
    }

    const nextScale = this.getNextLowerWebglResolutionScale();
    if (!nextScale) {
      this.lowFpsSinceAt = null;
      return;
    }

    this.applyWebglResolutionScale(nextScale, {
      reason: "auto_low_fps",
      persist: true,
    });
    this.lowFpsSinceAt = now;
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
    button.textContent = this.renderingPaused ? "Resume emulator" : "Pause emulator";
    button.setAttribute("aria-pressed", this.renderingPaused ? "true" : "false");
  }

  renderInspectorVisibility() {
    if (!this.elements.toggleInspectorButton || !this.elements.inspectorPanel) {
      return;
    }
    this.elements.inspectorPanel.hidden = !this.inspectorOpen;
    this.elements.toggleInspectorButton.textContent = this.inspectorOpen ? "Hide options" : "Show options";
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

  readInvertGamepadYPreference() {
    try {
      return localStorage.getItem(INVERT_GAMEPAD_Y_STORAGE_KEY) === "1";
    } catch (_error) {
      return false;
    }
  }

  writeInvertGamepadYPreference(enabled) {
    try {
      if (enabled) {
        localStorage.setItem(INVERT_GAMEPAD_Y_STORAGE_KEY, "1");
      } else {
        localStorage.removeItem(INVERT_GAMEPAD_Y_STORAGE_KEY);
      }
    } catch (_error) {
      return;
    }
  }

  readRendererProfilingPreference() {
    try {
      return localStorage.getItem(RENDERER_PROFILING_STORAGE_KEY) === "1";
    } catch (_error) {
      return false;
    }
  }

  writeRendererProfilingPreference(enabled) {
    try {
      if (enabled) {
        localStorage.setItem(RENDERER_PROFILING_STORAGE_KEY, "1");
      } else {
        localStorage.removeItem(RENDERER_PROFILING_STORAGE_KEY);
      }
    } catch (_error) {
      return;
    }
  }

  readWebglResolutionScalePreference() {
    try {
      const rawValue = localStorage.getItem(WEBGL_RESOLUTION_SCALE_STORAGE_KEY);
      const parsed = Number.parseFloat(rawValue ?? "");
      return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_WEBGL_RESOLUTION_SCALE;
    } catch (_error) {
      return DEFAULT_WEBGL_RESOLUTION_SCALE;
    }
  }

  writeWebglResolutionScalePreference(scale) {
    try {
      if (scale === DEFAULT_WEBGL_RESOLUTION_SCALE) {
        localStorage.removeItem(WEBGL_RESOLUTION_SCALE_STORAGE_KEY);
      } else {
        localStorage.setItem(WEBGL_RESOLUTION_SCALE_STORAGE_KEY, String(scale));
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
      const pollStartedAt = this.rendererProfiling ? performance.now() : 0;
      const gamepadChanged = this.updateGamepadButtons();
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

      let tickMs = 0;
      if (stepsDue > 0 && typeof this.adapter.tick === "function") {
        const tickStartedAt = this.rendererProfiling ? performance.now() : 0;
        await Promise.resolve(this.adapter.tick(stepsDue));
        if (this.rendererProfiling) {
          tickMs = performance.now() - tickStartedAt;
        }
        this.lastSceneTickAt += stepsDue * SCENE_STEP_MS;
      }

      if (!full && stepsDue === 0 && this.lastFrame) {
        if (this.rendererProfiling) {
          this.recordExecutionProfile({
            mode: "render_only",
            stepsDue,
            tickMs: 0,
            exportFrameMs: 0,
            framePrepMs: 0,
            totalMs: performance.now() - pollStartedAt,
          });
        }
        this.renderFrame();
        if (gamepadChanged) {
          this.renderStatus();
        }
        return;
      }

      const exportStartedAt = this.rendererProfiling ? performance.now() : 0;
      const frame = await Promise.resolve(this.adapter.exportFrame({ full }));
      const exportFrameMs = this.rendererProfiling ? performance.now() - exportStartedAt : 0;
      if (!frame || typeof frame !== "object") {
        throw new Error(`Invalid frame payload: ${String(frame)}`);
      }
      const framePrepStartedAt = this.rendererProfiling ? performance.now() : 0;
      if (this.usesEventStreamProtocol(frame)) {
        this.processFrameEvents(frame);
      } else if (!Array.isArray(frame.sprites)) {
        frame.sprites = [];
      }
      if (
        frame.palette instanceof Uint8Array &&
        (
          !(this.palette instanceof Uint8Array) ||
          Boolean(frame.palette_dirty) ||
          Number(frame.palette_version || 0) !== this.paletteVersion
        )
      ) {
        this.palette = frame.palette;
        this.paletteVersion = Number(frame.palette_version || 0);
        this.paletteLoadedBytes = frame.palette.length;
        this.assetRenderCache.clear();
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
      if (this.rendererProfiling) {
        this.recordExecutionProfile({
          mode: full ? "full" : "frame",
          stepsDue,
          tickMs,
          exportFrameMs,
          framePrepMs: performance.now() - framePrepStartedAt,
          totalMs: performance.now() - pollStartedAt,
        });
      }
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

    this.updateDisplayedFps();
    this.syncAdaptiveWebglResolution();
    const startedAt = this.rendererProfiling ? performance.now() : 0;

    const hasPendingVisibleAsset = this.visibleStripSlots.some((slot) => {
      const asset = this.assetIndex.get(slot);
      return !asset || !(asset.data instanceof Uint8Array) || asset.loadedBytes < asset.dataLength;
    });
    const beforePixelsAt = this.rendererProfiling ? performance.now() : 0;
    const ledPixels = hasPendingVisibleAsset && this.lastRenderedLedPixels
      ? this.lastRenderedLedPixels
      : computeLedFramePixels(frame, this.assetIndex, this.palette);
    const afterPixelsAt = this.rendererProfiling ? performance.now() : 0;
    if (!hasPendingVisibleAsset) {
      this.lastRenderedLedPixels = ledPixels;
    }
    this.renderCanvasVisibility();
    const beforeRendererAt = this.rendererProfiling ? performance.now() : 0;
    const rendered = !this.force2dFallback && this.renderer.render(ledPixels);
    if ((!rendered || this.force2dFallback) && this.fallbackRenderer) {
      this.fallbackRenderer.render(ledPixels);
    }
    const afterRendererAt = this.rendererProfiling ? performance.now() : 0;
    if (this.rendererProfiling) {
      this.recordRenderProfile({
        renderer: rendered && !this.force2dFallback ? "webgl" : "canvas",
        totalMs: afterRendererAt - startedAt,
        computePixelsMs: afterPixelsAt - beforePixelsAt,
        rendererMs: afterRendererAt - beforeRendererAt,
        rendererDetail: rendered && !this.force2dFallback
          ? this.renderer.lastProfile
          : this.fallbackRenderer?.lastProfile || null,
      });
    }
    this.renderStatus();
    this.renderInspectors(frame);
  }

  updateDisplayedFps() {
    const now = performance.now();
    if (this.lastRenderAt !== null) {
      const elapsedMs = now - this.lastRenderAt;
      if (elapsedMs > 0) {
        const instantaneousFps = 1000 / elapsedMs;
        this.pendingMinFps = this.pendingMinFps === null
          ? instantaneousFps
          : Math.min(this.pendingMinFps, instantaneousFps);
      }
    }

    if (this.lastFpsDisplayUpdateAt === null) {
      this.lastFpsDisplayUpdateAt = now;
    }

    if (this.displayedFps === null && this.pendingMinFps !== null) {
      this.displayedFps = this.pendingMinFps;
      this.pendingMinFps = null;
      this.lastFpsDisplayUpdateAt = now;
    } else if (this.pendingMinFps !== null && now - this.lastFpsDisplayUpdateAt >= FPS_DISPLAY_INTERVAL_MS) {
      this.displayedFps = this.pendingMinFps;
      this.pendingMinFps = null;
      this.lastFpsDisplayUpdateAt = now;
    }

    if (now < this.lastFpsDisplayUpdateAt) {
      this.lastFpsDisplayUpdateAt = now;
      this.pendingMinFps = null;
    }

    this.lastRenderAt = now;
  }

  recordRenderProfile(sample) {
    this.renderProfileSamples.push({
      at: performance.now(),
      ...sample,
    });
    if (this.renderProfileSamples.length > RENDER_PROFILE_SAMPLE_LIMIT) {
      this.renderProfileSamples.shift();
    }
  }

  recordExecutionProfile(sample) {
    this.executionProfileSamples.push({
      at: performance.now(),
      ...sample,
    });
    if (this.executionProfileSamples.length > RENDER_PROFILE_SAMPLE_LIMIT) {
      this.executionProfileSamples.shift();
    }
  }

  getRenderProfileSnapshot() {
    if (!this.rendererProfiling || !this.renderProfileSamples.length) {
      return null;
    }
    const samples = this.renderProfileSamples;
    const latest = samples[samples.length - 1];
    return {
      sampleCount: samples.length,
      renderer: latest.renderer,
      totalMs: summarizeProfileValues(samples, "totalMs"),
      computePixelsMs: summarizeProfileValues(samples, "computePixelsMs"),
      rendererMs: summarizeProfileValues(samples, "rendererMs"),
      detail: latest.renderer === "webgl" ? {
        resizeMs: summarizeProfileValues(samples, "rendererDetail.resizeMs"),
        clearMs: summarizeProfileValues(samples, "rendererDetail.clearMs"),
        colorExpandMs: summarizeProfileValues(samples, "rendererDetail.colorExpandMs"),
        uploadMs: summarizeProfileValues(samples, "rendererDetail.uploadMs"),
        drawSubmitMs: summarizeProfileValues(samples, "rendererDetail.drawSubmitMs"),
        colorBytes: latest.rendererDetail?.colorBytes ?? null,
        vertexCount: latest.rendererDetail?.vertexCount ?? null,
      } : {
        resizeMs: summarizeProfileValues(samples, "rendererDetail.resizeMs"),
        drawMs: summarizeProfileValues(samples, "rendererDetail.drawMs"),
        drawnLedCount: latest.rendererDetail?.drawnLedCount ?? null,
      },
    };
  }

  getExecutionProfileSnapshot() {
    if (!this.rendererProfiling || !this.executionProfileSamples.length) {
      return null;
    }
    const samples = this.executionProfileSamples;
    const latest = samples[samples.length - 1];
    return {
      sampleCount: samples.length,
      mode: latest.mode,
      stepsDue: summarizeProfileValues(samples, "stepsDue"),
      tickMs: summarizeProfileValues(samples, "tickMs"),
      exportFrameMs: summarizeProfileValues(samples, "exportFrameMs"),
      framePrepMs: summarizeProfileValues(samples, "framePrepMs"),
      totalMs: summarizeProfileValues(samples, "totalMs"),
    };
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
    if (this.elements.gamepadStatus) {
      this.elements.gamepadStatus.textContent = this.activeGamepadIndex === null
        ? "Gamepad none"
        : `Gamepad ${this.activeGamepadIndex + 1}`;
    }
    if (this.elements.frameCounter) {
      this.elements.frameCounter.textContent = this.displayedFps === null
        ? "FPS --"
        : `FPS ${this.displayedFps.toFixed(1)}`;
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
    const profile = this.getRenderProfileSnapshot();
    const executionProfile = this.getExecutionProfileSnapshot();
    const summary = [
      ["Sprites", frame.sprites.length],
      ["Assets", this.assetIndex.size],
      ["Events", frame.events.length],
      ["Column Offset", frame.column_offset],
      ["Gamma", frame.gamma_mode],
      ["Buttons", `0x${frame.buttons.toString(16).padStart(2, "0")}`],
      ["Gamepad", this.activeGamepadIndex === null ? "None" : `Controller ${this.activeGamepadIndex + 1}`],
      ["Renderer", this.force2dFallback ? "2D fallback" : this.renderer.available ? "WebGL" : "2D fallback"],
      ["WebGL Scale", `${Math.round(this.webglResolutionScale * 100)}%`],
    ];
    if (profile) {
      summary.push(
        ["Profile Samples", profile.sampleCount],
        ["Frame Total", `${formatProfileMs(profile.totalMs?.avg)} avg / ${formatProfileMs(profile.totalMs?.max)} max`],
        ["Pixels", `${formatProfileMs(profile.computePixelsMs?.avg)} avg / ${formatProfileMs(profile.computePixelsMs?.max)} max`],
        ["Renderer Cost", `${formatProfileMs(profile.rendererMs?.avg)} avg / ${formatProfileMs(profile.rendererMs?.max)} max`],
      );
      if (profile.renderer === "webgl") {
        summary.push(
          ["Color Expand", `${formatProfileMs(profile.detail.colorExpandMs?.avg)} avg / ${formatProfileMs(profile.detail.colorExpandMs?.max)} max`],
          ["Upload", `${formatProfileMs(profile.detail.uploadMs?.avg)} avg / ${formatProfileMs(profile.detail.uploadMs?.max)} max`],
          ["Draw Submit", `${formatProfileMs(profile.detail.drawSubmitMs?.avg)} avg / ${formatProfileMs(profile.detail.drawSubmitMs?.max)} max`],
        );
      } else {
        summary.push([
          "Canvas Draw",
          `${formatProfileMs(profile.detail.drawMs?.avg)} avg / ${formatProfileMs(profile.detail.drawMs?.max)} max`,
        ]);
      }
    }
    if (executionProfile) {
      summary.push(
        ["Poll Samples", executionProfile.sampleCount],
        ["Poll Total", `${formatProfileMs(executionProfile.totalMs?.avg)} avg / ${formatProfileMs(executionProfile.totalMs?.max)} max`],
        ["Tick", `${formatProfileMs(executionProfile.tickMs?.avg)} avg / ${formatProfileMs(executionProfile.tickMs?.max)} max`],
        ["Export", `${formatProfileMs(executionProfile.exportFrameMs?.avg)} avg / ${formatProfileMs(executionProfile.exportFrameMs?.max)} max`],
        ["Frame Prep", `${formatProfileMs(executionProfile.framePrepMs?.avg)} avg / ${formatProfileMs(executionProfile.framePrepMs?.max)} max`],
        ["Steps Due", executionProfile.stepsDue ? `${executionProfile.stepsDue.avg.toFixed(2)} avg / ${executionProfile.stepsDue.max.toFixed(0)} max` : "--"],
      );
    }
    if (frame.python_profile && typeof frame.python_profile === "object") {
      summary.push(
        [
          "Py Export",
          `${formatProfileMs(frame.python_profile.browserExportMs)} avg / ${formatProfileMs(frame.python_profile.browserExportMsMax)} max`,
        ],
        [
          "Py Display",
          `${formatProfileMs(frame.python_profile.displayExportMs)} avg / ${formatProfileMs(frame.python_profile.displayExportMsMax)} max`,
        ],
        [
          "Py Sprites",
          `${formatProfileMs(frame.python_profile.spritesDecodeMs)} avg / ${formatProfileMs(frame.python_profile.spritesDecodeMsMax)} max`,
        ],
        [
          "Py Assets",
          `${formatProfileMs(frame.python_profile.assetsAssembleMs)} avg / ${formatProfileMs(frame.python_profile.assetsAssembleMsMax)} max`,
        ],
      );
    }

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
    const renderProfile = this.getRenderProfileSnapshot();
    const executionProfile = this.getExecutionProfileSnapshot();
    const dpr = window.devicePixelRatio || 1;
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
      viewport: {
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
        devicePixelRatio: dpr,
      },
      webglResolutionScale: this.webglResolutionScale,
      webglCanvas: this.canvas ? {
        clientWidth: this.canvas.clientWidth,
        clientHeight: this.canvas.clientHeight,
        width: this.canvas.width,
        height: this.canvas.height,
      } : null,
      fallbackCanvas: this.fallbackCanvas ? {
        clientWidth: this.fallbackCanvas.clientWidth,
        clientHeight: this.fallbackCanvas.clientHeight,
        width: this.fallbackCanvas.width,
        height: this.fallbackCanvas.height,
      } : null,
      pythonProfile: frame.python_profile ?? null,
      renderProfile,
      executionProfile,
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
    const exportedDiagnostics = this.rendererProfiling
      ? diagnostics.filter((entry) => (
        entry?.type === "renderer.profiling" ||
        entry?.type === "renderer.mode" ||
        entry?.type === "timing.resync" ||
        entry?.type === "timing.catchup" ||
        entry?.type === "frame.error"
      ))
      : diagnostics;
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
      diagnostics: exportedDiagnostics,
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
