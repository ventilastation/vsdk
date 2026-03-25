import { loadMicroPython } from "./vendor/micropython/micropython.mjs";

const DEFAULT_CONFIG = {
  micropythonWasmUrl: "./vendor/micropython/micropython.wasm",
  runtimeBundleUrl: "./runtime-bundle.json",
  runtimeManifestUrl: "./runtime-manifest.json",
  fsRoot: "/apps/micropython",
  pystack: 32 * 1024,
  heapsize: 8 * 1024 * 1024,
};
const SCENE_STEP_MS = 30;
const MAX_CATCH_UP_STEPS = 6;
const MAX_TICK_BACKLOG_MS = SCENE_STEP_MS * MAX_CATCH_UP_STEPS;

const PY_BOOTSTRAP_SOURCE = `
import sys
import uos
if "/apps/micropython" not in sys.path:
    sys.path.insert(0, "/apps/micropython")
uos.chdir("/apps/micropython")
import ventilastation.wasm_bridge as __vs_wasm_bridge
__vs_wasm_bridge.boot_runtime()
`;

const PY_BRIDGE_CALL_SOURCE = "__vs_bridge_result = __vs_wasm_bridge.invoke_from_globals()";
const PY_STEP_SOURCE = "__vs_wasm_bridge.step(__vs_step_count)";

function dirname(path) {
  const normalized = path.replace(/\\/g, "/");
  const index = normalized.lastIndexOf("/");
  return index <= 0 ? "/" : normalized.slice(0, index);
}

function getProjectRootCandidates() {
  const emulatorBaseUrl = new URL(".", self.location.href);
  return [
    emulatorBaseUrl,
    new URL("../", emulatorBaseUrl),
  ];
}

async function fetchFirstAvailable(paths) {
  const errors = [];
  for (const baseUrl of getProjectRootCandidates()) {
    for (const path of paths) {
      const url = new URL(path.replace(/^\/+/, ""), baseUrl);
      try {
        const response = await fetch(url, {
          credentials: "same-origin",
          cache: "no-store",
        });
        if (response.ok) {
          return response;
        }
        errors.push(`${response.status} ${url.href}`);
      } catch (error) {
        errors.push(`${url.href}: ${error.message || String(error)}`);
      }
    }
  }
  throw new Error(`Unable to load asset; tried: ${errors.join(", ")}`);
}

function reviveBytes(value) {
  if (Array.isArray(value)) {
    return value.map(reviveBytes);
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  if (Object.keys(value).length === 1 && typeof value.__base64__ === "string") {
    const decoded = atob(value.__base64__);
    const bytes = new Uint8Array(decoded.length);
    for (let i = 0; i < decoded.length; i += 1) {
      bytes[i] = decoded.charCodeAt(i);
    }
    return bytes;
  }
  if (Object.keys(value).length === 1 && typeof value.__bytes_meta__ === "number") {
    return { byteLength: value.__bytes_meta__ };
  }
  const revived = {};
  for (const [key, entry] of Object.entries(value)) {
    revived[key] = reviveBytes(entry);
  }
  return revived;
}

function decodeBase64(base64) {
  const decoded = atob(base64);
  const bytes = new Uint8Array(decoded.length);
  for (let index = 0; index < decoded.length; index += 1) {
    bytes[index] = decoded.charCodeAt(index);
  }
  return bytes;
}

const exportWorkerProfileTotals = {
  sampleCount: 0,
  totalCallMs: 0,
  totalCallMsMax: 0,
  runPythonAsyncMs: 0,
  runPythonAsyncMsMax: 0,
  globalsGetMs: 0,
  globalsGetMsMax: 0,
  jsonParseMs: 0,
  jsonParseMsMax: 0,
  reviveBytesMs: 0,
  reviveBytesMsMax: 0,
  transferCollectMs: 0,
  transferCollectMsMax: 0,
  postMessageMs: 0,
  postMessageMsMax: 0,
};

function normalizeWorkerCommandPayload(data) {
  if (data instanceof Uint8Array) {
    return data;
  }
  if (!data) {
    return null;
  }
  if (typeof data === "string") {
    return new TextEncoder().encode(data);
  }
  if (typeof data === "object" && typeof data[Symbol.iterator] === "function") {
    try {
      return Uint8Array.from(data);
    } catch (_error) {
      return null;
    }
  }
  return null;
}

function updateWorkerProfileMetric(sumKey, maxKey, value) {
  exportWorkerProfileTotals[sumKey] += value;
  if (value > exportWorkerProfileTotals[maxKey]) {
    exportWorkerProfileTotals[maxKey] = value;
  }
}

function getExportWorkerProfileSnapshot() {
  const sampleCount = exportWorkerProfileTotals.sampleCount;
  if (!sampleCount) {
    return null;
  }
  return {
    sampleCount,
    totalCallMs: exportWorkerProfileTotals.totalCallMs / sampleCount,
    totalCallMsMax: exportWorkerProfileTotals.totalCallMsMax,
    runPythonAsyncMs: exportWorkerProfileTotals.runPythonAsyncMs / sampleCount,
    runPythonAsyncMsMax: exportWorkerProfileTotals.runPythonAsyncMsMax,
    globalsGetMs: exportWorkerProfileTotals.globalsGetMs / sampleCount,
    globalsGetMsMax: exportWorkerProfileTotals.globalsGetMsMax,
    jsonParseMs: exportWorkerProfileTotals.jsonParseMs / sampleCount,
    jsonParseMsMax: exportWorkerProfileTotals.jsonParseMsMax,
    reviveBytesMs: exportWorkerProfileTotals.reviveBytesMs / sampleCount,
    reviveBytesMsMax: exportWorkerProfileTotals.reviveBytesMsMax,
    transferCollectMs: exportWorkerProfileTotals.transferCollectMs / sampleCount,
    transferCollectMsMax: exportWorkerProfileTotals.transferCollectMsMax,
    postMessageMs: exportWorkerProfileTotals.postMessageMs / sampleCount,
    postMessageMsMax: exportWorkerProfileTotals.postMessageMsMax,
  };
}

class MicroPythonRuntime {
  constructor(config) {
    this.config = config;
    this.initialized = false;
    this.mp = null;
  }

  async initialize() {
    if (this.initialized) {
      return {
        runtime: "micropython-webassembly",
        micropythonWasmUrl: this.config.micropythonWasmUrl,
        fsRoot: this.config.fsRoot,
      };
    }

    this.mp = await loadMicroPython({
      url: this.config.micropythonWasmUrl,
      pystack: this.config.pystack,
      heapsize: this.config.heapsize,
      stdin: () => null,
      stdout: (line) => console.log("[mp]", line),
      stderr: (line) => console.error("[mp]", line),
    });

    this.mp.registerJsModule("__vs_host", {
      get_buttons: () => workerHostState.buttons,
      is_running: () => workerHostState.running,
      consume_full_frame_request: () => {
        const shouldSendFullFrame = workerHostState.fullNextFrame;
        workerHostState.fullNextFrame = false;
        return shouldSendFullFrame;
      },
      post_command: (line, data = null) => {
        handleRuntimeCommand(String(line || ""), normalizeWorkerCommandPayload(data));
        return null;
      },
      post_runtime_error: (message, stack = null) => {
        postEvent("runtime_error", {
          error: {
            message: message || "Unknown runtime error",
            stack: stack || null,
          },
        });
        return null;
      },
    });

    await this.populateFilesystem();
    await this.mp.runPythonAsync(PY_BOOTSTRAP_SOURCE);
    this.initialized = true;
    await this.call("ventilastation.browser", "configure_worker_host", ["__vs_host"]);

    return {
      runtime: "micropython-webassembly",
      micropythonWasmUrl: this.config.micropythonWasmUrl,
      fsRoot: this.config.fsRoot,
    };
  }

  async populateFilesystem() {
    if (await this.populateFilesystemFromBundle()) {
      return;
    }

    const response = await fetch(this.config.runtimeManifestUrl, {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`Unable to load runtime manifest: ${response.status} ${response.url}`);
    }
    const manifest = await response.json();
    this.ensureDir("/");
    this.ensureDir(this.config.fsRoot);

    for (const relativePath of manifest.files) {
      const fileResponse = await fetchFirstAvailable([relativePath]);
      const bytes = new Uint8Array(await fileResponse.arrayBuffer());
      const targetPath = `/${relativePath}`;
      this.ensureDir(dirname(targetPath));
      this.mp.FS.writeFile(targetPath, bytes);
    }
  }

  async populateFilesystemFromBundle() {
    let response;
    try {
      response = await fetch(this.config.runtimeBundleUrl, {
        credentials: "same-origin",
        cache: "no-store",
      });
    } catch (_error) {
      return false;
    }
    if (!response.ok) {
      return false;
    }

    const bundle = await response.json();
    if (!bundle || !Array.isArray(bundle.files)) {
      throw new Error("Invalid runtime bundle format");
    }

    this.ensureDir("/");
    this.ensureDir(this.config.fsRoot);
    for (const entry of bundle.files) {
      if (!entry || typeof entry.path !== "string" || typeof entry.base64 !== "string") {
        throw new Error("Invalid runtime bundle entry");
      }
      const targetPath = `/${entry.path}`;
      this.ensureDir(dirname(targetPath));
      this.mp.FS.writeFile(targetPath, decodeBase64(entry.base64));
    }
    return true;
  }

  ensureDir(path) {
    const parts = path.split("/").filter(Boolean);
    let current = "";
    for (const part of parts) {
      current += `/${part}`;
      try {
        this.mp.FS.mkdir(current);
      } catch (_error) {
        // Directory already exists.
      }
    }
  }

  async exec(code) {
    this.assertInitialized();
    return this.mp.runPythonAsync(code);
  }

  async call(moduleName, functionName, args) {
    this.assertInitialized();
    const callStartedAt = functionName === "export_frame" ? performance.now() : 0;
    this.mp.globals.set("__vs_bridge_module_name", moduleName);
    this.mp.globals.set("__vs_bridge_function_name", functionName);
    this.mp.globals.set("__vs_bridge_args_json", JSON.stringify(args));
    await this.mp.runPythonAsync(
      PY_BRIDGE_CALL_SOURCE
    );
    const afterRunPythonAt = functionName === "export_frame" ? performance.now() : 0;
    const jsonResult = this.mp.globals.get("__vs_bridge_result");
    this.mp.globals.delete("__vs_bridge_result");
    this.mp.globals.delete("__vs_bridge_module_name");
    this.mp.globals.delete("__vs_bridge_function_name");
    this.mp.globals.delete("__vs_bridge_args_json");
    const afterGlobalsGetAt = functionName === "export_frame" ? performance.now() : 0;
    const bridgeResult = JSON.parse(jsonResult);
    const afterJsonParseAt = functionName === "export_frame" ? performance.now() : 0;
    if (!bridgeResult || typeof bridgeResult !== "object") {
      throw new Error("Invalid bridge response from MicroPython runtime");
    }
    if (!bridgeResult.ok) {
      throw new Error(bridgeResult.error || "Unknown MicroPython bridge error");
    }
    const result = reviveBytes(bridgeResult.result);
    if (functionName === "export_frame" && result && typeof result === "object") {
      const afterReviveAt = performance.now();
      exportWorkerProfileTotals.sampleCount += 1;
      updateWorkerProfileMetric("totalCallMs", "totalCallMsMax", afterReviveAt - callStartedAt);
      updateWorkerProfileMetric("runPythonAsyncMs", "runPythonAsyncMsMax", afterRunPythonAt - callStartedAt);
      updateWorkerProfileMetric("globalsGetMs", "globalsGetMsMax", afterGlobalsGetAt - afterRunPythonAt);
      updateWorkerProfileMetric("jsonParseMs", "jsonParseMsMax", afterJsonParseAt - afterGlobalsGetAt);
      updateWorkerProfileMetric("reviveBytesMs", "reviveBytesMsMax", afterReviveAt - afterJsonParseAt);
      result.worker_js_profile = getExportWorkerProfileSnapshot();
    }
    return result;
  }

  async step(count = 1) {
    this.assertInitialized();
    this.mp.globals.set("__vs_step_count", Number(count) || 0);
    try {
      return await this.mp.runPythonAsync(PY_STEP_SOURCE);
    } finally {
      this.mp.globals.delete("__vs_step_count");
    }
  }

  assertInitialized() {
    if (!this.initialized || !this.mp) {
      throw new Error("WASM worker runtime has not been initialized");
    }
  }
}

async function createRuntime(config = {}) {
  const merged = { ...DEFAULT_CONFIG, ...config };
  return new MicroPythonRuntime(merged);
}

let runtime = null;
let runtimeQueue = Promise.resolve();
const runtimeLoop = {
  running: false,
  timerId: null,
  lastSceneTickAt: null,
  fullNextFrame: true,
};
const workerHostState = {
  buttons: 0,
  running: false,
  fullNextFrame: true,
};
const streamedFrameState = {
  frame: 0,
  buttons: 0,
  column_offset: 0,
  gamma_mode: 1,
  palette_length: 0,
  palette_version: 0,
  palette_dirty: false,
  events: [],
  sprites: [],
};

function finalizeStreamedFrame() {
  const frame = {
    frame: streamedFrameState.frame,
    buttons: streamedFrameState.buttons,
    column_offset: streamedFrameState.column_offset,
    gamma_mode: streamedFrameState.gamma_mode,
    palette_length: streamedFrameState.palette_length,
    palette_version: streamedFrameState.palette_version,
    palette_dirty: streamedFrameState.palette_dirty,
    events: streamedFrameState.events.slice(),
    sprites: streamedFrameState.sprites.slice(),
  };
  streamedFrameState.palette_dirty = false;
  streamedFrameState.events = [];
  return frame;
}

function handleRuntimeCommand(line, payloadBytes) {
  const parts = String(line || "").trim().split(/\s+/u);
  const command = parts[0] || "";

  if (command === "palette") {
    streamedFrameState.palette_length = Number(parts[1] || 0);
    streamedFrameState.palette_version = Number(parts[2] || streamedFrameState.palette_version);
    streamedFrameState.palette_dirty = true;
    streamedFrameState.events.push({
      command,
      args: parts.slice(1),
      data: payloadBytes || new Uint8Array(0),
    });
    return;
  }

  if (command === "imagestrip") {
    streamedFrameState.events.push({
      command,
      args: parts.slice(1),
      data: payloadBytes || new Uint8Array(0),
    });
    return;
  }

  if (command === "sprites") {
    streamedFrameState.events.push({
      command,
      args: parts.slice(1),
      data: payloadBytes || new Uint8Array(0),
    });
    streamedFrameState.sprites = [];
    return;
  }

  if (command === "frame") {
    streamedFrameState.frame = Number(parts[1] || streamedFrameState.frame);
    streamedFrameState.buttons = Number(parts[2] || 0);
    streamedFrameState.gamma_mode = Number(parts[3] || 1);
    streamedFrameState.column_offset = Number(parts[4] || 0);
    streamedFrameState.palette_length = Number(parts[5] || streamedFrameState.palette_length);
    streamedFrameState.palette_version = Number(parts[6] || streamedFrameState.palette_version);
    streamedFrameState.palette_dirty = Boolean(Number(parts[7] || 0)) || streamedFrameState.palette_dirty;
    postEvent("frame", { frame: finalizeStreamedFrame() });
    return;
  }

  const event = {
    command,
    args: parts.slice(1),
  };
  if (payloadBytes instanceof Uint8Array && payloadBytes.length) {
    event.data = payloadBytes;
  }
  streamedFrameState.events.push(event);
}

function enqueueRuntimeWork(work) {
  const next = runtimeQueue.then(work, work);
  runtimeQueue = next.catch(() => {});
  return next;
}

function collectTransferables(value, transferables = [], seen = new Set()) {
  if (value instanceof Uint8Array) {
    const buffer = value.buffer;
    if (!seen.has(buffer)) {
      seen.add(buffer);
      transferables.push(buffer);
    }
    return transferables;
  }
  if (Array.isArray(value)) {
    for (const entry of value) {
      collectTransferables(entry, transferables, seen);
    }
    return transferables;
  }
  if (value && typeof value === "object") {
    for (const entry of Object.values(value)) {
      collectTransferables(entry, transferables, seen);
    }
  }
  return transferables;
}

function success(id, result = null) {
  const transferStartedAt = result && typeof result === "object" && result.worker_js_profile
    ? performance.now()
    : 0;
  const transferables = collectTransferables(result);
  if (result && typeof result === "object" && result.worker_js_profile) {
    const afterCollectAt = performance.now();
    updateWorkerProfileMetric("transferCollectMs", "transferCollectMsMax", afterCollectAt - transferStartedAt);
    result.worker_js_profile = getExportWorkerProfileSnapshot();
    const postStartedAt = performance.now();
    self.postMessage({ id, ok: true, result }, transferables);
    const afterPostAt = performance.now();
    updateWorkerProfileMetric("postMessageMs", "postMessageMsMax", afterPostAt - postStartedAt);
    return;
  }
  self.postMessage({ id, ok: true, result }, transferables);
}

function failure(id, error) {
  const message = error instanceof Error ? error.message : String(error);
  self.postMessage({ id, ok: false, error: message });
}

function postEvent(type, payload = {}) {
  self.postMessage({ type, ...payload });
}

function stopRuntimeLoop() {
  runtimeLoop.running = false;
  runtimeLoop.lastSceneTickAt = null;
  runtimeLoop.fullNextFrame = true;
  workerHostState.running = false;
  workerHostState.fullNextFrame = true;
  if (runtimeLoop.timerId !== null) {
    clearTimeout(runtimeLoop.timerId);
    runtimeLoop.timerId = null;
  }
}

function scheduleRuntimeLoop(delay = 0) {
  if (!runtimeLoop.running || runtimeLoop.timerId !== null) {
    return;
  }
  runtimeLoop.timerId = setTimeout(async () => {
    runtimeLoop.timerId = null;
    await runRuntimeLoopIteration();
  }, Math.max(0, delay));
}

async function runRuntimeLoopIteration() {
  if (!runtime || !runtimeLoop.running) {
    return;
  }

  try {
    const now = performance.now();
    let stepsDue = 0;
    if (runtimeLoop.lastSceneTickAt === null) {
      runtimeLoop.lastSceneTickAt = now;
      stepsDue = 1;
    } else {
      const elapsed = now - runtimeLoop.lastSceneTickAt;
      if (elapsed > MAX_TICK_BACKLOG_MS) {
        runtimeLoop.lastSceneTickAt = now - SCENE_STEP_MS;
        stepsDue = 1;
      } else {
        stepsDue = Math.floor(elapsed / SCENE_STEP_MS);
      }
    }

    if (stepsDue > MAX_CATCH_UP_STEPS) {
      stepsDue = MAX_CATCH_UP_STEPS;
    }

    if (stepsDue > 0) {
      await enqueueRuntimeWork(async () => runtime.step(stepsDue));
      runtimeLoop.lastSceneTickAt += stepsDue * SCENE_STEP_MS;
    }
  } catch (error) {
    stopRuntimeLoop();
    postEvent("runtime_error", {
      error: {
        message: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? (error.stack || null) : null,
      },
    });
    return;
  }

  if (!runtimeLoop.running) {
    return;
  }

  const now = performance.now();
  const nextDelay = runtimeLoop.lastSceneTickAt === null
    ? 0
    : Math.max(0, SCENE_STEP_MS - (now - runtimeLoop.lastSceneTickAt));
  scheduleRuntimeLoop(nextDelay);
}

self.addEventListener("message", async (event) => {
  const message = event.data;
  const { id, type } = message || {};

  if (!id || !type) {
    return;
  }

  try {
    if (type === "initialize") {
      if (!runtime) {
        runtime = await createRuntime(message.config);
      }
      const result = await runtime.initialize();
      success(id, result);
      return;
    }

    if (!runtime) {
      throw new Error("WASM worker not initialized");
    }

    if (type === "start_runtime_loop") {
      runtimeLoop.running = true;
      runtimeLoop.lastSceneTickAt = null;
      runtimeLoop.fullNextFrame = message.full !== false;
      workerHostState.running = true;
      workerHostState.fullNextFrame = message.full !== false;
      scheduleRuntimeLoop(0);
      success(id, { running: true });
      return;
    }

    if (type === "stop_runtime_loop") {
      stopRuntimeLoop();
      success(id, { running: false });
      return;
    }

    if (type === "request_full_frame") {
      runtimeLoop.fullNextFrame = true;
      workerHostState.fullNextFrame = true;
      success(id, { pending: true });
      return;
    }

    if (type === "set_buttons") {
      workerHostState.buttons = (message.bitmask || 0) & 0xFF;
      success(id, null);
      return;
    }

    if (type === "exec") {
      const result = await enqueueRuntimeWork(async () => runtime.exec(message.code));
      success(id, result);
      return;
    }

    if (type === "call") {
      const result = await enqueueRuntimeWork(async () => (
        runtime.call(message.moduleName, message.functionName, message.args || [])
      ));
      success(id, result);
      return;
    }

    throw new Error(`Unsupported worker message type: ${type}`);
  } catch (error) {
    failure(id, error);
  }
});
