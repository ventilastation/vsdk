# Sprite ROM container format

Normative spec for the `.rom` files produced by `tools/generate_roms.py`
(Python/Pillow), `tools/generate_roms_js.cjs` + `web/rom-builder-core.js`
(Node/browser), and consumed by `ventilastation/director.py` on every
platform. `tests/test_rom_format.py` validates both builders against this
document. All integers are little-endian and offsets are absolute file
offsets.

## Layout

```
+--------------------------------------------------------------+
| u16 num_strips | u16 num_palettes                             |
| u32 strip_offset  × num_strips                                |
| u32 palette_offset × num_palettes                             |
| strip entries…                                                |
| palettes…                                                     |
+--------------------------------------------------------------+
```

Strips are written back-to-back in offset order, then palettes. The first
palette offset therefore also marks the end of strip data; the director's
streaming loader relies on that to slice `palette_data`.

## Strip entry

```
u8  name_len
u8  name[name_len]      strip id, UTF-8; e.g. "alecu/vyruss/menu.png"
u8  width - 1           width of one frame, 1..256 (256: full circle)
u8  height              0..255, stored as is
u8  frames - 1          number of animation frames, 1..256
u8  palette             palette group index this strip's pixels refer to
u8  pixels[width * height * frames]
u16 glyphs_len          length of the glyph table; 0 when there is none
u8  glyphs[glyphs_len]  UTF-8: the table's nth character draws frame n (VS2 labels)
```

A record is exactly these fields, so its length always follows from its
header, and the next strip's offset (or the first palette's) is where it
ends. `tests/test_rom_format.py`'s reference parser rejects any record that
isn't exact.

Width and frame count are stored minus one so that every byte value means
one number and 256 fits: no reader needs a special case for a full-circle
image or a 256-glyph font. Height is stored as is: 255 is a real height in
use, there is no 256 to represent, and it is the multiplier in the pixel
addressing, where a missed `+1` would corrupt every strip instead of
clipping one column. Readers decode through one helper per runtime:
`strip_frame_width()` / `strip_total_frames()` in C (the struct fields are
named `frame_width_minus_1` / `total_frames_minus_1` so a raw read stands
out), `ventilastation/romformat.py` in MicroPython,
`povrender.decode_strip_header` in the desktop emulator and
`decodeImageStripPayload` in the web emulator.

The builders reject what a header can't describe exactly, naming the file:
frame counts outside 1..256, frames wider than 256, heights outside 1..255,
and sheets whose width isn't a whole number of frames.

### ROMs from before this encoding

Older ROMs stored width 256 as 255, frame counts as is (256-glyph fonts
clamped to 255, 0 read as 1) and the glyph trailer only sometimes.
`romformat.resolve()` still loads them: it tries the current reading first,
then the older ones, and keeps the one that accounts for the record's length
exactly -- which also tells a full-circle image (byte 255, 256 wide) from the
two genuinely 255-wide images, and a clamped font from a real 255-frame
strip. The director and `menurom.py` hand every strip on with the current
header, so renderers only ever see one encoding, and game packages installed
before the change keep working.

The strip id is what game code looks up in `director.stripes` after
`load_rom()`. Builders derive it from the `id:` field in
`__images__.yaml`, defaulting to the image's basename; the
`game_menu_strips: true` expansion uses `<group>/<name>/menu.png`.

## Pixel data

One byte per pixel: an index into the strip's palette group. `0xFF` is
transparent and is never drawn (the quantizers reserve it).

Ordering is column-major with frames outermost, matching the renderers'
addressing `pixel = pixels[frame*width*height + column*height + row]`:
the source image (all frames side by side horizontally) is rotated 270°
before serialization, so each column is stored bottom-to-top as the
rotation leaves it.

## Palettes

Each palette is 256 entries × 4 bytes = 1024 bytes. Entry byte order as
written by the builders is `FF BB GG RR` (alpha always 0xFF); consumers
byte-swap into whatever their renderer needs. A strip's effective color
for index `i` is palette entry `i` of palette group `palette` (renderers
address a concatenated palette block as `i + 256*palette`). Entry 255 is
conventionally magenta and unused because index 0xFF means transparent.

## On-flash variant

The LittleFS image stores ROMs compressed as `<name>.romz`
(`hardware/rotor/build_micropython_fs.py`'s `compress_sprite_rom()`):

```
+--------------------------------------------------+
| u32 uncompressed_size                             |
| gzip data (the container above, compressed)       |
+--------------------------------------------------+
```

`director.load_rom()` looks for the `.romz` first, reads the size, and
inflates directly into one preallocated buffer via
`deflate.DeflateIO.readinto()` -- knowing the size upfront avoids
`DeflateIO.read()`'s unsized read, which reallocates and copies repeatedly
as the result grows. `menurom.py`'s `roms/menu.romz` uses the same format.
The uncompressed container is otherwise identical.

MSX cartridge/BIOS dumps (`roms/msx/*.rom`, `retro-go/bios/msx/*.rom`) are
a separate case: fMSX reads those directly as a bare gzip stream (via
zlib's `gzFile`), so they keep the old plain-gzip `.rom.gz` form with no
size prefix -- see `build_micropython_fs.py`'s `is_sprite_rom_path()`.
