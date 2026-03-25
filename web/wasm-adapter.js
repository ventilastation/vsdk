class VentilastationWasmAdapter {
  constructor(bridge, options = {}) {
    this.bridge = bridge;
    this.name = options.name || "MicroPython WASM";
    this.bootModule = options.bootModule || "main";
    this.bootstrapped = false;
    this.usesWorkerFrameStream = true;
  }

  async init() {
    if (this.bootstrapped) {
      return this;
    }

    if (typeof this.bridge.initialize === "function") {
      await this.bridge.initialize();
    }

    this.bootstrapped = true;
    return this;
  }

  setButtons(bitmask) {
    if (typeof this.bridge.setButtons === "function") {
      return this.bridge.setButtons(bitmask);
    }
    return this.bridge.call("ventilastation.browser", "set_buttons", bitmask);
  }

  exportFrame({ full = false } = {}) {
    return this.bridge.call("ventilastation.browser", "export_frame", full);
  }

  tick(count = 1) {
    return this.bridge.call("ventilastation.browser", "tick", count);
  }

  exportStorage() {
    return this.bridge.call("ventilastation.browser", "export_storage");
  }

  importStorage(files) {
    return this.bridge.call("ventilastation.browser", "import_storage", files);
  }

  onFrame(listener) {
    return this.bridge.on("frame", (message) => listener(message.frame, message));
  }

  onRuntimeError(listener) {
    return this.bridge.on("runtime_error", (message) => listener(message.error || null));
  }

  startLoop({ full = true } = {}) {
    return this.bridge.startRuntimeLoop({ full });
  }

  stopLoop() {
    return this.bridge.stopRuntimeLoop();
  }

  requestFullFrame() {
    return this.bridge.requestFullFrame();
  }
}

function isBridge(candidate) {
  return candidate &&
    typeof candidate.exec === "function" &&
    typeof candidate.call === "function";
}

async function resolveBridge(options = {}) {
  if (isBridge(options.bridge)) {
    return options.bridge;
  }

  if (isBridge(window.VentilastationWasmBridge)) {
    return window.VentilastationWasmBridge;
  }

  if (typeof window.createVentilastationWasmBridge === "function") {
    const bridge = await window.createVentilastationWasmBridge(options);
    if (isBridge(bridge)) {
      return bridge;
    }
  }

  return null;
}

export async function createVentilastationWasmAdapter(options = {}) {
  if (window.VentilastationRuntimeAdapter && window.VentilastationRuntimeAdapter.__isVentilastationWasmAdapter) {
    return window.VentilastationRuntimeAdapter;
  }

  const bridge = await resolveBridge(options);
  if (!bridge) {
    throw new Error(
      "No Ventilastation WASM bridge available. " +
      "Provide window.VentilastationWasmBridge or window.createVentilastationWasmBridge()."
    );
  }

  const adapter = new VentilastationWasmAdapter(bridge, options);
  await adapter.init();
  adapter.__isVentilastationWasmAdapter = true;
  window.VentilastationRuntimeAdapter = adapter;
  return adapter;
}

window.createVentilastationWasmAdapter = createVentilastationWasmAdapter;
