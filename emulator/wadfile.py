"""Minimal Doom WAD reader.

Just enough to enumerate lumps and pull their raw bytes out of an IWAD/PWAD so we
can extract Doom sound effects (DS* lumps) and music (D_* lumps). No external deps.

WAD layout (little-endian):
  Header (12 bytes): 4-byte magic ("IWAD"/"PWAD"), int32 numlumps, int32 infotableofs
  Directory (numlumps * 16 bytes), each entry:
    int32 filepos, int32 size, 8-byte name (NUL-padded, uppercase ASCII)
"""

import struct


class WAD:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.data = f.read()

        magic, numlumps, infotableofs = struct.unpack_from("<4sii", self.data, 0)
        if magic not in (b"IWAD", b"PWAD"):
            raise ValueError("not a WAD file: %r" % (magic,))

        self.magic = magic
        # name -> (filepos, size); later duplicates win (matches WAD override order)
        self._dir = {}
        self._order = []
        for i in range(numlumps):
            filepos, size, raw_name = struct.unpack_from(
                "<ii8s", self.data, infotableofs + i * 16
            )
            name = raw_name.split(b"\x00", 1)[0].decode("ascii", "replace").upper()
            self._dir[name] = (filepos, size)
            self._order.append(name)

    def has(self, name):
        return name.upper() in self._dir

    def lump(self, name):
        """Return the raw bytes of a lump, or None if absent."""
        entry = self._dir.get(name.upper())
        if entry is None:
            return None
        filepos, size = entry
        return self.data[filepos:filepos + size]

    def names(self):
        """All lump names, in directory order (may contain duplicates)."""
        return list(self._order)

    def names_with_prefix(self, prefix):
        """Unique lump names starting with `prefix` (e.g. 'DS' or 'D_')."""
        prefix = prefix.upper()
        seen = []
        for name in self._dir:  # dict keys are unique
            if name.startswith(prefix):
                seen.append(name)
        return sorted(seen)
