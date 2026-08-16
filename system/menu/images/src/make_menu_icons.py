#!/usr/bin/env python3
"""Generate menu icons for the group tiles and other slugs that have no
game of their own to borrow art from (see make_voom_menu.py, which this
factors the shared "rounded card + glow + gradient text" style out of).

Each entry in ICONS is one 64x30 strip, styled by hand to read as a small
badge for its theme -- a jam badge, a console badge, a warning-stripe demo
badge -- rather than borrowing any single game's actual in-game art, since a
group holds many unrelated games.
"""

from pathlib import Path

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFilter
from PIL import ImageFont


WIDTH = 64
HEIGHT = 30
ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = Path("/System/Library/Fonts/Supplemental/Verdana Bold.ttf")


def fit_font(text, max_width, max_height, max_size=28, min_size=8):
    for size in range(max_size, min_size - 1, -1):
        font = ImageFont.truetype(str(FONT_PATH), size=size)
        bbox = font.getbbox(text)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if width <= max_width and height <= max_height:
            return font
    return ImageFont.truetype(str(FONT_PATH), size=min_size)


def vertical_gradient(size, top_rgb, bottom_rgb):
    gradient = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = gradient.load()
    width, height = size
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(top_rgb[i] * (1 - t) + bottom_rgb[i] * t) for i in range(3))
        for x in range(width):
            pixels[x, y] = color + (255,)
    return gradient


def badge(text, card_fill, card_outline, glow_rgb, text_top, text_bottom,
          outline_rgb, accent_rgb, glow_alpha=90, max_text_width=56):
    """One rounded-card text badge, same recipe as make_voom_menu.py's VOOM
    icon: card, radial glow, drop shadow, gradient-filled outlined text, two
    accent lines along the bottom edge."""
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((1, 3, WIDTH - 2, HEIGHT - 4), radius=6, fill=card_fill)
    draw.rounded_rectangle((2, 4, WIDTH - 3, HEIGHT - 5), radius=5, outline=card_outline, width=1)

    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((6, 7, WIDTH - 7, HEIGHT + 6), fill=glow_rgb + (glow_alpha,))
    glow = glow.filter(ImageFilter.GaussianBlur(6))
    image.alpha_composite(glow)

    font = fit_font(text, max_width=max_text_width, max_height=18)
    bbox = font.getbbox(text)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (WIDTH - text_width) // 2 - bbox[0]
    y = (HEIGHT - text_height) // 2 - bbox[1] - 1

    shadow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 220),
                      stroke_width=2, stroke_fill=(0, 0, 0, 220))
    shadow = shadow.filter(ImageFilter.GaussianBlur(1))
    image.alpha_composite(shadow)

    text_mask = Image.new("L", (WIDTH, HEIGHT), 0)
    mask_draw = ImageDraw.Draw(text_mask)
    mask_draw.text((x, y), text, font=font, fill=255, stroke_width=2, stroke_fill=255)
    gradient = vertical_gradient((WIDTH, HEIGHT), text_top, text_bottom)
    gradient.putalpha(text_mask)
    image.alpha_composite(gradient)

    outline = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    outline_draw = ImageDraw.Draw(outline)
    outline_draw.text((x, y), text, font=font, fill=(0, 0, 0, 0),
                       stroke_width=2, stroke_fill=outline_rgb + (255,))
    image.alpha_composite(outline)

    draw = ImageDraw.Draw(image)
    draw.line((10, HEIGHT - 6, WIDTH - 10, HEIGHT - 6), fill=accent_rgb + (120,), width=1)
    draw.line((12, HEIGHT - 5, WIDTH - 12, HEIGHT - 5),
              fill=tuple(min(255, c + 40) for c in accent_rgb) + (90,), width=1)
    return image


# Each group holds many unrelated games, so there's no single "in-game"
# palette to borrow -- these lean on what the group itself represents
# instead: a jam badge for a jam, a console badge for emulators, a
# Python-brand badge for PyCamp, a warning-stripe badge for a stress-test
# demo. (order, filename, kwargs for badge()).
ICONS = [
    # Alecu: the flagship/personal-collection tile -- a cool cyan "signature"
    # badge, distinct from any one game's own colours.
    ("alecu.png", dict(
        text="ALECU", card_fill=(6, 18, 26, 210), card_outline=(20, 110, 130, 255),
        glow_rgb=(0, 200, 220), text_top=(190, 245, 255), text_bottom=(20, 150, 190),
        outline_rgb=(6, 40, 50), accent_rgb=(0, 190, 210),
    )),
    ("other.png", dict(
        text="OTHER", card_fill=(20, 16, 26, 210), card_outline=(90, 70, 120, 255),
        glow_rgb=(170, 120, 220), text_top=(230, 210, 255), text_bottom=(120, 80, 180),
        outline_rgb=(30, 18, 45), accent_rgb=(150, 110, 210),
    )),
    ("vsjam_may25.png", dict(
        text="MAY 25", card_fill=(8, 22, 10, 210), card_outline=(40, 140, 50, 255),
        glow_rgb=(110, 230, 90), text_top=(230, 255, 200), text_bottom=(60, 170, 50),
        outline_rgb=(10, 40, 12), accent_rgb=(120, 220, 90),
    )),
    ("vsjam_oct25.png", dict(
        text="OCT 25", card_fill=(26, 14, 4, 210), card_outline=(160, 80, 10, 255),
        glow_rgb=(255, 140, 20), text_top=(255, 220, 140), text_bottom=(210, 90, 10),
        outline_rgb=(40, 16, 2), accent_rgb=(255, 150, 30),
    )),
    ("pycamp_mar25.png", dict(
        text="PYCAMP", card_fill=(6, 14, 26, 210), card_outline=(40, 90, 160, 255),
        glow_rgb=(70, 150, 240), text_top=(255, 232, 130), text_bottom=(255, 196, 30),
        outline_rgb=(10, 24, 45), accent_rgb=(70, 150, 240), max_text_width=58,
    )),
    ("tech_demos.png", dict(
        text="DEMOS", card_fill=(6, 20, 20, 210), card_outline=(20, 130, 120, 255),
        glow_rgb=(40, 230, 200), text_top=(200, 255, 245), text_bottom=(20, 170, 150),
        outline_rgb=(6, 40, 36), accent_rgb=(40, 220, 190),
    )),
    ("emulators_group.png", dict(
        text="RETRO", card_fill=(16, 16, 20, 210), card_outline=(120, 120, 130, 255),
        glow_rgb=(180, 60, 220), text_top=(235, 235, 245), text_bottom=(140, 140, 155),
        outline_rgb=(20, 20, 26), accent_rgb=(180, 70, 220),
    )),
    ("more_apps.png", dict(
        text="MÁS...", card_fill=(10, 12, 22, 210), card_outline=(60, 80, 150, 255),
        glow_rgb=(110, 140, 255), text_top=(225, 232, 255), text_bottom=(120, 145, 230),
        outline_rgb=(14, 18, 36), accent_rgb=(110, 140, 255),
    )),
]


def main():
    for filename, kwargs in ICONS:
        image = badge(**kwargs)
        output = ROOT / filename
        image.save(output)
        print(f"Created {output}")


if __name__ == "__main__":
    main()
