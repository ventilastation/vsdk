"""Host playback for the Ventilastation emulator audio bridge.

The spinning board streams its console sound-chip register writes over serial
(see docs/internals/emulator-audio.md). Here we replay those writes through the *same*
chip cores (compiled into chipsynth/libgenesissynth.*) to regenerate PCM, and
feed it to a pyglet streaming player.

Wire commands handled (dispatched from comms.py):
    achip <system> [<nbytes>] -> start(system, rom_name): reset synth (+ load
                                  ROM for cores that need real ROM bytes, e.g.
                                  NES DMC) + start player
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
import zipfile

import pyglet
from pyglet.media import Source, Player
from pyglet.media.codecs import AudioData, AudioFormat

_EMULATOR_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_EMULATOR_DIR, "chipsynth")

# Same roms/ tree the board's own ROM files were synced from (see
# apps/retro-go/roms/README.md) -- cores that need real ROM bytes for
# fidelity (e.g. NES DMC sample playback) look the ROM up here by filename.
_ROMS_ROOT = os.path.join(_EMULATOR_DIR, "..", "apps", "retro-go", "roms")

# Genesis NTSC audio rate (≈ 888 samples/frame × 60 fps). The device tells us
# the exact sample count per frame; small rate drift is absorbed by the buffer.
GENESIS_SAMPLE_RATE = 53267
SMS_SAMPLE_RATE = 32000
NES_SAMPLE_RATE = 32000
GB_SAMPLE_RATE = 32000
MSX_SAMPLE_RATE = 32000


def _lib_ext():
    return "dylib" if platform.system() == "Darwin" else "so"


class _Synth:
    """ctypes wrapper around a chip-synth shared library."""

    def __init__(self, libname, reset_fn, render_fn, load_rom_fn=None):
        self.lib = ctypes.CDLL(os.path.join(_LIB_DIR, libname))
        self._reset = getattr(self.lib, reset_fn)
        self._reset.restype = None
        self._reset.argtypes = []
        self._render = getattr(self.lib, render_fn)
        self._render.restype = ctypes.c_int
        self._render.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                                 ctypes.POINTER(ctypes.c_int16)]
        self._out = (ctypes.c_int16 * 2048)()
        self._load_rom = None
        if load_rom_fn:
            self._load_rom = getattr(self.lib, load_rom_fn)
            self._load_rom.restype = None
            self._load_rom.argtypes = [ctypes.c_char_p, ctypes.c_int]

    def reset(self):
        self._reset()

    def load_rom(self, data):
        """Hand ROM bytes to cores that need them (e.g. NES DMC). No-op if
        this synth doesn't expose a load_rom entry point."""
        if self._load_rom:
            self._load_rom(data, len(data))

    def render(self, payload, nsamples):
        """Render one frame's register writes to int16 mono PCM bytes."""
        n = self._render(payload, len(payload), nsamples, self._out)
        if n <= 0:
            return b""
        return ctypes.string_at(self._out, n * 2)


def _ines_prg_last_bank(data):
    """Parse an iNES (.nes) buffer and return the last 16KB PRG-ROM bank
    (what's statically mapped at $C000-$FFFF -- see host_nes.c), or None if
    it doesn't look like a valid iNES file."""
    if len(data) < 16 or data[0:4] != b"NES\x1a":
        return None
    prg_units = data[4]
    has_trainer = bool(data[6] & 0x04)
    offset = 16 + (512 if has_trainer else 0)
    prg = data[offset:offset + prg_units * 0x4000]
    if len(prg) < 0x4000:
        return None
    return prg[-0x4000:]


def _load_nes_prg_last_bank(rom_name):
    """Locate the same ROM the board loaded (by filename) in our own roms/
    tree, unzip it if needed, and return its last PRG-ROM bank. Returns None
    (logging why) if the ROM can't be found or parsed -- DMC just stays
    silent in that case, same as before this existed."""
    name = rom_name.decode("utf-8", "replace")
    path = os.path.join(_ROMS_ROOT, "nes", name)
    if not os.path.isfile(path):
        print("emu_audio: NES ROM not found for DMC playback:", name)
        return None
    try:
        if path.lower().endswith(".zip"):
            with zipfile.ZipFile(path) as zf:
                entries = [n for n in zf.namelist() if n.lower().endswith(".nes")]
                if not entries:
                    print("emu_audio: no .nes file inside", path)
                    return None
                data = zf.read(entries[0])
        else:
            with open(path, "rb") as f:
                data = f.read()
    except (OSError, zipfile.BadZipFile) as e:
        print("emu_audio: failed to read NES ROM", path, "-", e)
        return None
    bank = _ines_prg_last_bank(data)
    if bank is None:
        print("emu_audio: could not parse iNES header in", path)
    else:
        print("emu_audio: loaded", path, "for DMC (last PRG bank,", len(bank), "bytes)")
    return bank


# system token (bytes) -> ROM loader, for synths whose fidelity needs actual
# ROM bytes. Only called when the device sends a ROM name with achip.
_ROM_LOADERS = {
    b"nes-ntsc": _load_nes_prg_last_bank,
    b"nes-pal": _load_nes_prg_last_bank,
}


# system token (bytes) -> factory building its synth wrapper.
_SYNTH_FACTORIES = {
    b"genesis": lambda: _Synth("libgenesissynth." + _lib_ext(),
                               "genesis_synth_reset", "genesis_synth_render"),
    b"sms-ntsc": lambda: _Synth("libsmssynth." + _lib_ext(),
                                "sms_synth_reset_ntsc", "sms_synth_render"),
    b"sms-pal": lambda: _Synth("libsmssynth." + _lib_ext(),
                               "sms_synth_reset_pal", "sms_synth_render"),
    b"nes-ntsc": lambda: _Synth("libnessynth." + _lib_ext(),
                                "nes_synth_reset_ntsc", "nes_synth_render",
                                load_rom_fn="nes_synth_load_rom"),
    b"nes-pal": lambda: _Synth("libnessynth." + _lib_ext(),
                               "nes_synth_reset_pal", "nes_synth_render",
                               load_rom_fn="nes_synth_load_rom"),
    b"gb": lambda: _Synth("libgbsynth." + _lib_ext(),
                          "gb_synth_reset", "gb_synth_render"),
    b"msx": lambda: _Synth("libmsxsynth." + _lib_ext(),
                           "msx_synth_reset", "msx_synth_render"),
}

_SYSTEM_RATE = {
    b"genesis": GENESIS_SAMPLE_RATE,
    b"sms-ntsc": SMS_SAMPLE_RATE,
    b"sms-pal": SMS_SAMPLE_RATE,
    b"nes-ntsc": NES_SAMPLE_RATE,
    b"nes-pal": NES_SAMPLE_RATE,
    b"gb": GB_SAMPLE_RATE,
    b"msx": MSX_SAMPLE_RATE,
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
        # Player(s) queued for deletion on the main thread. Kept separate
        # from _player/_synth/_stream (rather than a "please tear down
        # whatever's current" flag) so that a start() for a *new* session --
        # which reassigns _synth/_stream synchronously on the comms thread,
        # ahead of process() running on the main thread -- can never have its
        # brand-new objects wiped out by a stale teardown meant for the
        # *previous* session. That exact race made every other emulator
        # launch silent: request_stop() would flag a pending teardown,
        # start() would then immediately overwrite _synth/_stream with the
        # new session's objects, and process() would blindly null whatever
        # was *currently* in those fields -- the new session's, not the old
        # one's -- before a player was ever built for them.
        self._pending_stop_player = None
        self._missing_warned = set()

    # --- called from the comms receive thread -------------------------------

    def start(self, system, rom_name=b""):
        """Begin a new emulator's audio (system is a bytes token, e.g. b'genesis').
        rom_name (bytes filename, no path) is only sent -- and only used --
        by cores whose fidelity needs actual ROM bytes, e.g. NES DMC."""
        self._retire_current()
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
        loader = _ROM_LOADERS.get(system)
        if loader and rom_name:
            bank = loader(rom_name)
            if bank is not None:
                self._synth.load_rom(bank)
        self._stream = _ChipStream(_SYSTEM_RATE.get(system, GENESIS_SAMPLE_RATE))
        self._system = system
        self._want_start = True
        print("emu_audio: started", system.decode("latin1", "replace"))

    def frame(self, payload, nsamples):
        synth, stream = self._synth, self._stream
        if synth is None or stream is None:
            return
        stream.push(synth.render(payload, nsamples))

    def _retire_current(self):
        """Detach the current synth/stream/player so a new session can be
        assigned immediately without racing a deferred teardown. The actual
        Player.delete() (a pyglet call) is queued for process() to run on the
        main thread; everything else here is plain attribute assignment,
        safe from any thread."""
        if self._player is not None:
            self._pending_stop_player = self._player
        self._player = None
        self._synth = None
        self._stream = None
        self._system = None
        self._want_start = False

    def request_stop(self):
        self._retire_current()

    # --- called from the main (pyglet) thread each tick ---------------------

    def process(self):
        if self._pending_stop_player is not None:
            try:
                self._pending_stop_player.delete()
            except Exception:
                pass
            self._pending_stop_player = None
        if self._want_start and self._stream is not None:
            self._want_start = False
            self._player = Player()
            self._player.queue(self._stream)
            self._player.play()


# Singleton used by comms.py and the engine.
emu_audio = EmuAudio()
