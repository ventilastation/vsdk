"""Synthesises the small sound effects of the LD60 games in games/ld60/.

    python3 tools/ld60_assets/make_sounds.py

Each effect is a few hundred milliseconds of square wave, sweep or noise,
written as WAV and converted to MP3 with ffmpeg (the format the base and the
emulator play). Needs ffmpeg on the PATH.
"""
import math
import random
import subprocess
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAMES = ROOT / "games" / "ld60"
RATE = 22050


def tone(freq_from, freq_to, seconds, shape="square", volume=0.45, decay=3.0):
    """A sweep from one frequency to another with a falling envelope."""
    rng = random.Random(7)
    count = int(RATE * seconds)
    samples = []
    phase = 0.0
    for i in range(count):
        t = i / count
        freq = freq_from + (freq_to - freq_from) * t
        phase += freq / RATE
        if shape == "square":
            value = 1.0 if (phase % 1.0) < 0.5 else -1.0
        elif shape == "saw":
            value = 2.0 * (phase % 1.0) - 1.0
        elif shape == "noise":
            value = rng.uniform(-1.0, 1.0)
        else:
            value = math.sin(2 * math.pi * phase)
        samples.append(value * volume * math.exp(-decay * t))
    return samples


def join(*parts):
    out = []
    for part in parts:
        out.extend(part)
    return out


EFFECTS = {
    "shoot": tone(1400, 300, 0.16),
    "bomb": tone(500, 120, 0.22, "saw"),
    "explo": tone(300, 40, 0.35, "noise", 0.6, 4.0),
    "die": join(tone(600, 100, 0.45, "saw", 0.5, 2.0), tone(200, 30, 0.3, "noise", 0.5, 4.0)),
    "pickup": join(tone(880, 880, 0.05), tone(1320, 1320, 0.08)),
    "jump": tone(300, 900, 0.18, "square", 0.4, 2.0),
    "lane": tone(500, 800, 0.07, "square", 0.3, 1.0),
    "win": join(tone(523, 523, 0.1), tone(659, 659, 0.1), tone(784, 784, 0.1),
                tone(1047, 1047, 0.3, "square", 0.45, 2.0)),
}

GAME_SOUNDS = {
    "spiral_tunnel": ("bomb", "explo", "die", "win"),
    "catch_the_robots": ("pickup", "die", "win"),
    "rim_runner": ("jump", "pickup", "explo", "die", "win"),
    "dodge_em": ("pickup", "lane", "die", "win"),
    "defender": ("shoot", "explo", "die", "win"),
}


def write_mp3(samples, target):
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "effect.wav"
        with wave.open(str(wav_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(RATE)
            wav.writeframes(b"".join(
                int(max(-1.0, min(1.0, s)) * 32767).to_bytes(2, "little", signed=True)
                for s in samples))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_path),
                        "-codec:a", "libmp3lame", "-b:a", "48k", str(target)], check=True)


def main():
    for game, names in GAME_SOUNDS.items():
        folder = GAMES / game / "sounds"
        folder.mkdir(parents=True, exist_ok=True)
        for name in names:
            write_mp3(EFFECTS[name], folder / (name + ".mp3"))
    print("wrote sounds for", ", ".join(GAME_SOUNDS))


if __name__ == "__main__":
    main()
