// Shared constants, LED-core bindings and small helpers for the web emulator
// host (split out of app.js; see also led-ring-renderers.js and audio-host.js).

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

// The browser runtime mirrors input-protocol-v2.md.  The first seven bits of
// each joystick are directions plus A/B/X; Y, Start, and Back live here.
const INPUT_EXTRA = Object.freeze({
  JOY1_Y: 0x01,
  JOY2_Y: 0x02,
  JOY1_START: 0x04,
  JOY1_BACK: 0x08,
  JOY2_START: 0x10,
  JOY2_BACK: 0x20,
});

// Keyboard controls deliberately match the desktop emulator.  A key entry
// can target either joystick byte or the protocol-v2 extra byte.
const KEY_TO_INPUT = new Map([
  ["ArrowLeft", { joy1: BUTTONS.JOY_LEFT }],
  ["KeyA", { joy1: BUTTONS.JOY_LEFT }],
  ["ArrowRight", { joy1: BUTTONS.JOY_RIGHT }],
  ["KeyD", { joy1: BUTTONS.JOY_RIGHT }],
  ["ArrowUp", { joy1: BUTTONS.JOY_UP }],
  ["KeyW", { joy1: BUTTONS.JOY_UP }],
  ["ArrowDown", { joy1: BUTTONS.JOY_DOWN }],
  ["KeyS", { joy1: BUTTONS.JOY_DOWN }],
  ["Space", { joy1: BUTTONS.BUTTON_A }],
  ["KeyO", { joy1: BUTTONS.BUTTON_B }],
  ["KeyP", { joy1: BUTTONS.BUTTON_C }],
  ["KeyY", { extra: INPUT_EXTRA.JOY1_Y }],
  ["PageUp", { extra: INPUT_EXTRA.JOY1_START }],
  ["PageDown", { extra: INPUT_EXTRA.JOY1_BACK }],
  ["KeyH", { joy2: BUTTONS.JOY_LEFT }],
  ["KeyL", { joy2: BUTTONS.JOY_RIGHT }],
  ["KeyK", { joy2: BUTTONS.JOY_UP }],
  ["KeyJ", { joy2: BUTTONS.JOY_DOWN }],
  ["KeyZ", { joy2: BUTTONS.BUTTON_A }],
  ["KeyX", { joy2: BUTTONS.BUTTON_B }],
  ["KeyC", { joy2: BUTTONS.BUTTON_C }],
  ["KeyV", { extra: INPUT_EXTRA.JOY2_Y }],
  ["Home", { extra: INPUT_EXTRA.JOY2_START }],
  ["End", { extra: INPUT_EXTRA.JOY2_BACK }],
]);

// Retained for consumers that only use the original Joy1 byte.
const KEY_TO_BUTTON = new Map(
  [...KEY_TO_INPUT]
    .filter(([, input]) => input.joy1)
    .map(([code, input]) => [code, input.joy1]),
);

function keyboardInputForCode(code) {
  return KEY_TO_INPUT.get(code) || null;
}

function keyboardInputForCodes(codes) {
  const input = { joy1: 0, joy2: 0, extra: 0 };
  for (const code of codes) {
    const mapped = keyboardInputForCode(code);
    if (!mapped) {
      continue;
    }
    input.joy1 |= mapped.joy1 || 0;
    input.joy2 |= mapped.joy2 || 0;
    input.extra |= mapped.extra || 0;
  }
  return input;
}

const EXIT_KEY_CODES = new Set(["Escape"]);
const GAMEPAD_AXIS_DEAD_ZONE = 0.35;

// Standard Gamepad API button indices.  Browsers expose this stable layout
// for controllers whose `mapping` is "standard".
const GAMEPAD_BUTTONS = Object.freeze({
  A: 0,
  B: 1,
  X: 2,
  Y: 3,
  LEFT_SHOULDER: 4,
  RIGHT_SHOULDER: 5,
  LEFT_TRIGGER: 6,
  RIGHT_TRIGGER: 7,
  BACK: 8,
  START: 9,
  DPAD_UP: 12,
  DPAD_DOWN: 13,
  DPAD_LEFT: 14,
  DPAD_RIGHT: 15,
  GUIDE: 16,
});

function gamepadButtonPressed(gamepad, index) {
  const button = gamepad?.buttons[index];
  return Boolean(button?.pressed || Number(button?.value || 0) > 0.5);
}

function gamepadDirections(gamepad, axisOffset, includeDpad, invertY) {
  if (!gamepad) {
    return 0;
  }
  let buttons = 0;
  const axisX = gamepad.axes[axisOffset] || 0;
  const rawAxisY = gamepad.axes[axisOffset + 1] || 0;
  const axisY = invertY ? -rawAxisY : rawAxisY;
  if (axisX <= -GAMEPAD_AXIS_DEAD_ZONE ||
      (includeDpad && gamepadButtonPressed(gamepad, GAMEPAD_BUTTONS.DPAD_LEFT))) {
    buttons |= BUTTONS.JOY_LEFT;
  }
  if (axisX >= GAMEPAD_AXIS_DEAD_ZONE ||
      (includeDpad && gamepadButtonPressed(gamepad, GAMEPAD_BUTTONS.DPAD_RIGHT))) {
    buttons |= BUTTONS.JOY_RIGHT;
  }
  if (axisY <= -GAMEPAD_AXIS_DEAD_ZONE ||
      (includeDpad && gamepadButtonPressed(gamepad, GAMEPAD_BUTTONS.DPAD_UP))) {
    buttons |= BUTTONS.JOY_UP;
  }
  if (axisY >= GAMEPAD_AXIS_DEAD_ZONE ||
      (includeDpad && gamepadButtonPressed(gamepad, GAMEPAD_BUTTONS.DPAD_DOWN))) {
    buttons |= BUTTONS.JOY_DOWN;
  }
  return buttons;
}

function addControllerButtons(input, gamepad, player) {
  const joystickKey = player === 1 ? "joy1" : "joy2";
  const yBit = player === 1 ? INPUT_EXTRA.JOY1_Y : INPUT_EXTRA.JOY2_Y;
  const startBit = player === 1 ? INPUT_EXTRA.JOY1_START : INPUT_EXTRA.JOY2_START;
  const backBit = player === 1 ? INPUT_EXTRA.JOY1_BACK : INPUT_EXTRA.JOY2_BACK;
  if (gamepadButtonPressed(gamepad, GAMEPAD_BUTTONS.A)) {
    input[joystickKey] |= BUTTONS.BUTTON_A;
  }
  if (gamepadButtonPressed(gamepad, GAMEPAD_BUTTONS.B)) {
    input[joystickKey] |= BUTTONS.BUTTON_B;
  }
  if (gamepadButtonPressed(gamepad, GAMEPAD_BUTTONS.X)) {
    input[joystickKey] |= BUTTONS.BUTTON_C;
  }
  if (gamepadButtonPressed(gamepad, GAMEPAD_BUTTONS.Y)) {
    input.extra |= yBit;
  }
  if (gamepadButtonPressed(gamepad, GAMEPAD_BUTTONS.START)) {
    input.extra |= startBit;
  }
  if (gamepadButtonPressed(gamepad, GAMEPAD_BUTTONS.BACK)) {
    input.extra |= backBit;
  }
  if (gamepadButtonPressed(gamepad, GAMEPAD_BUTTONS.GUIDE)) {
    input.exit = true;
  }
}

// Map standard Gamepad API objects into Input Protocol v2.  This is kept
// pure so the browser mapping can be exercised without a DOM or WASM host.
function mapGamepadInput(primary, secondary = null, invertY = false) {
  const input = { joy1: 0, joy2: 0, extra: 0, exit: false };
  if (!primary) {
    return input;
  }

  input.joy1 = gamepadDirections(primary, 0, true, invertY);
  addControllerButtons(input, primary, 1);

  if (secondary) {
    // Controller 2 owns Joy2. Controller 1's right stick is ignored.
    input.joy2 = gamepadDirections(secondary, 0, true, invertY);
    addControllerButtons(input, secondary, 2);
    return input;
  }

  // A single controller exposes Joy2 through its right stick. Its spare
  // shoulder/trigger inputs provide Joy2 A/B/X/Y in that order.
  input.joy2 = gamepadDirections(primary, 2, false, invertY);
  if (gamepadButtonPressed(primary, GAMEPAD_BUTTONS.LEFT_SHOULDER)) {
    input.joy2 |= BUTTONS.BUTTON_A;
  }
  if (gamepadButtonPressed(primary, GAMEPAD_BUTTONS.LEFT_TRIGGER)) {
    input.joy2 |= BUTTONS.BUTTON_B;
  }
  if (gamepadButtonPressed(primary, GAMEPAD_BUTTONS.RIGHT_SHOULDER)) {
    input.joy2 |= BUTTONS.BUTTON_C;
  }
  if (gamepadButtonPressed(primary, GAMEPAD_BUTTONS.RIGHT_TRIGGER)) {
    input.extra |= INPUT_EXTRA.JOY2_Y;
  }
  return input;
}

const LedRenderCore = globalThis.VentilastationLedRenderCore;
if (!LedRenderCore) {
  throw new Error("Missing VentilastationLedRenderCore");
}

const {
  COLUMNS,
  PIXELS,
  computeLedFramePixels,
  computeLedFramePixelsFromRgb,
  createLedRingGeometry,
  decodeVs2SceneBuffer,
} = LedRenderCore;

const FORCE_2D_STORAGE_KEY = "ventilastation.force2dFallback";
const INVERT_GAMEPAD_Y_STORAGE_KEY = "ventilastation.invertGamepadY.v1";
const INSPECTOR_OPEN_STORAGE_KEY = "ventilastation.inspectorOpen.v2";
const EDITOR_OPEN_STORAGE_KEY = "ventilastation.editorOpen.v1";
const RENDERER_PROFILING_STORAGE_KEY = "ventilastation.rendererProfiling.v1";
const WEBGL_RESOLUTION_SCALE_STORAGE_KEY = "ventilastation.webglResolutionScale.v1";
const SCENE_RENDERER_STORAGE_KEY = "ventilastation.sceneRenderer.v1";
const SCENE_STEP_MS = 30;
const MAX_CATCH_UP_STEPS = 6;
const MAX_TICK_BACKLOG_MS = SCENE_STEP_MS * MAX_CATCH_UP_STEPS;
const TOUCH_STICK_DEAD_ZONE = 0.26;
const FPS_DISPLAY_INTERVAL_MS = 500;
const RENDER_PROFILE_SAMPLE_LIMIT = 60;
const MEMORY_SNAPSHOT_HISTORY_LIMIT = 20;
const TRACE_FLAGS = {
  auto_gc_frame: 32,
};
const WEBGL_RESOLUTION_SCALE_AUTO = "auto";
const DEFAULT_WEBGL_RESOLUTION_SCALE = 1;
const WEBGL_RESOLUTION_SCALES = [1, 0.75, 0.5, 0.375, 0.25];
const WEBGL_AUTO_SCALE_MIN_FPS = 20;
const WEBGL_AUTO_SCALE_WAIT_MS = 3000;
const MEMORY_FRAME_REFRESH_STORAGE_KEY = "ventilastation.memoryFrameRefresh.v1";
const EMULATOR_BASE_URL = new URL(".", window.location.href);
const PROJECT_ROOT_CANDIDATES = [
  EMULATOR_BASE_URL,
  new URL("../", EMULATOR_BASE_URL),
];

function decodePerspective(value) {
  return (value & 0x80) ? value - 0x100 : value;
}

function isEditableEventTarget(target) {
  if (!(target instanceof Element)) {
    return false;
  }
  if (target.closest("input, textarea, select, button, dialog, [contenteditable=\"true\"]")) {
    return true;
  }
  if (target.closest("#editor-panel-shell")) {
    return true;
  }
  return false;
}

function formatProfileMs(value) {
  return value === null || value === undefined ? "--" : `${value.toFixed(2)} ms`;
}

function formatBytes(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return "--";
  }
  const bytes = Number(value);
  if (Math.abs(bytes) < 1024) {
    return `${bytes} B`;
  }
  const units = ["KiB", "MiB", "GiB"];
  let amount = bytes;
  let unitIndex = -1;
  do {
    amount /= 1024;
    unitIndex += 1;
  } while (Math.abs(amount) >= 1024 && unitIndex < units.length - 1);
  return `${amount.toFixed(amount >= 10 ? 1 : 2)} ${units[unitIndex]}`;
}

function formatDeltaBytes(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return "--";
  }
  const numeric = Number(value);
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${formatBytes(numeric)}`;
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

function buildRenderProfileSnapshot(samples) {
  if (!Array.isArray(samples) || !samples.length) {
    return null;
  }
  const latest = samples[samples.length - 1];
  return {
    sampleCount: samples.length,
    renderer: latest.renderer,
    totalMs: summarizeProfileValues(samples, "totalMs"),
    computePixelsMs: summarizeProfileValues(samples, "computePixelsMs"),
    rendererMs: summarizeProfileValues(samples, "rendererMs"),
    detail: latest.renderer === "webgl" || latest.renderer === "scene-webgl" ? {
      resizeMs: summarizeProfileValues(samples, "rendererDetail.resizeMs"),
      clearMs: summarizeProfileValues(samples, "rendererDetail.clearMs"),
      colorExpandMs: summarizeProfileValues(samples, "rendererDetail.colorExpandMs"),
      uploadMs: summarizeProfileValues(samples, "rendererDetail.uploadMs"),
      drawSubmitMs: summarizeProfileValues(samples, "rendererDetail.drawSubmitMs"),
      sceneMs: summarizeProfileValues(samples, "rendererDetail.sceneMs"),
      scenePackMs: summarizeProfileValues(samples, "rendererDetail.sceneDetail.packMs"),
      sceneDynamicUploadMs: summarizeProfileValues(samples, "rendererDetail.sceneDetail.dynamicUploadMs"),
      sceneDrawSubmitMs: summarizeProfileValues(samples, "rendererDetail.sceneDetail.drawSubmitMs"),
      ringDrawSubmitMs: summarizeProfileValues(samples, "rendererDetail.ringDrawSubmitMs"),
      colorBytes: latest.rendererDetail?.colorBytes ?? null,
      vertexCount: latest.rendererDetail?.vertexCount ?? null,
      resolutionScale: latest.rendererDetail?.resolutionScale ?? null,
    } : {
      resizeMs: summarizeProfileValues(samples, "rendererDetail.resizeMs"),
      drawMs: summarizeProfileValues(samples, "rendererDetail.drawMs"),
      drawnLedCount: latest.rendererDetail?.drawnLedCount ?? null,
    },
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

export {
  BUTTONS,
  KEY_TO_BUTTON,
  KEY_TO_INPUT,
  keyboardInputForCode,
  keyboardInputForCodes,
  INPUT_EXTRA,
  EXIT_KEY_CODES,
  GAMEPAD_BUTTONS,
  mapGamepadInput,
  LedRenderCore,
  COLUMNS,
  PIXELS,
  computeLedFramePixels,
  computeLedFramePixelsFromRgb,
  createLedRingGeometry,
  FORCE_2D_STORAGE_KEY,
  INVERT_GAMEPAD_Y_STORAGE_KEY,
  INSPECTOR_OPEN_STORAGE_KEY,
  EDITOR_OPEN_STORAGE_KEY,
  RENDERER_PROFILING_STORAGE_KEY,
  WEBGL_RESOLUTION_SCALE_STORAGE_KEY,
  SCENE_RENDERER_STORAGE_KEY,
  SCENE_STEP_MS,
  MAX_CATCH_UP_STEPS,
  MAX_TICK_BACKLOG_MS,
  TOUCH_STICK_DEAD_ZONE,
  GAMEPAD_AXIS_DEAD_ZONE,
  FPS_DISPLAY_INTERVAL_MS,
  RENDER_PROFILE_SAMPLE_LIMIT,
  MEMORY_SNAPSHOT_HISTORY_LIMIT,
  TRACE_FLAGS,
  WEBGL_RESOLUTION_SCALE_AUTO,
  DEFAULT_WEBGL_RESOLUTION_SCALE,
  WEBGL_RESOLUTION_SCALES,
  WEBGL_AUTO_SCALE_MIN_FPS,
  WEBGL_AUTO_SCALE_WAIT_MS,
  MEMORY_FRAME_REFRESH_STORAGE_KEY,
  EMULATOR_BASE_URL,
  PROJECT_ROOT_CANDIDATES,
  decodePerspective,
  isEditableEventTarget,
  formatProfileMs,
  formatBytes,
  formatDeltaBytes,
  getNestedValue,
  summarizeProfileValues,
  buildRenderProfileSnapshot,
  resolveFirstAvailableUrl,
  decodeSpriteStateBuffer,
  decodeVs2SceneBuffer,
  decodeImageStripPayload,
};
