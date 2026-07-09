#!/usr/bin/env python3
"""Pre-render Doom (Voom) audio from the WAD into mp3s the emulator/host can play.

Voom runs on a spinning POV board with no audio; it sends "sound voom/<name>" /
"music voom/<name>" triggers (over TCP to the emulator, or serial to the hardware
host). Those consumers play files by name from system/<pkg>/sounds/, so this script
extracts every WAD sound and writes it to system/voom/sounds/<name>.mp3:

  - SFX  (DS* lumps): Doom DMX 8-bit PCM  -> WAV -> mp3            (needs ffmpeg)
  - Music (D_* lumps): MUS -> MIDI (mus2mid) -> synth -> WAV -> mp3 (needs fluidsynth
    or timidity, plus a soundfont; ffmpeg for the final mp3)

Run once (and again whenever the WAD changes):  make voom-sounds
"""

import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile

from wadfile import WAD
from mus2mid import mus2mid, Mus2MidError

DEFAULT_WAD = "../apps/retro-go/prboom-go/components/prboom/data/doom1.wad"
DEFAULT_OUT = "../system/voom/sounds"
DEFAULT_SOUNDFONTS = (
    "/usr/share/sounds/sf2/TimGM6mb.sf2",
    "/usr/share/sounds/sf2/default-GM.sf2",
    "/etc/alternatives/default-GM.sf2",
)


def build_wav(samplerate, samples):
    """Wrap raw 8-bit unsigned mono PCM in a WAV container (matches Doom DMX)."""
    data_len = len(samples)
    return b"".join([
        b"RIFF", struct.pack("<I", 36 + data_len), b"WAVE",
        b"fmt ", struct.pack("<IHHIIHH", 16, 1, 1, samplerate, samplerate, 1, 8),
        b"data", struct.pack("<I", data_len), samples,
    ])


def parse_dmx(lump):
    """Return (samplerate, pcm_bytes) from a Doom DMX sound lump, or None."""
    if not lump or len(lump) < 8:
        return None
    fmt, samplerate, numsamples = struct.unpack_from("<HHI", lump, 0)
    if fmt != 3:
        return None
    samples = lump[8:8 + numsamples]
    # DMX pads with 16 duplicate samples at each end; trim to avoid clicks.
    if len(samples) > 32:
        samples = samples[16:-16]
    if not samples:
        return None
    if samplerate <= 0:
        samplerate = 11025
    return samplerate, samples


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def find_soundfont(explicit):
    for sf in ([explicit] if explicit else []) + list(DEFAULT_SOUNDFONTS):
        if sf and os.path.exists(sf):
            return sf
    return None


def detect_synth():
    if shutil.which("fluidsynth"):
        return "fluidsynth"
    if shutil.which("timidity"):
        return "timidity"
    return None


def render_midi(synth, soundfont, mid_path, wav_path):
    if synth == "fluidsynth":
        run(["fluidsynth", "-ni", "-g", "1.0", "-F", wav_path, "-r", "44100",
             soundfont, mid_path])
    else:  # timidity
        run(["timidity", mid_path, "-Ow", "-o", wav_path])


def wav_to_mp3(wav_path, mp3_path):
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path, mp3_path])


def needs_build(out_path, wad_path, force):
    if force or not os.path.exists(out_path):
        return True
    return os.path.getmtime(wad_path) > os.path.getmtime(out_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wad", default=DEFAULT_WAD)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--soundfont", default=None)
    ap.add_argument("--force", action="store_true", help="rebuild even if up to date")
    ap.add_argument("--no-music", action="store_true", help="SFX only")
    args = ap.parse_args()

    if not os.path.exists(args.wad):
        sys.exit("WAD not found: %s" % args.wad)
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found (required). Install it and retry.")

    os.makedirs(args.out, exist_ok=True)
    wad = WAD(args.wad)
    print("Reading %s (%s)" % (args.wad, wad.magic.decode()))

    synth = None if args.no_music else detect_synth()
    soundfont = find_soundfont(args.soundfont) if synth == "fluidsynth" else "n/a"
    if not args.no_music and synth == "fluidsynth" and not soundfont:
        print("WARNING: no soundfont found; skipping music. "
              "Install one (e.g. /usr/share/sounds/sf2/TimGM6mb.sf2) or pass --soundfont.")
        synth = None
    if not args.no_music and not synth:
        print("WARNING: no MIDI synth found; skipping music.\n"
              "  Install one to render music, e.g.:  sudo apt install fluidsynth\n"
              "  (SFX still generated — they only need ffmpeg.)")

    sfx_count = music_count = skipped = failed = 0

    with tempfile.TemporaryDirectory(prefix="voom_build_") as tmp:
        # --- Sound effects (DS* lumps) ---
        for lump_name in wad.names_with_prefix("DS"):
            name = lump_name[2:].lower()
            mp3_path = os.path.join(args.out, name + ".mp3")
            if not needs_build(mp3_path, args.wad, args.force):
                skipped += 1
                continue
            parsed = parse_dmx(wad.lump(lump_name))
            if not parsed:
                continue
            samplerate, samples = parsed
            wav_path = os.path.join(tmp, name + ".wav")
            with open(wav_path, "wb") as f:
                f.write(build_wav(samplerate, samples))
            try:
                wav_to_mp3(wav_path, mp3_path)
                sfx_count += 1
                print("  sfx  ", name)
            except subprocess.CalledProcessError as e:
                failed += 1
                print("  FAIL sfx", name, e.stderr.decode("utf-8", "replace")[:200])

        # --- Music (D_* lumps) ---
        if synth:
            for lump_name in wad.names_with_prefix("D_"):
                name = lump_name[2:].lower()
                mp3_path = os.path.join(args.out, name + ".mp3")
                if not needs_build(mp3_path, args.wad, args.force):
                    skipped += 1
                    continue
                lump = wad.lump(lump_name)
                if not lump or lump[:4] != b"MUS\x1a":
                    continue  # not MUS (some D_* may be raw MIDI; skip for now)
                try:
                    mid = mus2mid(lump)
                except Mus2MidError as e:
                    failed += 1
                    print("  FAIL music", name, "(mus2mid:", e, ")")
                    continue
                mid_path = os.path.join(tmp, name + ".mid")
                wav_path = os.path.join(tmp, name + ".wav")
                with open(mid_path, "wb") as f:
                    f.write(mid)
                try:
                    render_midi(synth, soundfont, mid_path, wav_path)
                    wav_to_mp3(wav_path, mp3_path)
                    music_count += 1
                    print("  music", name)
                except subprocess.CalledProcessError as e:
                    failed += 1
                    print("  FAIL music", name, e.stderr.decode("utf-8", "replace")[:200])

    print("\nDone -> %s" % os.path.abspath(args.out))
    print("  sfx: %d  music: %d  skipped(up-to-date): %d  failed: %d"
          % (sfx_count, music_count, skipped, failed))
    if synth:
        print("  synth: %s  soundfont: %s" % (synth, soundfont))


if __name__ == "__main__":
    main()
