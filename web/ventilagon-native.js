// The same original C sources and host adapter as emulator/ventilagon_native.py.
// The worker copies a frame from C memory once; no pixels enter MicroPython.
export async function loadVentilagon(moduleUrl, wasmUrl = null) {
  const { default: createVentilagon } = await import(moduleUrl);
  const options = wasmUrl ? { locateFile: () => wasmUrl } : {};
  const module = await createVentilagon(options);
  let active = false;
  return {
    enter(seed) {
      module._ventilagon_host_enter(Number(seed) >>> 0);
      active = true;
    },
    exit() {
      module._ventilagon_host_exit();
      active = false;
    },
    update(elapsedUs, buttons) {
      if (!active) throw new Error("Ventilagon is not active");
      module._ventilagon_host_update(Math.max(0, Math.min(250000, Number(elapsedUs))) >>> 0, Number(buttons) & 255);
      const ptr = module._ventilagon_host_frame();
      return module.HEAPU8.slice(ptr, ptr + 256 * 54 * 3);
    },
    isIdle() { return Boolean(module._ventilagon_host_is_idle()); },
    drainCommands(consume) {
      let ptr;
      while ((ptr = module._ventilagon_host_sending())) consume(module.UTF8ToString(ptr));
    },
  };
}
