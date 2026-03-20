import { loadMicroPython } from "./vendor/micropython/micropython.mjs";

const DEFAULT_CONFIG = {
  micropythonWasmUrl: "./vendor/micropython/micropython.wasm",
  runtimeManifestUrl: "./runtime-manifest.json",
  fsRoot: "/apps/micropython",
  pystack: 8 * 1024,
  heapsize: 8 * 1024 * 1024,
};

const PY_BRIDGE_SOURCE = `
import json
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
`;

function dirname(path) {
  const normalized = path.replace(/\\/g, "/");
  const index = normalized.lastIndexOf("/");
  return index <= 0 ? "/" : normalized.slice(0, index);
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
    const response = await fetch(this.config.runtimeManifestUrl, { credentials: "same-origin" });
    if (!response.ok) {
      throw new Error(`Unable to load runtime manifest: ${response.status} ${response.url}`);
    }
    const manifest = await response.json();
    this.ensureDir("/");
    this.ensureDir(this.config.fsRoot);

    for (const relativePath of manifest.files) {
      const sourceUrl = new URL(`../${relativePath}`, self.location.href).href;
      const fileResponse = await fetch(sourceUrl, { credentials: "same-origin" });
      if (!fileResponse.ok) {
        throw new Error(`Unable to load runtime file: ${relativePath}`);
      }
      const bytes = new Uint8Array(await fileResponse.arrayBuffer());
      const targetPath = `/${relativePath}`;
      this.ensureDir(dirname(targetPath));
      this.mp.FS.writeFile(targetPath, bytes);
    }
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
      `__vs_bridge_result = __vs_bridge_call(${JSON.stringify(moduleName)}, ${JSON.stringify(functionName)}, ${JSON.stringify(JSON.stringify(args))})`
    );
    const jsonResult = this.mp.globals.get("__vs_bridge_result");
    this.mp.globals.delete("__vs_bridge_result");
    return reviveBytes(JSON.parse(jsonResult));
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

function success(id, result = null) {
  self.postMessage({ id, ok: true, result });
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
