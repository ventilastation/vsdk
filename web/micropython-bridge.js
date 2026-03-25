class WorkerBridge {
  constructor(worker) {
    this.worker = worker;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();

    this.worker.addEventListener("message", (event) => {
      const message = event.data;
      if (!message || typeof message !== "object") {
        return;
      }

      const { id, ok, result, error } = message;
      if (!this.pending.has(id)) {
        if (typeof message.type === "string") {
          this.emit(message.type, message);
        }
        return;
      }

      const { resolve, reject } = this.pending.get(id);
      this.pending.delete(id);

      if (ok) {
        resolve(result);
      } else {
        reject(new Error(error || "Unknown worker bridge error"));
      }
    });
  }

  on(type, listener) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type).add(listener);
    return () => {
      this.listeners.get(type)?.delete(listener);
    };
  }

  emit(type, message) {
    const listeners = this.listeners.get(type);
    if (!listeners || !listeners.size) {
      return;
    }
    for (const listener of listeners) {
      listener(message);
    }
  }

  request(type, payload = {}) {
    const id = this.nextId++;
    const message = { id, type, ...payload };
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.worker.postMessage(message);
    });
  }

  async initialize() {
    return this.request("initialize");
  }

  async exec(code) {
    return this.request("exec", { code });
  }

  call(moduleName, functionName, ...args) {
    return this.request("call", { moduleName, functionName, args });
  }

  setButtons(bitmask) {
    return this.request("set_buttons", { bitmask });
  }

  startRuntimeLoop(options = {}) {
    return this.request("start_runtime_loop", options);
  }

  stopRuntimeLoop() {
    return this.request("stop_runtime_loop");
  }

  requestFullFrame() {
    return this.request("request_full_frame");
  }
}

export async function createVentilastationWasmBridge(options = {}) {
  const workerUrl = options.workerUrl || new URL("./wasm-worker.js", import.meta.url).href;
  const worker = new Worker(workerUrl, { type: "module" });
  const bridge = new WorkerBridge(worker);
  return bridge;
}

window.createVentilastationWasmBridge = createVentilastationWasmBridge;
