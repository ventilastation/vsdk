import os
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))

from ventilastation import vszip


def _write_zip(path, members, compression=zipfile.ZIP_DEFLATED):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data, *rest in members:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = rest[0] if rest else compression
            archive.writestr(info, data)


class ZipReaderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _path(self, name="test.zip"):
        return os.path.join(self.tmp, name)

    def test_reads_stored_and_deflated_members(self):
        big = bytes(range(256)) * 64  # 16 KiB, spans several read chunks
        members = [
            ("meta.json", b'{"title": "Test"}', zipfile.ZIP_DEFLATED),
            ("sounds/blip.mp3", b"ID3fake-mp3-bytes", zipfile.ZIP_STORED),
            ("roms/big.rom", big, zipfile.ZIP_DEFLATED),
        ]
        _write_zip(self._path(), members)

        with vszip.ZipReader(self._path()) as reader:
            self.assertEqual(
                reader.names(), ["meta.json", "roms/big.rom", "sounds/blip.mp3"])
            self.assertTrue(reader.exists("meta.json"))
            self.assertFalse(reader.exists("missing"))
            self.assertEqual(reader.size("roms/big.rom"), len(big))
            self.assertEqual(reader.read("meta.json"), b'{"title": "Test"}')
            self.assertEqual(reader.read("sounds/blip.mp3"), b"ID3fake-mp3-bytes")
            self.assertEqual(reader.read("roms/big.rom"), big)

    def test_extract_streams_to_file(self):
        payload = b"x" * 10000
        _write_zip(self._path(), [("code/game.py", payload)])
        out_path = os.path.join(self.tmp, "game.py")

        with vszip.ZipReader(self._path()) as reader:
            written = reader.extract("code/game.py", out_path, chunk_size=1024)

        self.assertEqual(written, len(payload))
        with open(out_path, "rb") as f:
            self.assertEqual(f.read(), payload)

    def test_members_read_in_any_order(self):
        _write_zip(self._path(), [("a", b"first"), ("b", b"second" * 2000)])
        with vszip.ZipReader(self._path()) as reader:
            self.assertEqual(reader.read("b"), b"second" * 2000)
            self.assertEqual(reader.read("a"), b"first")
            self.assertEqual(reader.read("b"), b"second" * 2000)

    def test_rejects_non_zip(self):
        with open(self._path(), "wb") as f:
            f.write(b"definitely not a zip archive")
        with self.assertRaises(vszip.ZipError):
            vszip.ZipReader(self._path())

    def test_rejects_unsupported_compression(self):
        with zipfile.ZipFile(self._path(), "w", zipfile.ZIP_BZIP2) as archive:
            archive.writestr("member", b"data")
        with self.assertRaises(vszip.ZipError):
            vszip.ZipReader(self._path())

    def test_zip_with_comment(self):
        _write_zip(self._path(), [("member", b"data")])
        with zipfile.ZipFile(self._path(), "a") as archive:
            archive.comment = b"trailing comment " * 10
        with vszip.ZipReader(self._path()) as reader:
            self.assertEqual(reader.read("member"), b"data")


if __name__ == "__main__":
    unittest.main()
