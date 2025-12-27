import random
from struct import pack, unpack

from deepspace import deepspace, PIXELS

ROWS = 256
COLUMNS = 256
TRANSPARENT_INDEX = 0xFF
STARS = COLUMNS // 2
led_count = PIXELS

starfield = [(random.randrange(COLUMNS), random.randrange(ROWS)) for n in range(STARS)]
spritedata = bytearray( b"\0\0\0\xff\xff" * 100)
all_strips = {}
qpalette = []
upalette = []

def change_colors(colors):
    # byteswap all longs
    fmt_unpack = "<" + "L" * (len(colors)//4)
    fmt_pack = ">" + "L" * (len(colors)//4)
    b = unpack(fmt_unpack, colors)
    return pack(fmt_pack, *b)

def pack_colors(colors):
    fmt_pack = "<" + "L" * len(colors)
    return pack(fmt_pack, *colors)

def unpack_palette(pal):
    fmt_unpack = "<" + "L" * (len(pal)//4)
    return unpack(fmt_unpack, pal)

def repeated(n, iterable):
    """Yield each item from `iterable` `n` times."""
    for item in iterable:
        for _ in range(n):
            yield item

def set_palettes(paldata):
    global palette, upalette
    palette = change_colors(paldata)
    upalette = unpack_palette(palette)

def get_visible_column(sprite_x, sprite_width, render_column):
    sprite_column = sprite_width - 1 - ((render_column - sprite_x + COLUMNS) % COLUMNS)
    if 0 <= sprite_column < sprite_width:
        return sprite_column
    else:
        return -1

def step_starfield():
    for (n, (x, y)) in enumerate(starfield):
        y -= 1
        if y < 0:
            y = ROWS - 1
            x = random.randrange(COLUMNS)
        starfield[n] = (x, y)


def render(column):
    pixels = [0x00000000] * led_count

    for (x,y) in starfield:
        if x == column:
            try:
                px = deepspace[y]
                if px < PIXELS:
                    pixels[px] = 0xff404040
            except Exception as e:
                print(e, len(pixels), y, px)
                print(y, deepspace)

    # el sprite 0 se dibuja arriba de todos los otros
    for n in range(99, -1, -1):
        x, y, image, frame, perspective = unpack("BBBBb", spritedata[n*5:n*5+5])
        if frame == 255:
            continue

        strip = all_strips.get(image)
        if not strip:
            continue
        w, h, total_frames, pal = unpack("BBBB", strip[0:4])
        pal_base = 256 * pal
        if w == 255: w = 256 # caso especial, para los planetas
        pixeldata = memoryview(strip)[4:]

        frame %= total_frames

        visible_column = get_visible_column(x, w, column)
        if visible_column != -1:
            base = visible_column * h + (frame * w * h)
            if perspective:
                desde = max(y, 0)
                hasta = min(y + h, ROWS - 1)
                comienzo = max( -y, 0)
                src = base + comienzo

                for y in range(desde, hasta):
                    index = pixeldata[src]
                    src += 1
                    if index != TRANSPARENT_INDEX:
                        color = upalette[index + pal_base]
                        if perspective == 1:
                            y = deepspace[y]
                        else:
                            y = led_count - 1 - y
                        if y < led_count:
                            pixels[y] = color
            else:
                zleds = deepspace[255-y]

                for led in range(zleds):
                    src = led * led_count // zleds
                    if src >= h:
                        break
                    index = pixeldata[base + h - 1 - src]
                    if index != TRANSPARENT_INDEX:
                        color = upalette[index + pal_base]
                        pixels[led] = color

    return pixels
