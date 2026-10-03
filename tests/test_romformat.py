"""ventilastation/romformat.py and the director's ROM loading.

Plain asserts so it runs on the MicroPython unix port too, where romformat
runs on the board:

    python3 tests/test_romformat.py
    micropython tests/test_romformat.py

ROMs are built in the test, in the current encoding (romformat itself) and
in the one before it (by hand), so nothing depends on apps/micropython/roms.
"""

import os
import struct
import sys

sys.path.insert(0, "apps/micropython")

if sys.implementation.name != "micropython":
    import random
    import time

    class _Utime:
        ticks_ms = staticmethod(lambda: int(time.time() * 1000))
        ticks_add = staticmethod(lambda value, delta: value + delta)
        ticks_diff = staticmethod(lambda end, start: end - start)
        sleep_ms = staticmethod(lambda ms: time.sleep(ms / 1000.0))

    sys.modules.setdefault("uos", os)
    sys.modules.setdefault("urandom", random)
    sys.modules.setdefault("utime", _Utime)

from ventilastation import romformat
from ventilastation.director import configure_runtime, director, reset_runtime


def raises(exception, function, *args):
    try:
        function(*args)
    except exception as error:
        return str(error)
    raise AssertionError("%s not raised" % exception.__name__)


# --- headers ---------------------------------------------------------------

def test_header_round_trips_every_width_and_frame_count():
    for value in (1, 2, 128, 254, 255, 256):
        header = romformat.encode_header(value, 8, value, 3)
        assert len(header) == 4
        assert romformat.decode_header(header) == (value, 8, value, 3), value


def test_header_bytes_are_value_minus_one():
    assert romformat.encode_header(255, 8, 255, 0) == bytes((254, 8, 254, 0))
    assert romformat.encode_header(256, 8, 256, 0) == bytes((255, 8, 255, 0))
    assert romformat.encode_header(1, 0, 1, 255) == bytes((0, 0, 0, 255))


def test_height_is_stored_as_is():
    assert romformat.encode_header(4, 255, 1, 0)[1] == 255
    assert romformat.decode_header(bytes((3, 255, 0, 0)))[1] == 255


def test_out_of_range_headers_are_rejected():
    for args in ((0, 8, 1, 0), (257, 8, 1, 0), (8, 8, 0, 0), (8, 8, 257, 0),
                 (8, 256, 1, 0), (8, 8, 1, 256)):
        raises(ValueError, romformat.encode_header, *args)


# --- records ---------------------------------------------------------------

def body_of(record):
    """(header, body) of a record built by encode_record or legacy_record."""
    name_len = record[0]
    return record[1 + name_len:5 + name_len], record[5 + name_len:]


def resolve_record(record):
    header, body = body_of(record)
    return romformat.resolve(header, len(body), lambda offset: struct.unpack_from("<H", body, offset)[0])


def legacy_record(name, width, height, frames, pixels=None, trailer=None, header=None):
    """A record as ROMs built before the current encoding wrote it."""
    if header is None:
        header = bytes((255 if width == 256 else width, height, min(frames, 255), 0))
    if pixels is None:
        pixels = bytes(width * height * frames)
    tail = b"" if trailer is None else struct.pack("<H", len(trailer)) + trailer
    return bytes((len(name),)) + name + header + pixels + tail


def test_current_records_resolve():
    for width, frames, glyphs in ((8, 1, b""), (255, 1, b""), (256, 1, b""),
                                  (9, 256, b""), (9, 255, b""), (8, 3, "éAB".encode("utf-8"))):
        record = romformat.encode_record(b"s.png", width, 16, frames, 2,
                                         bytes(width * 16 * frames), glyphs)
        assert resolve_record(record) == (width, 16, frames, 2, len(glyphs)), (width, frames)


def test_older_full_circle_strip_is_256_wide():
    assert resolve_record(legacy_record(b"planet.png", 256, 25, 1)) == (256, 25, 1, 0, None)
    assert resolve_record(legacy_record(b"planet.png", 256, 25, 1, trailer=b"")) == (256, 25, 1, 0, 0)


def test_older_genuinely_255_wide_strip_is_255_wide():
    # warning.png in 2bam_sencom: the width byte said 255, and every reader
    # took that as 256 and read 8 bytes past it.
    record = legacy_record(b"warning.png", 255, 8, 1, trailer=b"")
    assert resolve_record(record) == (255, 8, 1, 0, 0)


def test_older_clamped_256_glyph_font_has_all_256_frames():
    record = legacy_record(b"vga_cp437.png", 9, 16, 256, trailer=b"")
    assert resolve_record(record) == (9, 16, 256, 0, 0)


def test_older_genuine_255_frame_strip_keeps_255():
    record = legacy_record(b"tinyfont_menu.png", 4, 6, 255, trailer=b"")
    assert resolve_record(record) == (4, 6, 255, 0, 0)


def test_older_glyph_table_is_kept():
    record = legacy_record(b"font.png", 8, 8, 10, trailer=b"0123456789")
    assert resolve_record(record) == (8, 8, 10, 0, 10)


def test_older_zero_frames_meant_one():
    record = legacy_record(b"x.png", 4, 4, 1, header=bytes((4, 4, 0, 0)))
    assert resolve_record(record) == (4, 4, 1, 0, None)


def test_older_sheet_with_leftover_columns_keeps_its_frames():
    # pollitos.png: 256 px for five 51 px frames; one column left over.
    pixels = bytes(256 * 19)
    record = legacy_record(b"pollitos.png", 51, 19, 5, pixels=pixels, trailer=b"")
    assert resolve_record(record) == (51, 19, 5, 0, None)


def test_a_record_shorter_than_its_header_is_an_error():
    record = legacy_record(b"cut.png", 8, 8, 4, pixels=bytes(8 * 8 * 2))
    message = raises(ValueError, resolve_record, record)
    assert "does not match" in message, message


def test_resolve_in_reads_a_record_in_place():
    record = romformat.encode_record(b"a.png", 4, 2, 3, 1, bytes(24), b"xy")
    data = b"\x00" * 7 + record
    assert romformat.resolve_in(data, 7 + 1 + 5, len(data)) == (4, 2, 3, 1, 2)


# --- loading ROMs ----------------------------------------------------------

def build_rom(records, palette_count=1):
    offset = 4 + 4 * (len(records) + palette_count)
    offsets = []
    for record in records:
        offsets.append(offset)
        offset += len(record)
    for _ in range(palette_count):
        offsets.append(offset)
        offset += 1024
    return (struct.pack("<HH", len(records), palette_count)
            + struct.pack("<%dL" % len(offsets), *offsets)
            + b"".join(records) + b"\xff" * (1024 * palette_count))


FIXTURE = (
    # (name, width, height, frames, glyphs)
    (b"wide255.png", 255, 8, 1, b""),
    (b"wide256.png", 256, 8, 1, b""),
    (b"font256.png", 9, 16, 256, b""),
    (b"font255.png", 9, 16, 255, b"ab"),
)


def current_rom():
    return build_rom([romformat.encode_record(name, w, h, f, 0, bytes([n + 1]) * (w * h * f), g)
                      for n, (name, w, h, f, g) in enumerate(FIXTURE)])


def legacy_rom():
    return build_rom([legacy_record(name, w, h, f, pixels=bytes([n + 1]) * (w * h * f),
                                    trailer=g if g else None)
                      for n, (name, w, h, f, g) in enumerate(FIXTURE)])


def load(rom, streaming):
    runtime = None
    reset_runtime()
    runtime = configure_runtime("headless")
    runtime.platform.disable_gc = not streaming
    path = "/tmp/vsdk_test_romformat.rom"
    with open(path, "wb") as f:
        f.write(rom)
    try:
        director.load_rom(path)
    finally:
        os.remove(path)
    return runtime


def check_loaded(runtime, label):
    metadata = director.image_metadata
    backend = runtime.platform.sprites
    for n, (name, width, height, frames, glyphs) in enumerate(FIXTURE):
        entry = metadata[n]
        assert (entry["width"], entry["height"], entry["frames"]) == (width, height, frames), (label, name, entry)
        # Every strip reaches the renderers with the current header.
        assert romformat.decode_header(backend.stripes[n]) == (width, height, frames, 0), (label, name)
        sprite = backend.Sprite()
        sprite.set_strip(n)
        # The V1 API keeps reporting a full-circle image as 255 wide.
        assert sprite.width() == min(width, 255), (label, name, sprite.width())
    assert metadata[3]["glyphs"] == "ab", (label, metadata[3]["glyphs"])
    strip = director._stripe_buffers[1]
    assert len(strip) == 4 + 256 * 8, (label, len(strip))
    assert bytes(strip[4:6]) == b"\x02\x02", label


def test_director_loads_current_roms():
    for streaming in (True, False):
        check_loaded(load(current_rom(), streaming), "current streaming=%s" % streaming)


def test_director_loads_older_roms():
    for streaming in (True, False):
        check_loaded(load(legacy_rom(), streaming), "older streaming=%s" % streaming)


def test_director_names_the_rom_and_strip_of_a_corrupt_record():
    rom = build_rom([legacy_record(b"cut.png", 8, 8, 4, pixels=bytes(8 * 8 * 2))])
    for streaming in (True, False):
        message = raises(ValueError, load, rom, streaming)
        assert "cut.png" in message and ".rom" in message and "rebuild" in message, message


def main():
    tests = [(name, value) for name, value in sorted(globals().items()) if name.startswith("test_")]
    for name, test in tests:
        test()
        print("ok", name)
    print("romformat: %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
