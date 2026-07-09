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
u8  width               255 means 256 (fullscreen/planet strips)
u8  height
u8  frames              number of animation frames (builders clamp to 255)
u8  palette             palette group index this strip's pixels refer to
u8  pixels[width * height * frames]
```

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

The LittleFS image stores ROMs gzip-compressed as `<name>.rom.gz`
(hardware/rotor/build_micropython_fs.py); `director.load_rom()` looks for
the `.gz` first and inflates it in memory. The uncompressed container is
identical.
