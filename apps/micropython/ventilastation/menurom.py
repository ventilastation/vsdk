"""Board-side maintenance of the monolithic menu rom.

The launcher renders every menu icon from one rom (roms/menu.rom, built by
tools/generate_roms.py from the repo tree), so a game installed as a .vs2
package would have no icon. Each package ships a one-strip menu-icon.rom
(the icon plus its palette); merge_icon() splices it into the menu rom at
install time, replacing the strip when a game is re-installed.

The board cannot gzip-compress, so the merged rom is written as a plain
roms/menu.rom and the tree's roms/menu.romz is deleted afterwards --
director.load_rom() prefers the .romz, so leaving it would shadow the merge.
That preference is also the staleness signal: a system OTA restores
menu.romz, and refresh_from_packages() (run at boot) notices it, re-merges
every stored package's icon into the fresh tree rom, and drops the .romz
again. No network involved: the icon roms live in /packages.

Container layout per docs/internals/rom-format.md.
"""

import struct

try:
    import uos as os
except ImportError:
    import os

from ventilastation import romformat
from ventilastation import vszip

ROMS_DIR = "/roms"
PACKAGES_DIR = "/packages"
PACKAGE_SUFFIX = ".no-sound.vs2"
ICON_MEMBER = "menu-icon.rom"


def parse(data):
    """Split a rom into ([name, palette_index, strip_record], ...) and raw
    palette blobs. Each strip record is complete (name, header, pixels and
    glyph trailer) and in the current encoding: a record from a rom built
    before it (an older package's icon) is re-encoded, so a merged menu rom
    never mixes encodings."""
    num_strips, num_palettes = struct.unpack_from("<HH", data, 0)
    offsets = struct.unpack_from("<%dL" % (num_strips + num_palettes), data, 4)

    strips = []
    for n in range(num_strips):
        off = offsets[n]
        # The next strip, or the first palette.
        record_end = offsets[n + 1] if n + 1 < len(offsets) else len(data)
        name_len = data[off]
        name = bytes(data[off + 1:off + 1 + name_len])
        header_start = off + 1 + name_len
        width, height, frames, palette, glyph_length = romformat.resolve_in(
            data, header_start, record_end)
        record = bytes(data[off:record_end])
        if record[1 + name_len:5 + name_len] != romformat.encode_header(width, height, frames, palette):
            pixels_start = header_start + romformat.HEADER_SIZE
            pixels_end = pixels_start + romformat.pixel_length(width, height, frames)
            glyphs = b""
            if glyph_length:
                glyphs_start = pixels_end + romformat.TRAILER_SIZE
                glyphs = bytes(data[glyphs_start:glyphs_start + glyph_length])
            record = romformat.encode_record(
                name, width, height, frames, palette, data[pixels_start:pixels_end], glyphs)
        strips.append([name, palette, record])

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
    """Inflate a ".romz" file: a little-endian uint32 uncompressed size
    followed by gzip data (see build_micropython_fs.py). Knowing the size
    upfront lets this read into one preallocated buffer via readinto()
    instead of DeflateIO.read()'s unsized read."""
    with open(path, "rb") as f:
        size = struct.unpack("<I", f.read(4))[0]
        try:
            import deflate
        except ImportError:
            import zlib
            return zlib.decompress(f.read(), 47)
        buffer = bytearray(size)
        stream = deflate.DeflateIO(f, deflate.GZIP)
        try:
            stream.readinto(buffer)
        finally:
            stream.close()
        return buffer


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def load_menu_rom(roms_dir=ROMS_DIR):
    """Current menu rom bytes, preferring the tree's .romz like the director
    does. Returns (data, from_romz)."""
    romz_path = roms_dir + "/menu.romz"
    if _exists(romz_path):
        return _gunzip_file(romz_path), True
    with open(roms_dir + "/menu.rom", "rb") as f:
        return f.read(), False


def _write_menu_rom(data, roms_dir, drop_romz):
    tmp_path = roms_dir + "/menu.rom.tmp"
    with open(tmp_path, "wb") as f:
        f.write(data)
    os.rename(tmp_path, roms_dir + "/menu.rom")
    if drop_romz:
        try:
            os.remove(roms_dir + "/menu.romz")
        except OSError:
            pass


def merge_icon_into_menu(icon_data, roms_dir=ROMS_DIR):
    menu_data, from_romz = load_menu_rom(roms_dir)
    _write_menu_rom(merge_icon(menu_data, icon_data), roms_dir, drop_romz=from_romz)


def refresh_from_packages(packages_dir=PACKAGES_DIR, roms_dir=ROMS_DIR):
    """Re-merge stored package icons after a system OTA restored
    roms/menu.romz. Cheap no-op (two stats) on a normal boot. Returns True
    when a re-merge happened."""
    if not _exists(roms_dir + "/menu.romz"):
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

    menu_data = _gunzip_file(roms_dir + "/menu.romz")
    for name in sorted(packages):
        try:
            with vszip.ZipReader(packages_dir + "/" + name) as package:
                if package.exists(ICON_MEMBER):
                    menu_data = merge_icon(menu_data, package.read(ICON_MEMBER))
        except Exception as e:
            print("menurom: skipping icon from", name, ":", e)
    _write_menu_rom(menu_data, roms_dir, drop_romz=True)
    return True
