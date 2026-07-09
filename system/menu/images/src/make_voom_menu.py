#!/usr/bin/env python3

from pathlib import Path

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFilter
from PIL import ImageFont


WIDTH = 64
HEIGHT = 30
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "voom.png"
FONT_PATH = Path("/System/Library/Fonts/Supplemental/Verdana Bold.ttf")


def fit_font(text, max_width, max_height):
    for size in range(28, 10, -1):
        font = ImageFont.truetype(str(FONT_PATH), size=size)
        bbox = font.getbbox(text)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if width <= max_width and height <= max_height:
            return font
    return ImageFont.truetype(str(FONT_PATH), size=12)


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


def main():
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((1, 3, WIDTH - 2, HEIGHT - 4), radius=6, fill=(18, 0, 0, 210))
    draw.rounded_rectangle((2, 4, WIDTH - 3, HEIGHT - 5), radius=5, outline=(113, 14, 0, 255), width=1)

    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((6, 7, WIDTH - 7, HEIGHT + 6), fill=(255, 104, 0, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(6))
    image.alpha_composite(glow)

    text = "VOOM"
    font = fit_font(text, max_width=56, max_height=18)
    bbox = font.getbbox(text)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (WIDTH - text_width) // 2 - bbox[0]
    y = (HEIGHT - text_height) // 2 - bbox[1] - 1

    shadow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 220), stroke_width=2, stroke_fill=(0, 0, 0, 220))
    shadow = shadow.filter(ImageFilter.GaussianBlur(1))
    image.alpha_composite(shadow)

    text_mask = Image.new("L", (WIDTH, HEIGHT), 0)
    mask_draw = ImageDraw.Draw(text_mask)
    mask_draw.text((x, y), text, font=font, fill=255, stroke_width=2, stroke_fill=255)
    gradient = vertical_gradient((WIDTH, HEIGHT), (255, 221, 94), (209, 31, 0))
    gradient.putalpha(text_mask)
    image.alpha_composite(gradient)

    outline = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    outline_draw = ImageDraw.Draw(outline)
    outline_draw.text((x, y), text, font=font, fill=(0, 0, 0, 0), stroke_width=2, stroke_fill=(28, 0, 0, 255))
    image.alpha_composite(outline)

    draw = ImageDraw.Draw(image)
    draw.line((10, HEIGHT - 6, WIDTH - 10, HEIGHT - 6), fill=(255, 160, 0, 120), width=1)
    draw.line((12, HEIGHT - 5, WIDTH - 12, HEIGHT - 5), fill=(255, 232, 121, 90), width=1)

    image.save(OUTPUT)
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()
