class WorkerBridge {
  constructor(worker) {
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
    this.worker = null;
    this.workspaceFiles = new Map();
    this.initializePromise = null;
    this.restartPromise = null;
    this.handleWorkerMessage = (event) => {
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
    };
    this.attachWorker(worker);
  }

  attachWorker(worker) {
    if (this.worker) {
      this.worker.removeEventListener("message", this.handleWorkerMessage);
    }
    this.worker = worker;
    this.worker.addEventListener("message", this.handleWorkerMessage);
  }

  rejectPending(reason) {
    for (const { reject } of this.pending.values()) {
      reject(new Error(reason));
    }
    this.pending.clear();
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
    const send = () => {
      const id = this.nextId++;
      const message = { id, type, ...payload };
      return new Promise((resolve, reject) => {
        this.pending.set(id, { resolve, reject });
        this.worker.postMessage(message);
      });
    };

    if (type !== "initialize" && this.initializePromise) {
      return this.initializePromise.then(() => send());
    }

    return send();
  }

  initialize(config = {}) {
    if (!this.initializePromise) {
      this.initializePromise = this.request("initialize", {
        config: {
          workspaceFiles: Array.from(this.workspaceFiles.values()),
          ...config,
        },
      }).catch((error) => {
        this.initializePromise = null;
        throw error;
      });
    }
    return this.initializePromise;
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

  getProxyRefInfo() {
    return this.request("get_proxy_ref_info");
  }

  listWorkspaceFiles(path = ".") {
    return this.request("list_workspace_files", { path });
  }

  readWorkspaceFile(path, encoding = "utf8") {
    return this.request("read_workspace_file", { path, encoding });
  }

  async writeWorkspaceFile(path, content, encoding = "utf8") {
    const entry = { path, content, encoding };
    this.workspaceFiles.set(path, entry);
    try {
      return await this.request("write_workspace_file", entry);
    } catch (error) {
      this.workspaceFiles.delete(path);
      throw error;
    }
  }

  async deleteWorkspaceFile(path) {
    const previousEntry = this.workspaceFiles.get(path) || null;
    this.workspaceFiles.delete(path);
    try {
      return await this.request("delete_workspace_file", { path });
    } catch (error) {
      if (previousEntry) {
        this.workspaceFiles.set(path, previousEntry);
      }
      throw error;
    }
  }

  async applyWorkspaceSnapshot(files = []) {
    this.workspaceFiles.clear();
    for (const file of files) {
      if (!file || typeof file.path !== "string") {
        continue;
      }
      this.workspaceFiles.set(file.path, {
        path: file.path,
        content: file.content,
        encoding: file.encoding || "utf8",
      });
    }
    return this.request("apply_workspace_snapshot", {
      files: Array.from(this.workspaceFiles.values()),
    });
  }

  async restartRuntime(options = {}) {
    if (this.restartPromise) {
      return this.restartPromise;
    }
    this.rejectPending("Worker restarted");
    if (this.worker) {
      this.worker.terminate();
    }
    const workerUrl = options.workerUrl || new URL(`./wasm-worker.js?v=${WORKER_SCRIPT_VERSION}`, import.meta.url).href;
    const worker = new Worker(workerUrl, { type: "module" });
    this.attachWorker(worker);
    this.initializePromise = null;
    this.restartPromise = this.initialize({
      autostartSlug: options.autostartSlug || null,
    }).finally(() => {
      this.restartPromise = null;
    });
    return this.restartPromise;
  }
}

const WORKER_SCRIPT_VERSION = "worker-debug-20260622T204800Z";

export async function createVentilastationWasmBridge(options = {}) {
  const workerUrl = options.workerUrl || new URL(`./wasm-worker.js?v=${WORKER_SCRIPT_VERSION}`, import.meta.url).href;
  const worker = new Worker(workerUrl, { type: "module" });
  const bridge = new WorkerBridge(worker);
  return bridge;
}

window.createVentilastationWasmBridge = createVentilastationWasmBridge;
