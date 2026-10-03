"""Strip records in a sprite ROM (docs/internals/rom-format.md).

A strip record is a length-prefixed name, a 4-byte header, the pixel data
and a glyph trailer. The header is (width - 1, height, frames - 1,
palette): width and frame count run 1..256 and are stored minus one, so
every byte value means exactly one number, and no reader needs a special
case for a full-circle (256 wide) image or a 256-glyph font. Height is
stored as is. The width * height * frames pixel bytes are followed by a
little-endian u16 glyph-table length and that many UTF-8 bytes (zero
length when the strip has no glyph table).

ROMs built before that encoding stored width 256 as 255, frame counts as
is (a 256-glyph font clamped to 255) and the trailer only sometimes.
resolve() recognises those from the record's length, so a game package
installed before the change keeps loading. The director and menurom.py
decode every record through here and hand on strips with the current
header, so the renderers only ever see one encoding.

vsdk_ota_rings.py builds its strips by hand and deliberately doesn't import
this module (it must work with an empty filesystem); keep its header
literals in step with encode_header().
"""

import struct

HEADER_SIZE = 4
TRAILER_SIZE = 2  # the u16 glyph-table length
MAX_WIDTH = 256
MAX_FRAMES = 256


def encode_header(width, height, frames, palette):
    """The 4 header bytes for a strip of `frames` frames of width x height."""
    if not 1 <= width <= MAX_WIDTH:
        raise ValueError("width %d is outside 1..%d" % (width, MAX_WIDTH))
    if not 0 <= height <= 255:
        raise ValueError("height %d is outside 0..255" % height)
    if not 1 <= frames <= MAX_FRAMES:
        raise ValueError("%d frames is outside 1..%d" % (frames, MAX_FRAMES))
    if not 0 <= palette <= 255:
        raise ValueError("palette %d is outside 0..255" % palette)
    return bytes((width - 1, height, frames - 1, palette))


def decode_header(header):
    """(width, height, frames, palette) from a strip's 4 header bytes."""
    return header[0] + 1, header[1], header[2] + 1, header[3]


def pixel_length(width, height, frames):
    return width * height * frames


def _trailer_glyph_length(pixels, body_length, read_u16):
    """The glyph-table length when a trailer right after `pixels` bytes of
    pixel data accounts for the rest of the record exactly, else None."""
    if body_length < pixels + TRAILER_SIZE:
        return None
    glyph_length = body_length - pixels - TRAILER_SIZE
    if read_u16(pixels) != glyph_length:
        return None
    return glyph_length


def resolve(header, body_length, read_u16):
    """Decode one strip record, in the current encoding or the older one.

    header is the record's 4 header bytes, body_length the number of bytes
    after them up to the next record (or the palettes), and read_u16(offset)
    the little-endian u16 at that offset from the end of the header.

    Returns (width, height, frames, palette, glyph_length), where
    glyph_length is None when the record has no glyph trailer. Raises
    ValueError when no encoding accounts for the record.
    """
    width_byte, height, frames_byte, palette = header[0], header[1], header[2], header[3]

    width, frames = width_byte + 1, frames_byte + 1
    glyph_length = _trailer_glyph_length(width * height * frames, body_length, read_u16)
    if glyph_length is not None:
        return width, height, frames, palette, glyph_length

    # The older encoding. Width byte 255 meant 256 (planets, backdrops),
    # except in the two genuinely 255-wide images; frames byte 255 meant 255,
    # except in every 256-glyph font, which was clamped. Only the record's
    # length tells them apart, so try each reading against it.
    widths = (256, 255) if width_byte == 255 else (width_byte,)
    frame_counts = (255, 256) if frames_byte == 255 else (frames_byte or 1,)
    for width in widths:
        for frames in frame_counts:
            pixels = width * height * frames
            if body_length == pixels:
                return width, height, frames, palette, None
            glyph_length = _trailer_glyph_length(pixels, body_length, read_u16)
            if glyph_length is not None:
                return width, height, frames, palette, glyph_length

    # Older still: a sheet whose width wasn't a whole number of frames kept
    # its leftover columns after the frames, so the record holds more than
    # the header describes. The described frames are all there.
    width, frames = widths[0], frame_counts[0]
    if width > 0 and width * height * frames <= body_length:
        return width, height, frames, palette, None
    raise ValueError(
        "strip header (%d, %d, %d) does not match its %d-byte record"
        % (width_byte, height, frames_byte, body_length))


def resolve_in(data, header_start, record_end):
    """resolve() for a record held in memory: its header starts at
    header_start in data and the record ends at record_end."""
    body_start = header_start + HEADER_SIZE
    return resolve(
        data[header_start:body_start],
        record_end - body_start,
        lambda offset: struct.unpack_from("<H", data, body_start + offset)[0],
    )


def encode_record(name, width, height, frames, palette, pixels, glyphs=b""):
    """A complete strip record in the current encoding."""
    return b"".join((
        bytes((len(name),)),
        name,
        encode_header(width, height, frames, palette),
        bytes(pixels),
        struct.pack("<H", len(glyphs)),
        bytes(glyphs),
    ))
