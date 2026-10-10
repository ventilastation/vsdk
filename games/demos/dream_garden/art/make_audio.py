"""Rebuild original soft tones. Host tool: Python 3 and ffmpeg, no game dependency."""
from pathlib import Path
import math
import struct
import subprocess
import tempfile
import wave

RATE = 22050
DESTINATION = Path(__file__).resolve().parents[1] / "sounds"


def encode(name, duration, sample):
    with tempfile.TemporaryDirectory() as temporary:
        wav_path = Path(temporary) / "tone.wav"
        with wave.open(str(wav_path), "wb") as output:
            output.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
            output.writeframes(b"".join(struct.pack("<h", int(32767 * sample(i / RATE)))
                                       for i in range(int(duration * RATE))))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", "64k",
                        str(DESTINATION / (name + ".mp3"))], check=True)


def bloom(t):
    envelope = (1 - math.exp(-t * 40)) * math.exp(-t * 4)
    return 0.13 * envelope * (math.sin(2 * math.pi * 440 * t)
                              + 0.4 * math.sin(2 * math.pi * 660 * t))


def lullaby(t):
    notes = (220, 261.626, 329.628, 391.995)
    result = 0
    for index, frequency in enumerate(notes):
        local = t - index * 8
        if local >= 0:
            envelope = min(1, local / 2) * math.exp(-local / 7)
            result += 0.08 * envelope * math.sin(2 * math.pi * frequency * t)
    return result * min(1, (32 - t) / 3)


if __name__ == "__main__":
    DESTINATION.mkdir(exist_ok=True)
    encode("bloom", 1.5, bloom)
    encode("lullaby", 32, lullaby)
