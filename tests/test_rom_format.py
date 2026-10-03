#!/usr/bin/env python3
"""Validate built sprite ROMs against docs/internals/rom-format.md, and check that the
Python and JS builders write structurally identical ROMs.

    python3 tests/test_rom_format.py

The reference parser below implements the spec only from the document, so a
builder drifting from the format (or from the other builder) fails here.
"""

import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROMS = ROOT / "apps" / "micropython" / "roms"


def parse_rom(data):
    """Reference parser for docs/internals/rom-format.md. Returns (strips, palettes).

    Every strip record must be exactly its name, header, pixels and glyph
    trailer: a header that describes more or less than its record (the old
    255-means-256 width, a clamped frame count, a sheet that didn't divide
    into whole frames) fails here."""
    num_strips, num_palettes = struct.unpack_from("<HH", data, 0)
    offsets = struct.unpack_from("<%dL" % (num_strips + num_palettes), data, 4)
    strip_offsets = offsets[:num_strips]
    palette_offsets = offsets[num_strips:]

    strips = []
    for n, off in enumerate(strip_offsets):
        record_end = offsets[n + 1] if n + 1 < len(offsets) else len(data)
        name_len = data[off]
        name = data[off + 1:off + 1 + name_len].decode("utf-8")
        header = bytes(data[off + 1 + name_len:off + 5 + name_len])
        width_minus_1, height, frames_minus_1, palette = header
        width, frames = width_minus_1 + 1, frames_minus_1 + 1
        pixels_start = off + 5 + name_len
        pixels_len = width * height * frames
        trailer = pixels_start + pixels_len
        assert trailer + 2 <= record_end, (name, "record shorter than its header describes")
        glyph_len = struct.unpack_from("<H", data, trailer)[0]
        assert trailer + 2 + glyph_len == record_end, (
            name, "record is %d bytes, header and trailer describe %d"
            % (record_end - off, trailer + 2 + glyph_len - off))
        strips.append({
            "name": name,
            "header": header,
            "width": width,
            "height": height,
            "frames": frames,
            "palette": palette,
            "pixels_start": pixels_start,
            "pixels_len": pixels_len,
            "glyphs": bytes(data[trailer + 2:record_end]),
            "record_len": record_end - off,
        })

    palettes = []
    for n, off in enumerate(palette_offsets):
        end = palette_offsets[n + 1] if n + 1 < num_palettes else len(data)
        palettes.append(data[off:end])

    return strips, palettes


def validate_rom(path):
    data = path.read_bytes()
    strips, palettes = parse_rom(data)
    assert strips, f"{path.name}: no strips"
    assert palettes, f"{path.name}: no palettes"
    names = [s["name"] for s in strips]
    assert len(names) == len(set(names)), f"{path.name}: duplicate strip ids"
    for strip in strips:
        assert strip["palette"] < len(palettes), (path.name, strip["name"], "palette index out of range")
    for palette in palettes:
        assert len(palette) % 1024 == 0 and len(palette) >= 1024, (path.name, "palette size", len(palette))
        # Alpha byte first in every entry, always 0xFF.
        assert all(palette[i] == 0xFF for i in range(0, 1024, 4)), (path.name, "palette alpha")
    return strips, palettes


def test_all_built_roms():
    roms = sorted(ROMS.glob("*.rom"))
    if not roms:
        print("SKIP: no built ROMs (run make generate-roms)")
        return
    for rom in roms:
        validate_rom(rom)
    print("validated %d ROMs" % len(roms))


# The menu ROM (game_menu_strips expansion, many palettes' worth of icons)
# and the smallest ROM with glyph tables.
PARITY_TARGETS = ("system/menu/images", "games/alecu/vixeous/images")


def build_with_python(folder, out):
    sys.path.insert(0, str(ROOT / "tools"))
    import generate_roms
    spritedef = folder / generate_roms.STRIPEDEF_FILENAME
    rom = out / (generate_roms.rom_name_for_folder(folder) + ".rom")
    out.mkdir(parents=True, exist_ok=True)
    generate_roms.generate_rom(folder, generate_roms.load_palettegroups(spritedef), spritedef,
                               rom_filename=rom, force=True)
    return rom.name, rom.read_bytes()


def build_with_js(folder, out):
    subprocess.run(
        ["node", "tools/generate_roms_js.cjs", "--force", "--out", str(out), str(folder)],
        cwd=ROOT, check=True, capture_output=True,
    )
    (rom,) = out.glob("*.rom")
    return rom.name, rom.read_bytes()


def structure(data):
    """Everything about a ROM both builders must agree on byte for byte:
    each record's name, its raw header bytes (so an encoding drift on either
    side shows), its pixel and record lengths, and its glyph trailer. Pixel
    bytes themselves differ: the two builders quantize colors differently."""
    strips, palettes = parse_rom(data)
    return ([(s["name"], s["header"], s["pixels_len"], s["record_len"], s["glyphs"]) for s in strips],
            len(palettes))


def test_builder_parity():
    """The Python and JS builders produce structurally identical ROMs."""
    if not shutil.which("node") or not (ROOT / "node_modules" / "pngjs").exists():
        print("SKIP: node/pngjs unavailable for builder parity check")
        return
    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
    except ModuleNotFoundError as error:
        print("SKIP builder parity: missing", error.name)
        return
    for target in PARITY_TARGETS:
        folder = ROOT / target
        with tempfile.TemporaryDirectory() as tmp:
            py_name, py_rom = build_with_python(folder, Path(tmp) / "py")
            js_name, js_rom = build_with_js(folder, Path(tmp) / "js")
        assert py_name == js_name, (py_name, js_name)
        py_structure, js_structure = structure(py_rom), structure(js_rom)
        assert py_structure == js_structure, (
            "%s: builders disagree\npy=%r\njs=%r" % (target, py_structure, js_structure))
        glyph_strips = sum(1 for record in py_structure[0] if record[4])
        print("builder parity %s: %d strips match, %d with glyph tables"
              % (target, len(py_structure[0]), glyph_strips))


def test_builder_rejects_image_strip_cap():
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from PIL import Image
        import generate_roms
    except ModuleNotFoundError as error:
        print("SKIP builder cap check: missing", error.name)
        return

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        manifest = folder / "__images__.yaml"
        manifest.write_text("palettegroups: []\n")
        group = []
        for index in range(generate_roms.MAX_IMAGE_STRIPS + 1):
            name = "image%d.png" % index
            Image.new("RGBA", (1, 1), (0, 0, 0, 255)).save(folder / name)
            group.append((name, {"frames": 1}))
        try:
            generate_roms.generate_rom(folder, [group], manifest, folder / "too-many.rom")
        except ValueError as error:
            assert "defines 101 images; this target supports 100" in str(error), error
        else:
            raise AssertionError("ROM builder accepted more than 100 image strips")


def test_builder_rejects_unrepresentable_images():
    """Images no strip header can describe exactly are errors naming the
    file, not silent clamps."""
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from PIL import Image
        import generate_roms
    except ModuleNotFoundError as error:
        print("SKIP builder rejection check: missing", error.name)
        return

    cases = (
        ((256, 19), 5, "doesn't divide into 5 equal frames"),
        ((257, 4), 257, "declares 257 frames"),
        ((514, 4), 2, "257 px wide frames"),
        ((4, 256), 1, "256 px tall"),
    )
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        manifest = folder / "__images__.yaml"
        manifest.write_text("palettegroups: []\n")
        for size, frames, expected in cases:
            Image.new("RGBA", size, (0, 0, 0, 255)).save(folder / "sheet.png")
            try:
                generate_roms.generate_rom(folder, [[("sheet.png", {"frames": frames})]], manifest,
                                           folder / "out.rom", force=True)
            except ValueError as error:
                message = str(error)
                assert "sheet.png" in message and expected in message, message
            else:
                raise AssertionError("builder accepted %r with %d frames" % (size, frames))
        # The largest of each is fine: 256 wide, 256 frames, 255 tall.
        Image.new("RGBA", (256 * 2, 255), (0, 0, 0, 255)).save(folder / "sheet.png")
        generate_roms.generate_rom(folder, [[("sheet.png", {"frames": 2})]], manifest,
                                   folder / "ok.rom", force=True)
        Image.new("RGBA", (256, 1), (0, 0, 0, 255)).save(folder / "sheet.png")
        generate_roms.generate_rom(folder, [[("sheet.png", {"frames": 256})]], manifest,
                                   folder / "font.rom", force=True)
        (font,), _ = parse_rom((folder / "font.rom").read_bytes())
        assert (font["width"], font["frames"], font["header"][:3]) == (1, 256, bytes((0, 1, 255))), font


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("rom format: %d checks passed" % len(tests))
    return 0


if __name__ == "__main__":
    sys.exit(main())
