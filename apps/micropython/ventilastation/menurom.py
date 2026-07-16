"""Board-side maintenance of the monolithic menu rom.

The launcher renders every menu icon from one rom (roms/menu.rom, built by
tools/generate_roms.py from the repo tree), so a game installed as a .vs2
package would have no icon. Each package ships a one-strip menu-icon.rom
(the icon plus its palette); merge_icon() splices it into the menu rom at
install time, replacing the strip when a game is re-installed.

The board cannot gzip-compress, so the merged rom is written as a plain
roms/menu.rom and the tree's roms/menu.rom.gz is deleted afterwards --
director.load_rom() prefers the .gz, so leaving it would shadow the merge.
That preference is also the staleness signal: a system OTA restores
menu.rom.gz, and refresh_from_packages() (run at boot) notices it, re-merges
every stored package's icon into the fresh tree rom, and drops the .gz
again. No network involved: the icon roms live in /packages.

Container layout per docs/internals/rom-format.md.
"""

import struct

try:
    import uos as os
except ImportError:
    import os

from ventilastation import vszip

ROMS_DIR = "/roms"
PACKAGES_DIR = "/packages"
PACKAGE_SUFFIX = ".no-sound.vs2"
ICON_MEMBER = "menu-icon.rom"


def parse(data):
    """Split a rom into ([name, palette_index, strip_blob], ...) and raw
    palette blobs. Strip blobs cover name_len..pixels, sized from the strip
    header itself (width byte 255 means 256)."""
    num_strips, num_palettes = struct.unpack_from("<HH", data, 0)
    offsets = struct.unpack_from("<%dL" % (num_strips + num_palettes), data, 4)

    strips = []
    for off in offsets[:num_strips]:
        name_len = data[off]
        name = bytes(data[off + 1:off + 1 + name_len])
        attrs = off + 1 + name_len
        width = data[attrs]
        height = data[attrs + 1]
        frames = data[attrs + 2] or 1
        palette = data[attrs + 3]
        real_width = 256 if width == 255 else width
        blob_len = 5 + name_len + real_width * height * frames
        strips.append([name, palette, bytes(data[off:off + blob_len])])

    palettes = []
    palette_offsets = offsets[num_strips:]
    for n, off in enumerate(palette_offsets):
        end = palette_offsets[n + 1] if n + 1 < num_palettes else len(data)
        palettes.append(bytes(data[off:end]))
    return strips, palettes


def serialize(strips, palettes):
    offset = 4 + 4 * (len(strips) + len(palettes))
    offsets = []
    for _name, _pal, blob in strips:
        offsets.append(offset)
        offset += len(blob)
    for palette in palettes:
        offsets.append(offset)
        offset += len(palette)
    parts = [struct.pack("<HH", len(strips), len(palettes))]
    parts.append(struct.pack("<%dL" % len(offsets), *offsets))
    for _name, _pal, blob in strips:
        parts.append(blob)
    parts.extend(palettes)
    return b"".join(parts)


def _with_palette(blob, palette_index):
    """Copy of a strip blob with its palette attribute byte rewritten."""
    patched = bytearray(blob)
    patched[4 + patched[0]] = palette_index
    return bytes(patched)


def merge_icon(menu_data, icon_data):
    """Return menu_data with every strip of icon_data spliced in
    (replace-by-name or append), each with its own palette. Unreferenced
    palettes are dropped afterwards so re-installs don't grow the rom."""
    strips, palettes = parse(menu_data)
    icon_strips, icon_palettes = parse(icon_data)
    if not icon_strips:
        raise ValueError("icon rom has no strips")

    for name, icon_pal, blob in icon_strips:
        new_index = len(palettes)
        palettes.append(icon_palettes[icon_pal])
        entry = [name, new_index, _with_palette(blob, new_index)]
        for i, strip in enumerate(strips):
            if strip[0] == name:
                strips[i] = entry
                break
        else:
            strips.append(entry)

    used = sorted(set(strip[1] for strip in strips))
    remap = {old: new for new, old in enumerate(used)}
    palettes = [palettes[old] for old in used]
    for strip in strips:
        new_index = remap[strip[1]]
        if new_index != strip[1]:
            strip[1] = new_index
            strip[2] = _with_palette(strip[2], new_index)
    return serialize(strips, palettes)


def _gunzip_file(path):
    with open(path, "rb") as f:
        try:
            import deflate
            stream = deflate.DeflateIO(f, deflate.GZIP)
            try:
                return stream.read()
            finally:
                stream.close()
        except ImportError:
            import zlib
            return zlib.decompress(f.read(), 47)


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def load_menu_rom(roms_dir=ROMS_DIR):
    """Current menu rom bytes, preferring the tree's .gz like the director
    does. Returns (data, from_gz)."""
    gz_path = roms_dir + "/menu.rom.gz"
    if _exists(gz_path):
        return _gunzip_file(gz_path), True
    with open(roms_dir + "/menu.rom", "rb") as f:
        return f.read(), False


def _write_menu_rom(data, roms_dir, drop_gz):
    tmp_path = roms_dir + "/menu.rom.tmp"
    with open(tmp_path, "wb") as f:
        f.write(data)
    os.rename(tmp_path, roms_dir + "/menu.rom")
    if drop_gz:
        try:
            os.remove(roms_dir + "/menu.rom.gz")
        except OSError:
            pass


def merge_icon_into_menu(icon_data, roms_dir=ROMS_DIR):
    menu_data, from_gz = load_menu_rom(roms_dir)
    _write_menu_rom(merge_icon(menu_data, icon_data), roms_dir, drop_gz=from_gz)


def refresh_from_packages(packages_dir=PACKAGES_DIR, roms_dir=ROMS_DIR):
    """Re-merge stored package icons after a system OTA restored
    roms/menu.rom.gz. Cheap no-op (two stats) on a normal boot. Returns True
    when a re-merge happened."""
    if not _exists(roms_dir + "/menu.rom.gz"):
        return False
    try:
        packages = [
            name for name in os.listdir(packages_dir)
            if name.endswith(PACKAGE_SUFFIX)
        ]
    except OSError:
        return False
    if not packages:
        return False

    menu_data = _gunzip_file(roms_dir + "/menu.rom.gz")
    for name in sorted(packages):
        try:
            with vszip.ZipReader(packages_dir + "/" + name) as package:
                if package.exists(ICON_MEMBER):
                    menu_data = merge_icon(menu_data, package.read(ICON_MEMBER))
        except Exception as e:
            print("menurom: skipping icon from", name, ":", e)
    _write_menu_rom(menu_data, roms_dir, drop_gz=True)
    return True
