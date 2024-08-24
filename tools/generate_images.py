from PIL import Image, ImageChops
import os
import sys
from itertools import zip_longest, chain
import struct
import imagedefs

import matplotlib.image as mpimg
from numpy import sin, cos, pi, ndarray, array, uint8

TRANSPARENT = (255, 0, 255)
FOLDER = "../images"
WORKDIR = ".workdir/"

os.makedirs(WORKDIR, exist_ok=True)

def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)

"""
La funcion toma un archivo *.png y devuelve en binario (RGBI) la secuencia 
de n_leds prendidos para n_ang diferentes
"""
def reproject(image, n_led=54, n_ang=256):
    src = array(image)                    # Levanta la imagen
    dst = ndarray((n_led, n_ang, 4), uint8)        # Imagen de destino

    wx, wy, dim = src.shape         # Me da las dimensiones del frame en pixeles

    center_x = int((wx-1)/2)        # Calcula la cordenada x del centro de la imagen
    center_y = int((wy-1)/2)        # Calcula la cordenada y del centro de la imagen
    rad = min(center_x, center_y)   # Calcula el radio que barre la imagen dentro del frame

    #intensidad = [ int(31 * i**2 / n_led**2) for i in range(n_led)]
    
    for m in range(0,n_ang):
        for n in range(0,n_led):
            x = center_x + int(rad * (n+1)/n_led * cos(m * 2*pi/n_ang)) 
            y = center_y + int(rad * (n+1)/n_led * sin(m * 2*pi/n_ang))
            dst[n, m] = src[x,y,0:4]

    return Image.fromarray(dst)


images_per_palette = {}

for filename, opts in imagedefs.all_images.items():
    palnumber = opts["palette"]
    images_per_palette.setdefault(palnumber, []).append(filename)

raws = []
rom_strips = []
palettes = []
attributes = {}

for palnumber, filenames in sorted(images_per_palette.items()):
    images = {}

    for f in filenames:
        image = Image.open(os.path.join(FOLDER, f)).convert("RGBA")
        opts = imagedefs.all_images[f]
        if opts.get("process") == "reproject":
            print("reprojecting", f, file=sys.stderr)
            image = reproject(image)
        images[f] = image

    workspace_size = (
        max(i.width for i in images.values()),
        sum(i.height for i in images.values())
    )

    workspace = Image.new("RGBA", workspace_size, (0,0,0,255))

    y = 0
    for fn, i in images.items():
        workspace.alpha_composite(i, (0, y))
        y += i.height
        opts = imagedefs.all_images[fn]
        frames = opts["frames"]
        if frames > 255:
            frames = 255
        width = i.width // frames
        attributes[fn] = (width, i.height, frames, palnumber)

    #Debug:
    workspace.save(WORKDIR + "workspace%d-A.png" % palnumber)

    def fill_palette(palette):
        """If less that 256 colors, fill up to 255 with black + 1 magenta."""
        black = [0,0,0]
        magenta = [255,0,255]
        entries_missing = (765-len(palette))//3 
        return palette + entries_missing * black + magenta

    workspace_paletted = workspace.convert("RGB").quantize(dither=0, colors=255)
    palette = workspace_paletted.getpalette()
    #print("palette=", palette, len(palette), file=sys.stderr)

    full_palette = fill_palette(palette)
    #print("full_palette=", full_palette, len(full_palette), file=sys.stderr)


    #Debug:
    workspace_paletted.save(WORKDIR + "workspace%d-B.png" % palnumber)


    #print("unsigned long palette_pal[] PROGMEM = {")

    pal_raw = []
    with open(WORKDIR + "palette.pal", "wb") as palfile:
        for r, g, b in grouper(full_palette, 3):
            quad = bytearray((255, b, g, r))
            palfile.write(quad)
            #print("    0x%02x%02x%02x%02x," % (r, g, b, 255))
            pal_raw.append(quad)

    #print("};")
    #print()

    palettes.append(b"".join(pal_raw))

    y = 0
    for fn, i in images.items():
        print("processing", fn, file=sys.stderr)
        bitmask = ImageChops.invert(i.getchannel(3).convert("1"))
        i_paletted = workspace_paletted.crop((0, y, i.width, y + i.height))
        y += i.height
        i_paletted.paste(255, mask=bitmask)

        b = i_paletted.transpose(Image.ROTATE_270).tobytes()
        filename = fn.rsplit("/", 1)[-1]
        frames, palette = attributes[fn][2:4]
        width = i.width // frames
        if width > 255:
            width = 255
        attrs = (width, i.height, frames, palette)
        #print(filename, attrs)
        attrbytes = bytes(attrs)

        var_name = filename.replace(".", "_")
        if var_name.startswith("0") or var_name.startswith("1"):
            var_name = "_" + var_name
        print(var_name, "=", repr(attrbytes + b))
        #print("unsigned char %s[] PROGMEM = {" % var_name)
        for g in grouper(("0x%02x" % n for n in b), 8):
            #print("    " + ", ".join(g) + ",")
            pass
        #print("};")
        print()
        #rom_strips.append(struct.pack("<sx", var_name.encode("utf-8")) + attrbytes + b)
        rom_strips.append(var_name.encode("utf-8") + bytes(0) + attrbytes + b)
        
        if ("fondo.png" in fn):
            fn = WORKDIR + fn.rsplit(".", 1)[0] + ".raw"
            with open(fn, "wb") as raw:
                raw.write(b)
        else:
            raws.append(b)

print("palette_pal =", repr(b"".join(palettes)))
print()

with open(WORKDIR + "images.raw", "wb") as raw:
    raw.write(b"".join(raws))

with open(WORKDIR + "sprites.rom", "wb") as rom:
    offset = 4 + len(rom_strips) * 4 + len(palettes) * 4
    rom.write(struct.pack("<HH", len(rom_strips), len(palettes)))

    for strip in rom_strips:
        rom.write(struct.pack("<L", offset))
        offset += len(strip)
    for palette in palettes:
        rom.write(struct.pack("<L", offset))
        offset += len(palette)
        
    for strip in rom_strips:
        rom.write(strip)

    for palette in palettes:
        rom.write(palette)
