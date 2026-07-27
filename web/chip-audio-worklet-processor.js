// AudioWorkletProcessor for the remote-workbench chip-audio pipeline
// (SMS/NES/MSX music+SFX resynthesized in-browser from register-write logs;
// see chip-audio-host.js). Runs on the real-time audio thread: no allocation
// on the hot path, no access to window/fetch/etc.
//
// chip-audio-host.js renders PCM on the main thread (from the WASM chip
// cores) and posts Int16 chunks here. This processor only buffers and plays
// them back at a fixed cadence, mirroring the same underrun/overrun policy
// already used by the desktop pyglet host's ring buffer
// (emulator/emu_audio.py's _ChipStream): silence on underrun, drop-oldest on
// overrun so latency stays bounded after a stall.

const RING_CAPACITY = 32000; // ~1 s of mono samples at the chips' 32 kHz rate

class ChipAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._ring = new Float32Array(RING_CAPACITY);
    this._writeIndex = 0;
    this._readIndex = 0;
    this._available = 0;
    this.port.onmessage = (event) => this._handleMessage(event.data);
  }

  _handleMessage(message) {
    if (!message) {
      return;
    }
    if (message.type === "clear") {
      this._writeIndex = 0;
      this._readIndex = 0;
      this._available = 0;
      return;
    }
    if (message.type === "push" && message.pcm instanceof Int16Array) {
      this._push(message.pcm);
    }
  }

  _push(int16Samples) {
    const n = int16Samples.length;
    if (n >= RING_CAPACITY) {
      // Pathological chunk larger than the whole ring: keep only its tail.
      this._writeIndex = 0;
      this._readIndex = 0;
      this._available = 0;
      for (let i = n - RING_CAPACITY; i < n; i++) {
        this._ring[this._writeIndex] = int16Samples[i] / 32768;
        this._writeIndex = (this._writeIndex + 1) % RING_CAPACITY;
      }
      this._available = RING_CAPACITY;
      return;
    }
    for (let i = 0; i < n; i++) {
      this._ring[this._writeIndex] = int16Samples[i] / 32768;
      this._writeIndex = (this._writeIndex + 1) % RING_CAPACITY;
    }
    this._available += n;
    if (this._available > RING_CAPACITY) {
      // Overrun: drop the oldest samples by advancing the read pointer.
      const overflow = this._available - RING_CAPACITY;
      this._readIndex = (this._readIndex + overflow) % RING_CAPACITY;
      this._available = RING_CAPACITY;
    }
  }

  process(_inputs, outputs) {
    const output = outputs[0];
    if (!output || !output.length) {
      return true;
    }
    const frames = output[0].length;
    for (let i = 0; i < frames; i++) {
      let sample = 0;
      if (this._available > 0) {
        sample = this._ring[this._readIndex];
        this._readIndex = (this._readIndex + 1) % RING_CAPACITY;
        this._available -= 1;
      }
      for (let channel = 0; channel < output.length; channel++) {
        output[channel][i] = sample;
      }
    }
    return true;
  }
}

registerProcessor("chip-audio", ChipAudioProcessor);
