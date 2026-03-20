class VentilastationWasmAdapter {
  constructor(bridge, options = {}) {
    this.bridge = bridge;
    this.name = options.name || "MicroPython WASM";
    this.bootModule = options.bootModule || "main";
    this.bootstrapped = false;
  }

  async init() {
    if (this.bootstrapped) {
      return this;
    }

    if (typeof this.bridge.initialize === "function") {
      await this.bridge.initialize();
    }

    await this.bridge.exec(`
import sys
import uos
if "/apps/micropython" not in sys.path:
    sys.path.insert(0, "/apps/micropython")
uos.chdir("/apps/micropython")
from ventilastation.director import configure_runtime
configure_runtime("browser")
import ventilastation.browser as __vs_browser
__vs_browser.boot_main()
`);

    this.bootstrapped = true;
    return this;
  }

  setButtons(bitmask) {
    this.bridge.call("ventilastation.browser", "set_buttons", bitmask);
  }

  exportFrame({ full = false } = {}) {
    return this.bridge.call("ventilastation.browser", "export_frame", full);
  }

  exportPaletteChunk({ offset = 0, chunkSize = 2048 } = {}) {
    return this.bridge.call("ventilastation.browser", "export_palette_chunk", offset, chunkSize);
  }

  tick(count = 1) {
    return this.bridge.call("ventilastation.browser", "tick", count);
  }

  exportAssets({ full = false, maxItems = null } = {}) {
    return this.bridge.call("ventilastation.browser", "export_assets", full, maxItems);
  }

  exportAssetChunk(slot, { offset = 0, chunkSize = 2048 } = {}) {
    return this.bridge.call("ventilastation.browser", "export_asset_chunk", slot, offset, chunkSize);
  }

  exportStorage() {
    return this.bridge.call("ventilastation.browser", "export_storage");
  }

  importStorage(files) {
    return this.bridge.call("ventilastation.browser", "import_storage", files);
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
