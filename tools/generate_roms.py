import os
import sys
import struct

from pathlib import Path
from itertools import zip_longest, chain
from numpy import sin, cos, pi, ndarray, array, uint8
from PIL import Image, ImageChops

TRANSPARENT = (255, 0, 255)
ROOT_FOLDER = "../apps/images"
ROMS_FOLDER = "../apps/micropython/roms"

os.makedirs(ROMS_FOLDER, exist_ok=True)

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

    for m in range(0,n_ang):
        for n in range(0,n_led):
            x = center_x + int(rad * (n+1)/n_led * cos(m * 2*pi/n_ang)) 
            y = center_y + int(rad * (n+1)/n_led * sin(m * 2*pi/n_ang))
            dst[n, m] = src[x,y,0:4]

    return Image.fromarray(dst)


#vugo [[
# ('moregrass.png', {'frames': 4}), 
# ('monchito_runs.png', {'frames': 4}), 
# ('obstacles.png', {'frames': 2}), 
# ('bushes.png', {'frames': 4}), 
# ('nube8bit.png', {'frames': 1}), 
# ('bluesky.png', {'frames': 1, 'radius': 54, 'process': 'reproject'})]]


def generate_rom(folder, palettegroups):
    rom_name = folder.parts[-1]
    rom_filename = Path(ROMS_FOLDER) / (rom_name + ".rom")
    rom_timestamp = rom_filename.stat().st_mtime if rom_filename.exists() else 0
    src_filenames = (folder / filename for group in palettegroups for filename, _ in group)

    if all(f.stat().st_mtime <= rom_timestamp for f in src_filenames):
        print("Skipping", rom_name, file=sys.stderr)
        return
    print("Generating", rom_name, file=sys.stderr)

    rom_strips = []
    palettes = []
    attributes = {}

    for palnumber, group in enumerate(palettegroups):
        images = {}
        images_opts = {}

        for filename, file_opts in group:
            image = Image.open(folder / filename).convert("RGBA")
            if file_opts.get("process") == "reproject":
                print("    Reprojecting", filename, file=sys.stderr)
                image = reproject(image, n_led=file_opts["radius"])
            images[filename] = image
            images_opts[filename] = file_opts

        workspace_size = (
            max(i.width for i in images.values()),
            sum(i.height for i in images.values())
        )

        workspace = Image.new("RGBA", workspace_size, (0,0,0,255))

        y = 0
        for fn, i in images.items():
            workspace.alpha_composite(i, (0, y))
            y += i.height
            opts = images_opts[fn]
            frames = opts["frames"]
            if frames > 255:
                frames = 255
            width = i.width // frames
            attributes[fn] = (width, i.height, frames, palnumber)

        def fill_palette(palette):
            """If less that 256 colors, fill up to 255 with black + 1 magenta."""
            black = [0,0,0]
            magenta = [255,0,255]
            entries_missing = (765-len(palette))//3 
            return palette + entries_missing * black + magenta

        workspace_paletted = workspace.convert("RGB").quantize(dither=0, colors=255)
        palette = workspace_paletted.getpalette()

        full_palette = fill_palette(palette)


        pal_raw = []
        for r, g, b in grouper(full_palette, 3):
            quad = bytearray((255, b, g, r))
            pal_raw.append(quad)


        palettes.append(b"".join(pal_raw))

        y = 0
        for fn, i in images.items():
            print("    Processing", fn, file=sys.stderr)
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
            attrbytes = bytes(attrs)

            var_name = filename.rsplit(".", 1)[0].replace(".", "_") + "_data"
            if var_name.startswith("0") or var_name.startswith("1"):
                var_name = "_" + var_name

            fnb = filename.encode("utf-8")
            pascal_filename = struct.pack("B", len(fnb)) + fnb
            rom_strips.append(pascal_filename + attrbytes + b)
        
    with open(rom_filename, "wb") as rom:
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



STRIPEDEF_FILENAME = "stripedefs.py"

def palettegroup(*items):
    return list(items)

def strip(filename, frames=1):
    return filename, dict(frames=frames)

def fullscreen(filename, radius=54):
    return filename, dict(frames=1, radius=radius, process="reproject")

for root, dirs, files in Path(ROOT_FOLDER).walk(on_error=print):
    if STRIPEDEF_FILENAME in files:
        stripedef = open(root / STRIPEDEF_FILENAME).read()
        parsed = exec(stripedef)
        generate_rom(root, stripes)
