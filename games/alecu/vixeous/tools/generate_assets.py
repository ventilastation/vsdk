#!/usr/bin/env python3
"""Generate Vixeous placeholder assets.

This keeps the intentionally original pixel art and synth sounds reproducible.
Run from the VSDK root or directly from this script's folder:

    python3 games/alecu/vixeous/tools/generate_assets.py
"""

import argparse
import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "images"
SOUNDS = ROOT / "sounds"
TRANSPARENT = (255, 0, 255, 0)
RATE = 22050


try:
    FONT = ImageFont.load_default()
except Exception:
    FONT = None


def save_strip(name, frame_w, frame_h, frames, draw_frame):
    image = Image.new("RGBA", (frame_w * frames, frame_h), TRANSPARENT)
    for frame in range(frames):
        tile = Image.new("RGBA", (frame_w, frame_h), TRANSPARENT)
        draw_frame(ImageDraw.Draw(tile), frame, frame_w, frame_h)
        image.alpha_composite(tile, (frame * frame_w, 0))
    image.save(IMAGES / name)


def draw_ship(draw, frame, w, h):
    hull = (166, 176, 184, 255)
    bright = (222, 230, 232, 255)
    dark = (54, 62, 70, 255)
    red = (238, 36, 52, 255) if frame % 2 == 0 else (255, 90, 68, 255)
    draw.polygon([(w // 2, 0), (w - 3, h - 4), (w // 2 + 2, h - 2), (w // 2, h - 6), (w // 2 - 2, h - 2), (2, h - 4)], fill=hull)
    draw.polygon([(w // 2, 2), (w // 2 + 3, h - 4), (w // 2, h - 6), (w // 2 - 3, h - 4)], fill=dark)
    draw.line([(4, h - 5), (0, h - 1)], fill=red)
    draw.line([(w - 5, h - 5), (w - 1, h - 1)], fill=red)
    draw.rectangle((w // 2 - 1, 4, w // 2 + 1, 6), fill=bright)
    draw.rectangle((w // 2 - 1, h - 2, w // 2 + 1, h - 1), fill=red)


def draw_enemy(draw, frame, w, h):
    kind = frame // 2
    flap = frame & 1
    grays = (
        ((178, 185, 184, 255), (60, 67, 72, 255)),
        ((140, 151, 156, 255), (44, 50, 57, 255)),
        ((200, 195, 184, 255), (68, 62, 58, 255)),
    )
    body, shade = grays[kind]
    red = (230, 36, 48, 255) if flap == 0 else (255, 82, 56, 255)
    draw.polygon([(w // 2, flap), (w - 2, 5 + flap), (w - 4, h - 2), (w // 2, h - 4), (3, h - 2), (1, 5 + flap)], fill=body)
    draw.polygon([(w // 2, 3 + flap), (w - 5, 6 + flap), (w // 2, h - 5), (4, 6 + flap)], fill=shade)
    draw.rectangle((w // 2 - 2, 5 + flap, w // 2 + 2, 6 + flap), fill=red)


def draw_boss(draw, frame, w, h):
    shell = (122, 130, 134, 255)
    dark = (34, 39, 45, 255)
    red = (210, 28 + frame * 36, 44, 255)
    hot = (255, 112, 74, 255)
    draw.rounded_rectangle((3, 3, w - 4, h - 4), radius=3, fill=dark, outline=shell)
    draw.polygon([(w // 2, 0), (w - 1, h // 2), (w // 2, h - 1), (0, h // 2)], outline=shell, fill=(74, 80, 86, 255))
    draw.rectangle((w // 2 - 4, h // 2 - 3, w // 2 + 4, h // 2 + 3), fill=red)
    draw.line((5, h - 3, w - 6, h - 3), fill=hot)
    draw.line((6, 4, w - 7, 4), fill=(188, 198, 200, 255))


def draw_shots(draw, frame, w, h):
    red = (255, 70, 58, 255)
    if frame == 0:
        draw.rectangle((w // 2 - 1, 0, w // 2 + 1, h - 2), fill=(235, 244, 246, 255))
        draw.point((w // 2, h - 1), fill=red)
    elif frame == 1:
        draw.ellipse((1, 1, w - 2, h - 2), fill=(132, 132, 128, 255), outline=red)
        draw.rectangle((w // 2 - 1, 0, w // 2, 2), fill=(255, 210, 96, 255))
    else:
        draw.line((0, h // 2, w - 1, h // 2), fill=red)
        draw.line((w // 2, 0, w // 2, h - 1), fill=red)


def draw_explosion(draw, frame, w, h):
    colors = (
        (255, 245, 180, 255), (255, 190, 84, 255), (255, 98, 52, 255),
        (214, 34, 52, 255), (84, 84, 92, 220), (38, 42, 50, 160),
    )
    radius = 2 + frame * 2
    cx, cy = w // 2, h // 2
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=colors[frame])
    if frame < 4:
        draw.line((cx, 0, cx, h - 1), fill=(255, 255, 255, 220))
        draw.line((0, cy, w - 1, cy), fill=(255, 255, 255, 220))


def draw_targets(draw, frame, w, h):
    gray = ((128, 132, 128, 255), (154, 156, 150, 255), (108, 112, 112, 255), (176, 172, 160, 255))[frame]
    dark = (36, 40, 42, 255)
    red = (232, 32, 42, 255)
    draw.rounded_rectangle((1, 1, w - 2, h - 2), radius=2, fill=dark, outline=gray)
    draw.ellipse((4, 2, w - 5, h - 3), fill=gray)
    draw.line((w // 2, 0, w // 2, h - 1), fill=red)
    draw.line((1, h // 2, w - 2, h // 2), fill=red)
    draw.rectangle((w // 2 - 1, h // 2 - 1, w // 2 + 1, h // 2 + 1), fill=(255, 120, 72, 255))


def draw_reticle(draw, frame, w, h):
    colors = ((220, 230, 224, 230), (255, 196, 74, 255), (255, 72, 72, 255))
    color = colors[frame]
    draw.line((0, h // 2, 5, h // 2), fill=color)
    draw.line((w - 6, h // 2, w - 1, h // 2), fill=color)
    draw.rectangle((7, 1, w - 8, h - 2), outline=color)


def _draw_water(draw, frame, w, h, transition=False):
    base = (18, 82 + (frame & 1) * 12, 148 + (frame & 1) * 18, 255)
    wave = (72, 154, 210, 255)
    draw.rectangle((0, 0, w - 1, h - 1), fill=base)
    for y in range(3 + (frame & 1) * 2, h, 6):
        draw.arc((1, y - 4, 13, y + 4), 0, 180, fill=wave)
        draw.arc((14, y - 4, 29, y + 4), 0, 180, fill=wave)
    if transition:
        sand = (178, 142, 62, 255)
        draw.polygon([(w - 10, 0), (w - 1, 0), (w - 1, h - 1), (w - 16, h - 1), (w - 12, h // 2)], fill=sand)
        draw.line((w - 12, 0, w - 18, h - 1), fill=(210, 178, 96, 255))


def _draw_sand(draw, frame, w, h, grass=False, water=False):
    base = (174, 132, 54, 255) if frame & 1 else (190, 148, 62, 255)
    speck = (218, 182, 92, 255)
    draw.rectangle((0, 0, w - 1, h - 1), fill=base)
    for x in range((frame * 5) % 9, w, 9):
        draw.line((x, 0, x - 6, h - 1), fill=speck)
    if water:
        draw.polygon([(0, 0), (7, 0), (12, h // 2), (8, h - 1), (0, h - 1)], fill=(24, 104, 164, 255))
        draw.line((9, 0, 14, h - 1), fill=(224, 188, 104, 255))
    if grass:
        green = (48, 122, 58, 255)
        draw.polygon([(w - 10, 0), (w - 1, 0), (w - 1, h - 1), (w - 14, h - 1), (w - 8, h // 2)], fill=green)
        for x in range(w - 12, w, 4):
            draw.line((x, h - 1, x + 2, 4), fill=(92, 166, 78, 255))


def _draw_grass(draw, frame, w, h, sand_edge=False):
    base = (42, 120 + (frame & 1) * 12, 58, 255)
    dark = (24, 82, 44, 255)
    light = (100, 170, 78, 255)
    draw.rectangle((0, 0, w - 1, h - 1), fill=base)
    for x in range((frame * 4) % 8, w, 8):
        draw.polygon([(x, h - 1), (x + 3, 3), (x + 6, h - 1)], fill=dark if x % 16 else light)
    if sand_edge:
        sand = (178, 138, 58, 255)
        draw.polygon([(0, 0), (8, 0), (14, h // 2), (10, h - 1), (0, h - 1)], fill=sand)
        draw.line((11, 0, 16, h - 1), fill=(92, 166, 78, 255))


def _draw_pad(draw, frame, w, h):
    base = (88, 92, 94, 255) if frame == 14 else (108, 104, 98, 255)
    draw.rectangle((0, 0, w - 1, h - 1), fill=base)
    draw.rectangle((2, 2, w - 3, h - 3), outline=(166, 170, 166, 255))
    draw.line((4, h // 2, w - 5, h // 2), fill=(226, 30, 42, 255), width=2)
    if frame == 15:
        draw.rectangle((w // 2 - 3, 3, w // 2 + 3, h - 4), fill=(226, 30, 42, 255))
    else:
        draw.ellipse((w // 2 - 4, h // 2 - 4, w // 2 + 4, h // 2 + 4), outline=(226, 30, 42, 255))


def draw_terrain(draw, frame, w, h):
    if frame in (0, 1):
        _draw_water(draw, frame, w, h)
    elif frame in (2, 3):
        _draw_sand(draw, frame, w, h, water=True)
    elif frame in (4, 5):
        _draw_sand(draw, frame, w, h)
    elif frame in (6, 7):
        _draw_grass(draw, frame, w, h)
    elif frame in (8, 9):
        _draw_water(draw, frame, w, h, transition=True)
    elif frame in (10, 11):
        _draw_sand(draw, frame, w, h, grass=True)
    elif frame in (12, 13):
        _draw_grass(draw, frame, w, h, sand_edge=True)
    else:
        _draw_pad(draw, frame, w, h)


def draw_digits():
    width, height, frames = 5, 7, 12
    image = Image.new("RGBA", (width * frames, height), TRANSPARENT)
    glyphs = ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", " ", "*")
    for index, char in enumerate(glyphs):
        tile = Image.new("RGBA", (width, height), TRANSPARENT)
        draw = ImageDraw.Draw(tile)
        if char == "*":
            draw.polygon([(2, 0), (4, 3), (3, 6), (1, 6), (0, 3)], fill=(232, 32, 42, 255))
        elif char != " ":
            draw.text((0, -2), char, font=FONT, fill=(220, 230, 224, 255))
        image.alpha_composite(tile, (index * width, 0))
    image.save(IMAGES / "digits.png")


def draw_messages():
    labels = ("VIXEOUS", "AREA 2", "GAME OVER")
    width, height = 64, 12
    image = Image.new("RGBA", (width * len(labels), height), TRANSPARENT)
    for index, label in enumerate(labels):
        tile = Image.new("RGBA", (width, height), TRANSPARENT)
        draw = ImageDraw.Draw(tile)
        draw.rectangle((0, 2, width - 1, height - 3), fill=(28, 32, 36, 235), outline=(180, 188, 184, 255))
        draw.line((2, height - 3, width - 3, height - 3), fill=(232, 32, 42, 255))
        text_w = draw.textlength(label, font=FONT) if hasattr(draw, "textlength") else len(label) * 6
        draw.text(((width - int(text_w)) // 2, 1), label, font=FONT, fill=(245, 235, 170, 255))
        image.alpha_composite(tile, (index * width, 0))
    image.save(IMAGES / "messages.png")


def draw_menu():
    width, height, frames = 64, 30, 2
    image = Image.new("RGBA", (width * frames, height), (0, 0, 0, 255))
    for frame in range(frames):
        tile = Image.new("RGBA", (width, height), (16, 28, 34, 255))
        draw = ImageDraw.Draw(tile)
        draw.rectangle((0, 16, width, height), fill=(28, 122, 62, 255))
        draw.polygon([(0, 18), (18, 13), (36, 19), (64, 12), (64, 20), (36, 25), (18, 20), (0, 25)], fill=(184, 142, 58, 255))
        draw.polygon([(0, 24), (22, 20), (42, 24), (64, 18), (64, 30), (0, 30)], fill=(22, 104, 178, 255))
        draw.ellipse((7, 5, 56, 28), outline=(185, 194, 194, 255))
        draw.polygon([(32, 5), (41, 20), (32, 17), (23, 20)], fill=(178, 186, 188, 255))
        draw.line((24, 20, 16, 26), fill=(232, 32 + frame * 24, 42, 255), width=2)
        draw.line((40, 20, 48, 26), fill=(232, 32 + frame * 24, 42, 255), width=2)
        draw.text((9, 1), "VIXEOUS", font=FONT, fill=(238, 224, 154, 255))
        image.alpha_composite(tile, (frame * width, 0))
    image.save(ROOT / "menu.png")


def envelope(index, total):
    attack = max(1, int(total * 0.05))
    release = max(1, int(total * 0.18))
    if index < attack:
        return index / attack
    if index > total - release:
        return max(0, (total - index) / release)
    return 1.0


def write_wav(path, duration, voices, volume=0.35):
    samples = int(RATE * duration)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        frames = bytearray()
        for index in range(samples):
            t = index / RATE
            value = 0.0
            for freq, amp, mod in voices:
                f = freq(t) if callable(freq) else freq
                phase_mod = mod(t) if callable(mod) else mod
                value += amp * math.sin(2 * math.pi * f * t + phase_mod)
            value *= envelope(index, samples) * volume
            value = max(-1, min(1, value))
            frames.extend(struct.pack("<h", int(value * 32767)))
        out.writeframes(frames)


def convert_sound(name, duration, voices, volume=0.35):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to generate Vixeous MP3 assets")
    wav = SOUNDS / (name + ".wav")
    mp3 = SOUNDS / (name + ".mp3")
    write_wav(wav, duration, voices, volume)
    subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "6", str(mp3)], check=True)
    wav.unlink()


def generate_images():
    IMAGES.mkdir(parents=True, exist_ok=True)
    save_strip("ship.png", 18, 13, 4, draw_ship)
    save_strip("enemy.png", 14, 11, 6, draw_enemy)
    save_strip("boss.png", 36, 19, 2, draw_boss)
    save_strip("shots.png", 6, 10, 3, draw_shots)
    save_strip("explosion.png", 20, 20, 6, draw_explosion)
    save_strip("targets.png", 14, 10, 4, draw_targets)
    save_strip("reticle.png", 18, 6, 3, draw_reticle)
    save_strip("terrain.png", 32, 16, 16, draw_terrain)
    draw_digits()
    draw_messages()
    draw_menu()


def generate_sounds():
    SOUNDS.mkdir(parents=True, exist_ok=True)
    convert_sound("shoot", 0.16, [
        (lambda t: 840 + 620 * t, 0.8, 0),
        (lambda t: 1680 + 300 * t, 0.25, 0),
    ], 0.28)
    convert_sound("bomb", 0.28, [
        (lambda t: 260 - 130 * t, 0.8, 0),
        (90, 0.25, lambda t: 15 * t),
    ], 0.32)
    convert_sound("boom", 0.42, [
        (lambda t: 120 - 80 * min(t, 0.35), 0.9, lambda t: 20 * math.sin(70 * t)),
        (43, 0.4, 0),
    ], 0.45)
    convert_sound("hit", 0.12, [
        (lambda t: 520 - 240 * t, 0.75, 0),
        (1200, 0.25, lambda t: 9 * math.sin(90 * t)),
    ], 0.24)
    convert_sound("boss", 0.55, [
        (lambda t: 90 + 60 * math.sin(5 * t), 0.7, 0),
        (180, 0.35, lambda t: 8 * math.sin(20 * t)),
    ], 0.38)
    convert_sound("area", 0.8, [
        (lambda t: (330, 440, 554, 660)[min(3, int(t * 5))], 0.55, 0),
        (lambda t: (660, 554, 880, 990)[min(3, int(t * 5))], 0.22, 0),
    ], 0.34)
    convert_sound("gameover", 1.4, [
        (lambda t: 360 - 160 * min(t / 1.4, 1), 0.65, 0),
        (lambda t: 180 - 80 * min(t / 1.4, 1), 0.35, 0),
    ], 0.32)
    convert_sound("flight", 10.0, [
        (lambda t: (220, 247, 294, 330, 294, 247, 196, 247)[int(t * 2) % 8], 0.45, 0),
        (lambda t: (440, 494, 587, 660, 587, 494, 392, 494)[int(t * 2) % 8], 0.18, 0),
        (55, 0.25, lambda t: 2.5 * math.sin(2 * math.pi * 0.5 * t)),
    ], 0.28)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-sounds", action="store_true", help="only regenerate PNG assets")
    parser.add_argument("--skip-images", action="store_true", help="only regenerate MP3 assets")
    args = parser.parse_args()
    if not args.skip_images:
        generate_images()
    if not args.skip_sounds:
        generate_sounds()


if __name__ == "__main__":
    main()
