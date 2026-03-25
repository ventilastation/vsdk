import { loadMicroPython } from "./vendor/micropython/micropython.mjs";

const DEFAULT_CONFIG = {
  micropythonWasmUrl: "./vendor/micropython/micropython.wasm",
  runtimeBundleUrl: "./runtime-bundle.json",
  runtimeManifestUrl: "./runtime-manifest.json",
  fsRoot: "/apps/micropython",
  pystack: 32 * 1024,
  heapsize: 8 * 1024 * 1024,
};

const PY_BRIDGE_SOURCE = `
import json
import sys
import ubinascii

def _vs_serialize_binary(value, binary_mode):
    if binary_mode != "base64":
        return {"__bytes_meta__": len(value)}
    encoded = ubinascii.b2a_base64(bytes(value)).decode().strip()
    return {"__base64__": encoded}

def _vs_serialize(value, binary_mode):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (bytes, bytearray)):
        return _vs_serialize_binary(value, binary_mode)
    if isinstance(value, memoryview):
        return _vs_serialize_binary(value, binary_mode)
    if isinstance(value, (list, tuple, set)):
        return [_vs_serialize(item, binary_mode) for item in value]
    if isinstance(value, dict):
        return {str(key): _vs_serialize(item, binary_mode) for key, item in value.items()}
    return str(value)

def __vs_bridge_call(module_name, function_name, args_json):
    module = __import__(module_name, None, None, [function_name])
    function = getattr(module, function_name)
    args = json.loads(args_json)
    result = function(*args)
    binary_mode = "base64" if function_name == "export_frame" else "meta"
    return json.dumps(_vs_serialize(result, binary_mode))

def __vs_bridge_invoke(module_name, function_name, args_json):
    try:
        return json.dumps({"ok": True, "result": json.loads(__vs_bridge_call(module_name, function_name, args_json))})
    except Exception as error:
        error_type = sys.exc_info()[0]
        error_name = getattr(error_type, "__name__", str(error_type))
        return json.dumps({"ok": False, "error": error_name + ": " + str(error)})
`;

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

    await this.populateFilesystem();
    await this.mp.runPythonAsync(PY_BRIDGE_SOURCE);
    this.initialized = true;

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
    await this.mp.runPythonAsync(
      `__vs_bridge_result = __vs_bridge_invoke(${JSON.stringify(moduleName)}, ${JSON.stringify(functionName)}, ${JSON.stringify(JSON.stringify(args))})`
    );
    const jsonResult = this.mp.globals.get("__vs_bridge_result");
    this.mp.globals.delete("__vs_bridge_result");
    const bridgeResult = JSON.parse(jsonResult);
    if (!bridgeResult || typeof bridgeResult !== "object") {
      throw new Error("Invalid bridge response from MicroPython runtime");
    }
    if (!bridgeResult.ok) {
      throw new Error(bridgeResult.error || "Unknown MicroPython bridge error");
    }
    return reviveBytes(bridgeResult.result);
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
  const transferables = collectTransferables(result);
  self.postMessage({ id, ok: true, result }, transferables);
}

function failure(id, error) {
  const message = error instanceof Error ? error.message : String(error);
  self.postMessage({ id, ok: false, error: message });
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

    if (type === "exec") {
      const result = await runtime.exec(message.code);
      success(id, result);
      return;
    }

    if (type === "call") {
      const result = await runtime.call(message.moduleName, message.functionName, message.args || []);
      success(id, result);
      return;
    }

    throw new Error(`Unsupported worker message type: ${type}`);
  } catch (error) {
    failure(id, error);
  }
});
