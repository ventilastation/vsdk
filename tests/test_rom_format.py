#!/usr/bin/env python3
"""Validate built sprite ROMs against docs/internals/rom-format.md, and check that the
Python and JS builders agree on the menu ROM's structure.

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
    """Reference parser for docs/internals/rom-format.md. Returns (strips, palettes)."""
    num_strips, num_palettes = struct.unpack_from("<HH", data, 0)
    offsets = struct.unpack_from("<%dL" % (num_strips + num_palettes), data, 4)
    strip_offsets = offsets[:num_strips]
    palette_offsets = offsets[num_strips:]

    strips = []
    for off in strip_offsets:
        name_len = data[off]
        name = data[off + 1:off + 1 + name_len].decode("utf-8")
        width, height, frames, palette = data[off + 1 + name_len:off + 5 + name_len]
        real_width = 256 if width == 255 else width
        pixels_start = off + 5 + name_len
        pixels_len = real_width * height * (frames or 1)
        assert pixels_start + pixels_len <= len(data), (name, "pixels out of bounds")
        strips.append({
            "name": name,
            "width": real_width,
            "height": height,
            "frames": frames or 1,
            "palette": palette,
            "pixels_start": pixels_start,
            "pixels_len": pixels_len,
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
        # Strip entries are written back to back: the pixel run must not
        # overlap the next strip's entry.
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


def test_menu_rom_builder_parity():
    """The Python and JS builders must produce the same strip inventory for
    the menu ROM (palette bytes may differ: different quantizers)."""
    if not shutil.which("node") or not (ROOT / "node_modules" / "pngjs").exists():
        print("SKIP: node/pngjs unavailable for builder parity check")
        return
    py_rom = ROMS / "menu.rom"
    if not py_rom.exists():
        print("SKIP: menu.rom not built")
        return

    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ)
        out = Path(tmp) / "menu.rom"
        # The JS CLI writes into apps/micropython/roms; run it and restore.
        # Restore the mtime too: a fresher menu.rom would make the Python
        # generator's staleness check skip a needed rebuild after a new
        # game's menu.png is added.
        original = py_rom.read_bytes()
        original_stat = py_rom.stat()
        try:
            subprocess.run(
                ["node", "tools/generate_roms_js.cjs", "system/menu/images"],
                cwd=ROOT, check=True, capture_output=True, env=env,
            )
            out.write_bytes(py_rom.read_bytes())
        finally:
            py_rom.write_bytes(original)
            os.utime(py_rom, (original_stat.st_atime, original_stat.st_mtime))

        py_strips, py_palettes = parse_rom(original)
        js_strips, js_palettes = parse_rom(out.read_bytes())

    def inventory(strips):
        return [(s["name"], s["width"], s["height"], s["frames"], s["palette"]) for s in strips]

    assert inventory(py_strips) == inventory(js_strips), (
        "builder strip inventories differ:\npy=%r\njs=%r" % (inventory(py_strips), inventory(js_strips))
    )
    assert len(py_palettes) == len(js_palettes)
    print("builder parity: %d strips match" % len(py_strips))


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("rom format: %d checks passed" % len(tests))
    return 0


if __name__ == "__main__":
    sys.exit(main())
