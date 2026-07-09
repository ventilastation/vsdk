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
  computeLedFramePixelsFromRgb,
  createLedRingGeometry,
} = LedRenderCore;

const FORCE_2D_STORAGE_KEY = "ventilastation.force2dFallback";
const INVERT_GAMEPAD_Y_STORAGE_KEY = "ventilastation.invertGamepadY.v1";
const INSPECTOR_OPEN_STORAGE_KEY = "ventilastation.inspectorOpen.v2";
const EDITOR_OPEN_STORAGE_KEY = "ventilastation.editorOpen.v1";
const RENDERER_PROFILING_STORAGE_KEY = "ventilastation.rendererProfiling.v1";
const WEBGL_RESOLUTION_SCALE_STORAGE_KEY = "ventilastation.webglResolutionScale.v1";
const SCENE_STEP_MS = 30;
const MAX_CATCH_UP_STEPS = 6;
const MAX_TICK_BACKLOG_MS = SCENE_STEP_MS * MAX_CATCH_UP_STEPS;
const TOUCH_STICK_DEAD_ZONE = 0.26;
const GAMEPAD_AXIS_DEAD_ZONE = 0.35;
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
    detail: latest.renderer === "webgl" ? {
      resizeMs: summarizeProfileValues(samples, "rendererDetail.resizeMs"),
      clearMs: summarizeProfileValues(samples, "rendererDetail.clearMs"),
      colorExpandMs: summarizeProfileValues(samples, "rendererDetail.colorExpandMs"),
      uploadMs: summarizeProfileValues(samples, "rendererDetail.uploadMs"),
      drawSubmitMs: summarizeProfileValues(samples, "rendererDetail.drawSubmitMs"),
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

function fillRepeatedLedColors(ledPixels, repeatedWords, multiplier) {
  const ledWords = new Uint32Array(
    ledPixels.buffer,
    ledPixels.byteOffset,
    ledPixels.byteLength / 4
  );
  let dest = 0;
  for (let index = 0; index < ledWords.length; index += 1) {
    const word = ledWords[index];
    for (let repeat = 0; repeat < multiplier; repeat += 1) {
      repeatedWords[dest] = word;
      dest += 1;
    }
  }
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
  GAMEPAD_FACE_BUTTONS,
  GAMEPAD_DPAD_BUTTONS,
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
  fillRepeatedLedColors,
  resolveFirstAvailableUrl,
  decodeSpriteStateBuffer,
  decodeImageStripPayload,
};
