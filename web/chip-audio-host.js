// Browser chip-audio host: resynthesizes SMS/NES/MSX chip audio in the tab
// from the achip/aframe/astop register-write logs relayed over the
// remote-workbench WSS host-event channel (see remote_gateway.py and
// docs/internals/emulator-audio.md). This runs the *same* device/host
// chip-emulation C sources the desktop pyglet emulator uses
// (emulator/chipsynth/host_nes.c, host_sms.c, host_msx.c + the vendored
// chip cores), compiled to WebAssembly by tools/build-chipsynth-wasm.sh, so
// output matches real hardware. Playback is separate from the pre-rendered
// clip-trigger system in audio-host.js -- this is continuous synthesized
// PCM, not named sound/music assets.
//
// Wire shapes (apps/retro-go/components/retro-go/emu_audio_bridge.c):
//   achip <system> [<rom-name-len>]   -> args=[system], data=rom name bytes
//   aframe <wire-len> <nsamples>      -> args=[wireLen, nsamples], data=register log
//   astop

// Bump this whenever tools/build-chipsynth-wasm.sh output changes, same
// discipline as the other ?v= cache-busting tags in this directory (see
// docs/internals/deploying-web-emulator.md).
const CHIPSYNTH_VERSION = "20260727a";

const WASM_MODULES = {
  "nes-ntsc": { key: "nes", path: `./vendor/chipsynth/nes-synth.mjs?v=${CHIPSYNTH_VERSION}`, factory: "createNesSynth" },
  "nes-pal": { key: "nes", path: `./vendor/chipsynth/nes-synth.mjs?v=${CHIPSYNTH_VERSION}`, factory: "createNesSynth" },
  "sms-ntsc": { key: "sms", path: `./vendor/chipsynth/sms-synth.mjs?v=${CHIPSYNTH_VERSION}`, factory: "createSmsSynth" },
  "sms-pal": { key: "sms", path: `./vendor/chipsynth/sms-synth.mjs?v=${CHIPSYNTH_VERSION}`, factory: "createSmsSynth" },
  msx: { key: "msx", path: `./vendor/chipsynth/msx-synth.mjs?v=${CHIPSYNTH_VERSION}`, factory: "createMsxSynth" },
};

const RESET_FUNCTIONS = {
  "nes-ntsc": "nes_synth_reset_ntsc",
  "nes-pal": "nes_synth_reset_pal",
  "sms-ntsc": "sms_synth_reset_ntsc",
  "sms-pal": "sms_synth_reset_pal",
  msx: "msx_synth_reset",
};

const RENDER_FUNCTIONS = {
  nes: "nes_synth_render",
  sms: "sms_synth_render",
  msx: "msx_synth_render",
};

// Matches the shared MAXSAMP bound in host_nes.c/host_sms.c/host_msx.c --
// the C side clamps to this regardless of what nsamples the wire sends.
const MAX_SAMPLES = 2048;
const OUTPUT_BYTES = MAX_SAMPLES * 2; // int16
const CHIP_SAMPLE_RATE = 32000;

class ChipAudioHost {
  constructor() {
    this.audioContext = null;
    this.workletNode = null;
    this._readyPromise = null;
    this._moduleCache = new Map(); // synth key -> { Module, outPtr, render }
    this._currentSystem = null;
    this._current = null; // { Module, outPtr, render } for the active system
    this._missingWarned = new Set();
  }

  async _ensureAudioGraph() {
    if (!this._readyPromise) {
      this._readyPromise = (async () => {
        this.audioContext = new AudioContext({ sampleRate: CHIP_SAMPLE_RATE });
        await this.audioContext.audioWorklet.addModule(
          new URL(`./chip-audio-worklet-processor.js?v=${CHIPSYNTH_VERSION}`, import.meta.url),
        );
        this.workletNode = new AudioWorkletNode(this.audioContext, "chip-audio", {
          numberOfInputs: 0,
          numberOfOutputs: 1,
          outputChannelCount: [2],
        });
        this.workletNode.connect(this.audioContext.destination);
      })();
    }
    return this._readyPromise;
  }

  // Must be called from a user-gesture handler (browser autoplay policy).
  async resume() {
    await this._ensureAudioGraph();
    if (this.audioContext.state !== "running") {
      await this.audioContext.resume();
    }
  }

  async _loadModule(key, path, factoryName) {
    if (this._moduleCache.has(key)) {
      return this._moduleCache.get(key);
    }
    const url = new URL(path, import.meta.url);
    const imported = await import(url.href);
    const factory = imported[factoryName] || imported.default;
    const Module = await factory();
    const outPtr = Module._malloc(OUTPUT_BYTES);
    const entry = { Module, outPtr, renders: new Map() };
    this._moduleCache.set(key, entry);
    return entry;
  }

  _renderFn(entry, key) {
    const name = RENDER_FUNCTIONS[key];
    let render = entry.renders.get(name);
    if (!render) {
      render = entry.Module.cwrap(name, "number", ["array", "number", "number", "number"]);
      entry.renders.set(name, render);
    }
    return render;
  }

  // achip: begin a new emulator's audio. `system` is one of the tokens in
  // WASM_MODULES (e.g. "nes-ntsc"); romNameBytes is the ROM filename the
  // board sent (only meaningful for NES DMC fidelity, which needs real
  // PRG-ROM bytes the browser bundle doesn't ship -- DMC just stays silent
  // here, same graceful fallback as the desktop host when it can't find a
  // ROM file either).
  async begin(system, _romNameBytes) {
    await this._ensureAudioGraph();
    this.workletNode.port.postMessage({ type: "clear" });
    this._currentSystem = system;
    this._current = null;

    const spec = WASM_MODULES[system];
    if (!spec) {
      if (!this._missingWarned.has(system)) {
        this._missingWarned.add(system);
        console.warn("chip-audio: no browser synth for", system);
      }
      return;
    }

    let entry;
    try {
      entry = await this._loadModule(spec.key, spec.path, spec.factory);
    } catch (error) {
      if (!this._missingWarned.has(system)) {
        this._missingWarned.add(system);
        console.warn("chip-audio: could not load synth for", system, error);
      }
      return;
    }

    if (this._currentSystem !== system) {
      // A newer achip arrived while this module was loading; don't clobber it.
      return;
    }

    entry.Module.cwrap(RESET_FUNCTIONS[system], null, [])();
    this._current = { Module: entry.Module, outPtr: entry.outPtr, render: this._renderFn(entry, spec.key) };
  }

  // aframe: render one video frame's worth of register writes to PCM and
  // hand it to the AudioWorklet for playback.
  frame(payloadBytes, nsamples) {
    if (!this._current || !this.workletNode) {
      return;
    }
    const n = Math.max(0, Math.min(nsamples | 0, MAX_SAMPLES));
    if (n === 0) {
      return;
    }
    const payload = payloadBytes instanceof Uint8Array ? payloadBytes : new Uint8Array(0);
    const { Module, outPtr, render } = this._current;
    const rendered = render(payload, payload.length, n, outPtr);
    if (rendered <= 0) {
      return;
    }
    // Copy out of WASM heap immediately: ALLOW_MEMORY_GROWTH can detach this
    // buffer view on a later allocation, and postMessage needs to own the
    // ArrayBuffer it transfers.
    const pcm = new Int16Array(Module.HEAP16.buffer, outPtr, rendered).slice();
    this.workletNode.port.postMessage({ type: "push", pcm }, [pcm.buffer]);
  }

  // astop: emulator exited, let the worklet drain to silence.
  stop() {
    this._currentSystem = null;
    this._current = null;
    this.workletNode?.port.postMessage({ type: "clear" });
  }
}

export { ChipAudioHost };
