from PIL import Image
import os
import sys
from itertools import zip_longest, chain
import struct
import imagedefs

import matplotlib.image as mpimg
from numpy import sin, cos, pi, ndarray, array, uint8

TRANSPARENT = (255, 0, 255)
FOLDER = "../images"

def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)

def gamma(value, gamma=2.5, offset=0.5):
    assert 0 <= value <= 255
    return int( pow( float(value) / 255.0, gamma ) * 255.0 + offset )

def null_gamma(value):
    return value

"""
La funcion toma un archivo *.png y devuelve en binario (RGBI) la secuencia 
de n_leds prendidos para n_ang diferentes
"""
def reproject(image, n_led=54, n_ang=256):
    src = array(image)                    # Levanta la imagen
    dst = ndarray((n_led, n_ang, 3), uint8)        # Imagen de destino

    wx, wy, dim = src.shape         # Me da las dimensiones del frame en pixeles

    center_x = int((wx-1)/2)        # Calcula la cordenada x del centro de la imagen
    center_y = int((wy-1)/2)        # Calcula la cordenada y del centro de la imagen
    rad = min(center_x, center_y)   # Calcula el radio que barre la imagen dentro del frame

    #led = []
    
    intensidad = [ int(31 * i**2 / n_led**2) for i in range(n_led)]
    
    for m in range(0,n_ang):
        for n in range(0,n_led):
            x = center_x + int(rad * (n+1)/n_led * cos(m * 2*pi/n_ang)) 
            y = center_y + int(rad * (n+1)/n_led * sin(m * 2*pi/n_ang))
            #tupla_rgb = tuple(null_gamma(int(255 * g)) for g in src[x,y,0:3])
            dst[n, m] = src[x,y,0:3]

    return Image.fromarray(dst)


images_per_palette = {}

for filename, opts in imagedefs.all_images.items():
    palnumber = opts["palette"]
    images_per_palette.setdefault(palnumber, []).append(filename)

raws = []
sizes = []
rom_strips = []
palettes = []
attributes = {}

for palnumber, filenames in sorted(images_per_palette.items()):
    images = {}

    for f in filenames:
        image = Image.open(os.path.join(FOLDER, f)).convert("RGB")
        opts = imagedefs.all_images[f]
        if opts.get("process") == "reproject":
            image = reproject(image)
        images[f] = image

    #w_size = (sum(i.width for i in images) + 1, max(i.height for i in images) + 1)
    w_size = (max(i.width for i in images.values()) + 1, int(sum(i.height for i in images.values()) * 1.3))

    workspace = Image.new("RGB", w_size, (255,0,255))

    y = 0
    for fn, i in images.items():
        #workspace.paste(i, (x, 0, x+i.width, i.height))
        #x+=i.width
        workspace.paste(i, (0, y, i.width, y+i.height))
        y += i.height
        opts = imagedefs.all_images[fn]
        frames = opts["frames"]
        if frames > 255:
            frames = 255
        width = i.width // frames
        attributes[fn] = (width, i.height, frames, palnumber)

    #Debug:
    workspace.save(".output/workspace%d-A.png" % palnumber)

    import pprint
    workspace = workspace.convert("P", palette=Image.ADAPTIVE, dither=0, colors=256)
    palette = list(grouper(workspace.getpalette(), 3))
    #pprint.pprint(palette, stream=sys.stderr)
    mi = palette.index(TRANSPARENT)
    palorder = list(range(256))
    palorder[255] = mi
    palorder[mi] = 255
    workspace = workspace.remap_palette(palorder)
    #pprint.pprint(list(grouper(workspace.getpalette(), 3)), stream=sys.stderr)

    palette = list(grouper(workspace.getpalette(), 3))
    mi = palette.index(TRANSPARENT)
    print(palette, file=sys.stderr)
    print([n for n, c in enumerate(palette) if c in [(254, 0, 254), (255, 0, 255)]], file=sys.stderr)
    print(mi, file=sys.stderr)
    #import pdb; pdb.set_trace()
    for n, c in enumerate(palette):
        if (c == TRANSPARENT or c == (254, 0, 254)) and n != 255:
            palette[n] = (255, 0, 255)
    try:
        print("transparent index=", palette.index(TRANSPARENT), file=sys.stderr)
    except:
        print("no transparent in this palette", file=sys.stderr)
    workspace.putpalette(chain.from_iterable(palette))
    #Debug:
    workspace.save(".output/workspace%d-B.png" % palnumber)

    #print("unsigned long palette_pal[] PROGMEM = {")

    pal_raw = []
    with open(".output/palette.pal", "wb") as palfile:
        for c in palette:
            r, g, b = c
            #if (r, g, b) == TRANSPARENT:
                #r, g, b = 255, 255, 0
            #r, g, b = gamma(r), gamma(g), gamma(b)
            quad = bytearray((255, b, g, r))
            palfile.write(quad)
            #print("    0x%02x%02x%02x%02x," % (r, g, b, 255))
            pal_raw.append(quad)

    #print("};")
    #print()

    palettes.append(b"".join(pal_raw))

    for (j, (fn, i)) in enumerate(images.items()):
        p = i.quantize(palette=workspace, colors=256, method=Image.FASTOCTREE, dither=Image.NONE)
        #Debug:
        #p.save("debug/xx%02d.png" % j)
        b = p.transpose(Image.ROTATE_270).tobytes()
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
            fn = ".output/" + fn.rsplit(".", 1)[0] + ".raw"
            with open(fn, "wb") as raw:
                raw.write(b)
        else:
            raws.append(b)
            sizes.append(p.size)

print("palette_pal =", repr(b"".join(palettes)))
print()

with open(".output/images.raw", "wb") as raw:
    raw.write(b"".join(raws))

with open(".output/sprites.rom", "wb") as rom:
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
