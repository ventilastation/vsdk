"""Minimal zip reader for .vs2 game packages.

Runs on both MicroPython (the board's installer) and CPython (tests and
host tools). Covers only what the packaging pipeline emits: STORE and
DEFLATE members, no zip64, no encryption, sizes taken from the central
directory (so data-descriptor members work too). DEFLATE members inflate
through the `deflate` module on MicroPython (raw window) or zlib on
CPython.
"""

import struct

try:
    import deflate as _deflate
except ImportError:
    _deflate = None
    import zlib

_EOCD_SIG = b"PK\x05\x06"
_CDH_SIG = b"PK\x01\x02"
_LFH_SIG = b"PK\x03\x04"
# EOCD record (22 bytes) plus the longest possible trailing comment.
_EOCD_MAX_SCAN = 22 + 65535

STORED = 0
DEFLATED = 8


class ZipError(Exception):
    pass


class _ZlibStream:
    """CPython stand-in for deflate.DeflateIO over a raw-deflate member."""

    def __init__(self, fileobj, comp_size):
        self._f = fileobj
        self._obj = zlib.decompressobj(-15)
        self._remaining = comp_size
        self._buf = b""

    def read(self, n):
        while len(self._buf) < n:
            if not self._remaining:
                self._buf += self._obj.flush()
                break
            chunk = self._f.read(min(4096, self._remaining))
            if not chunk:
                break
            self._remaining -= len(chunk)
            self._buf += self._obj.decompress(chunk)
        out = self._buf[:n]
        self._buf = self._buf[n:]
        return out


class ZipReader:
    """Read-only access to a zip archive's members.

    entries: name -> (method, comp_size, uncomp_size, local_header_offset)
    """

    def __init__(self, path):
        self._f = open(path, "rb")
        try:
            self.entries = self._read_central_directory()
        except Exception:
            self._f.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self._f.close()

    def _read_central_directory(self):
        f = self._f
        f.seek(0, 2)
        file_size = f.tell()
        tail_len = min(file_size, _EOCD_MAX_SCAN)
        f.seek(file_size - tail_len)
        tail = f.read(tail_len)
        pos = tail.rfind(_EOCD_SIG)
        if pos < 0:
            raise ZipError("end of central directory not found")
        total_entries = struct.unpack_from("<H", tail, pos + 10)[0]
        cd_size, cd_offset = struct.unpack_from("<LL", tail, pos + 12)

        f.seek(cd_offset)
        cd = f.read(cd_size)
        entries = {}
        off = 0
        for _ in range(total_entries):
            if cd[off:off + 4] != _CDH_SIG:
                raise ZipError("bad central directory entry")
            flags, method = struct.unpack_from("<HH", cd, off + 8)
            if flags & 0x1:
                raise ZipError("encrypted members not supported")
            comp_size, uncomp_size = struct.unpack_from("<LL", cd, off + 20)
            name_len, extra_len, comment_len = struct.unpack_from("<HHH", cd, off + 28)
            header_offset = struct.unpack_from("<L", cd, off + 42)[0]
            name = cd[off + 46:off + 46 + name_len].decode("utf-8")
            if method not in (STORED, DEFLATED):
                raise ZipError("unsupported compression method %d for %s" % (method, name))
            entries[name] = (method, comp_size, uncomp_size, header_offset)
            off += 46 + name_len + extra_len + comment_len
        return entries

    def names(self):
        return sorted(self.entries)

    def exists(self, name):
        return name in self.entries

    def size(self, name):
        return self.entries[name][2]

    def _seek_member_data(self, name):
        method, comp_size, uncomp_size, header_offset = self.entries[name]
        f = self._f
        f.seek(header_offset)
        header = f.read(30)
        if header[:4] != _LFH_SIG:
            raise ZipError("bad local header for %s" % name)
        name_len, extra_len = struct.unpack_from("<HH", header, 26)
        f.seek(header_offset + 30 + name_len + extra_len)
        return method, comp_size, uncomp_size

    def _member_chunks(self, name, chunk_size):
        method, comp_size, uncomp_size = self._seek_member_data(name)
        if method == STORED:
            remaining = comp_size
            while remaining:
                chunk = self._f.read(min(chunk_size, remaining))
                if not chunk:
                    raise ZipError("truncated member %s" % name)
                remaining -= len(chunk)
                yield chunk
            return
        if _deflate is not None:
            # wbits must be explicit: for RAW streams MicroPython defaults
            # to a 256-byte window, far smaller than the 32 KiB window zip
            # writers deflate with -- a back-reference past the window makes
            # the read raise EINVAL.
            stream = _deflate.DeflateIO(self._f, _deflate.RAW, 15)
        else:
            stream = _ZlibStream(self._f, comp_size)
        remaining = uncomp_size
        while remaining:
            chunk = stream.read(min(chunk_size, remaining))
            if not chunk:
                raise ZipError("truncated member %s" % name)
            remaining -= len(chunk)
            yield chunk

    def read(self, name, chunk_size=4096):
        """Whole member as bytes; suits small members (meta, icon roms)."""
        return b"".join(self._member_chunks(name, chunk_size))

    def extract(self, name, out_path, chunk_size=4096):
        """Stream a member to out_path (parent dirs must already exist)."""
        with open(out_path, "wb") as out:
            for chunk in self._member_chunks(name, chunk_size):
                out.write(chunk)
        return self.entries[name][2]
