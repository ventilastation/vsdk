"""Host playback for the Ventilastation emulator audio bridge.

The spinning board streams its console sound-chip register writes over serial
(see EMULATOR_AUDIO_PLAN.md). Here we replay those writes through the *same*
chip cores (compiled into chipsynth/libgenesissynth.*) to regenerate PCM, and
feed it to a pyglet streaming player.

Wire commands handled (dispatched from comms.py):
    achip <system>            -> start(system): reset synth + start player
    aframe <nbytes> <nsamples> -> frame(payload, nsamples): render + buffer
    astop                     -> request_stop(): tear down

Threading: aframe rendering happens on the comms receive thread (pure ctypes,
cheap) and the PCM is pushed into a lock-protected ring buffer. pyglet's audio
worker thread pulls from that buffer via _ChipStream.get_audio_data. Only the
pyglet Player lifecycle touches the main thread, driven by process() which the
engine calls each tick.
"""

import os
import ctypes
import platform
import threading

import pyglet
from pyglet.media import Source, Player
from pyglet.media.codecs import AudioData, AudioFormat

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chipsynth")

# Genesis NTSC audio rate (≈ 888 samples/frame × 60 fps). The device tells us
# the exact sample count per frame; small rate drift is absorbed by the buffer.
GENESIS_SAMPLE_RATE = 53267
SMS_SAMPLE_RATE = 32000


def _lib_ext():
    return "dylib" if platform.system() == "Darwin" else "so"


class _Synth:
    """ctypes wrapper around a chip-synth shared library."""

    def __init__(self, libname, reset_fn, render_fn):
        self.lib = ctypes.CDLL(os.path.join(_LIB_DIR, libname))
        self._reset = getattr(self.lib, reset_fn)
        self._reset.restype = None
        self._reset.argtypes = []
        self._render = getattr(self.lib, render_fn)
        self._render.restype = ctypes.c_int
        self._render.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                                 ctypes.POINTER(ctypes.c_int16)]
        self._out = (ctypes.c_int16 * 2048)()

    def reset(self):
        self._reset()

    def render(self, payload, nsamples):
        """Render one frame's register writes to int16 mono PCM bytes."""
        n = self._render(payload, len(payload), nsamples, self._out)
        if n <= 0:
            return b""
        return ctypes.string_at(self._out, n * 2)


# system token (bytes) -> factory building its synth wrapper.
_SYNTH_FACTORIES = {
    b"genesis": lambda: _Synth("libgenesissynth." + _lib_ext(),
                               "genesis_synth_reset", "genesis_synth_render"),
    b"sms-ntsc": lambda: _Synth("libsmssynth." + _lib_ext(),
                                "sms_synth_reset_ntsc", "sms_synth_render"),
    b"sms-pal": lambda: _Synth("libsmssynth." + _lib_ext(),
                               "sms_synth_reset_pal", "sms_synth_render"),
}

_SYSTEM_RATE = {
    b"genesis": GENESIS_SAMPLE_RATE,
    b"sms-ntsc": SMS_SAMPLE_RATE,
    b"sms-pal": SMS_SAMPLE_RATE,
}


class _ChipStream(Source):
    """A never-ending pyglet Source backed by a thread-safe PCM ring buffer.

    Returns silence on underrun (so the player never reaches end-of-stream) and
    drops the oldest audio if the producer outruns the consumer (so latency
    stays bounded after a stall).
    """

    def __init__(self, sample_rate):
        self.audio_format = AudioFormat(channels=1, sample_size=16, sample_rate=sample_rate)
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._max = sample_rate * 2  # ~1 s of 16-bit mono

    def push(self, pcm):
        if not pcm:
            return
        with self._lock:
            self._buf += pcm
            if len(self._buf) > self._max:
                # Keep only the most recent ~0.5 s to recover bounded latency.
                del self._buf[:-self._max // 2]

    def get_audio_data(self, num_bytes, compensation_time=0.0):
        num_bytes &= ~1  # whole 16-bit samples
        with self._lock:
            take = min(num_bytes, len(self._buf))
            data = bytes(self._buf[:take])
            del self._buf[:take]
        if take < num_bytes:
            data += b"\x00" * (num_bytes - take)  # silence on underrun
        duration = num_bytes / self.audio_format.bytes_per_second
        return AudioData(data, num_bytes, 0.0, duration, [])

    def is_precise(self):
        return True

    def seek(self, timestamp):
        pass


class EmuAudio:
    def __init__(self):
        self._synth = None
        self._stream = None
        self._player = None
        self._system = None
        self._want_start = False
        self._want_stop = False
        self._missing_warned = set()

    # --- called from the comms receive thread -------------------------------

    def start(self, system):
        """Begin a new emulator's audio (system is a bytes token, e.g. b'genesis')."""
        self.request_stop()
        factory = _SYNTH_FACTORIES.get(system)
        if not factory:
            if system not in self._missing_warned:
                self._missing_warned.add(system)
                print("emu_audio: no host synth for", system.decode("latin1", "replace"))
            return
        try:
            self._synth = factory()
        except OSError as e:
            if system not in self._missing_warned:
                self._missing_warned.add(system)
                print("emu_audio: could not load synth lib for",
                      system.decode("latin1", "replace"), "-", e,
                      "(build it: make -C chipsynth)")
            self._synth = None
            return
        self._synth.reset()
        self._stream = _ChipStream(_SYSTEM_RATE.get(system, GENESIS_SAMPLE_RATE))
        self._system = system
        self._want_start = True
        print("emu_audio: started", system.decode("latin1", "replace"))

    def frame(self, payload, nsamples):
        synth, stream = self._synth, self._stream
        if synth is None or stream is None:
            return
        stream.push(synth.render(payload, nsamples))

    def request_stop(self):
        if self._synth or self._stream or self._player:
            self._want_stop = True

    # --- called from the main (pyglet) thread each tick ---------------------

    def process(self):
        if self._want_stop:
            self._want_stop = False
            if self._player is not None:
                try:
                    self._player.delete()
                except Exception:
                    pass
            self._player = None
            self._stream = None
            self._synth = None
            self._system = None
            self._want_start = False
        if self._want_start and self._stream is not None:
            self._want_start = False
            self._player = Player()
            self._player.queue(self._stream)
            self._player.play()


# Singleton used by comms.py and the engine.
emu_audio = EmuAudio()
