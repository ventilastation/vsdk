"""Board-side package code under the MicroPython unix port.

The CPython suites (test_vszip/test_menurom/test_installer) cover logic;
this one proves the same modules run on MicroPython itself -- the deflate
module (RAW members, GZIP roms), uos.ilistdir/statvfs, and dict/str
idioms. Fixtures are pre-built zips embedded as base64 because MicroPython
cannot create archives.

Run: micropython tests/test_installer_micropython.py   (from the repo root;
tests/run_tests.py does this automatically when micropython is on PATH)
"""

import binascii
import os
import struct
import sys

sys.path.insert(0, "apps/micropython")

from ventilastation import installer, menurom, vszip

# zip with DEFLATE (meta.json, code/big.py) + STORE (sounds/raw.mp3) members
ZIP_FIXTURE = binascii.a2b_base64(
    b"UEsDBBQAAAAIAAAAIQDNYCqOFgAAABQAAAAJAAAAbWV0YS5qc29uq1YqySzJSVWyUlBy"
    b"y6woKS1KVaoFAFBLAwQUAAAACAAAACEAB1NntlsBAAAAIAAACwAAAGNvZGUvYmlnLnB5"
    b"Y2BkYmZhZWPn4OTi5uHl4xcQFBIWERUTl5CUkpaRlZNXUFRSVlFVU9fQ1NLW0dXTNzA0"
    b"MjYxNTO3sLSytrG1s3dwdHJ2cXVz9/D08vbx9fMPCAwKDgkNC4+IjIqOiY2LT0hMSk5J"
    b"TUvPyMzKzsnNyy8oLCouKS0rr6isqq6pratvaGxqbmlta+/o7Oru6e3rnzBx0uQpU6dN"
    b"nzFz1uw5c+fNX7Bw0eIlS5ctX7Fy1eo1a9et37Bx0+YtW7dt37Fz1+49e/ftP3Dw0OEj"
    b"R48dP3Hy1OkzZ8+dv3Dx0uUrV69dv3Hz1u07d+/df/Dw0eMnT589f/Hy1es3b9+9//Dx"
    b"0+cvX799//Hz1+8/f//9Zxj1/6j/R/0/6v9R/4/6f9T/o/4f9f+o/0f9P+r/Uf+P+n/U"
    b"/6P+H/X/qP9H/T/q/1H/j/p/1P+j/h/1/6j/R/0/6v9R/4/6fxj4HwBQSwMEFAAAAAAA"
    b"AAAhAOI2g08QAAAAEAAAAA4AAABzb3VuZHMvcmF3Lm1wM0lEMyBzdG9yZWQgYnl0ZXNQ"
    b"SwECFAMUAAAACAAAACEAzWAqjhYAAAAUAAAACQAAAAAAAAAAAAAAgAEAAAAAbWV0YS5q"
    b"c29uUEsBAhQDFAAAAAgAAAAhAAdTZ7ZbAQAAACAAAAsAAAAAAAAAAAAAAIABPQAAAGNv"
    b"ZGUvYmlnLnB5UEsBAhQDFAAAAAAAAAAhAOI2g08QAAAAEAAAAA4AAAAAAAAAAAAAAIAB"
    b"wQEAAHNvdW5kcy9yYXcubXAzUEsFBgAAAAADAAMArAAAAP0BAAAAAA=="
)

# gzip of a menu rom holding strips "menu.png" + "alecu/vyruss_vs2/menu.png"
# sharing one palette (what a tree OTA would restore as roms/menu.rom.gz)
MENU_GZ_FIXTURE = binascii.a2b_base64(
    b"H4sIAAAAAAAC/+3YQQpAQACF4Tez0qxmyUI5AWXrMJJkwyTTKKfHxiX4v/rfIZ6VkZdU"
    b"PtPlUrZOIdVbmL33MgAAAAAA4POKYZnG1BznnmLsj9g27ztQVVYWAAD8zuWcI6J/dgMV"
    b"ynHsOxwAAA=="
)

# stripped package (.no-sound.vs2) for games/alecu/newgame: meta + code
# (DEFLATE), roms/alecu.newgame.rom.gz (STORE, 1177-byte rom inside),
# menu-icon.rom (strip "alecu/newgame/menu.png" + own palette)
STRIPPED_FIXTURE = binascii.a2b_base64(
    b"UEsDBBQAAAAIAAAAIQAR1m/fGgAAABoAAAAdAAAAZ2FtZXMvYWxlY3UvbmV3Z2FtZS9t"
    b"ZXRhLmpzb26rVkosyFSyUlAqKzZS0lFQyi9KSS0C8s1rAVBLAwQUAAAACAAAACEA8FPT"
    b"RxwAAAAcAAAAIwAAAGdhbWVzL2FsZWN1L25ld2dhbWUvY29kZS9uZXdnYW1lLnB5S0lN"
    b"U8hNzMzT0LTiUgCCotSS0qI8Bb/8vFQuAFBLAwQUAAAAAAAAACEAlUfzhjoAAAA6AAAA"
    b"GQAAAHJvbXMvYWxlY3UubmV3Z2FtZS5yb20uZ3ofiwgAAAAAAAL/Y2RgZOBhYGCYCcQc"
    b"xRmZBXoFeekcHEwMrAMM/ouIiIziUTyKRyYGABJtWoOZBAAAUEsDBBQAAAAIAAAAIQDQ"
    b"oSLVQwAAACcUAAANAAAAbWVudS1pY29uLnJvbe3DMQqAMBBFwR+0tLCyTmdnzhSWJY1Z"
    b"bILH13voG5ikpEXSvkpbPd1GCb9b7V66xziuaDnPmgAAAAAAwOc9Zkbyn19QSwECFAMU"
    b"AAAACAAAACEAEdZv3xoAAAAaAAAAHQAAAAAAAAAAAAAAgAEAAAAAZ2FtZXMvYWxlY3Uv"
    b"bmV3Z2FtZS9tZXRhLmpzb25QSwECFAMUAAAACAAAACEA8FPTRxwAAAAcAAAAIwAAAAAA"
    b"AAAAAAAAgAFVAAAAZ2FtZXMvYWxlY3UvbmV3Z2FtZS9jb2RlL25ld2dhbWUucHlQSwEC"
    b"FAMUAAAAAAAAACEAlUfzhjoAAAA6AAAAGQAAAAAAAAAAAAAAgAGyAAAAcm9tcy9hbGVj"
    b"dS5uZXdnYW1lLnJvbS5nelBLAQIUAxQAAAAIAAAAIQDQoSLVQwAAACcUAAANAAAAAAAA"
    b"AAAAAACAASMBAABtZW51LWljb24ucm9tUEsFBgAAAAAEAAQAHgEAAJEBAAAAAA=="
)

ROOT_DIR = "build/test_mp_root"


def _reset_root():
    installer._rmtree(ROOT_DIR)
    for path in ("build", ROOT_DIR, ROOT_DIR + "/roms"):
        try:
            os.mkdir(path)
        except OSError:
            pass


def _write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def test_vszip_reads_store_and_deflate():
    _reset_root()
    zip_path = ROOT_DIR + "/fixture.zip"
    _write(zip_path, ZIP_FIXTURE)
    reader = vszip.ZipReader(zip_path)
    assert reader.names() == ["code/big.py", "meta.json", "sounds/raw.mp3"], reader.names()
    assert reader.read("meta.json") == b'{"title": "Fixture"}'
    assert reader.read("code/big.py") == bytes(range(256)) * 32
    out_path = ROOT_DIR + "/raw.mp3"
    reader.extract("sounds/raw.mp3", out_path)
    assert _read(out_path) == b"ID3 stored bytes"
    reader.close()


def test_install_from_stripped_package():
    _reset_root()
    _write(ROOT_DIR + "/roms/menu.rom.gz", MENU_GZ_FIXTURE)
    package_path = ROOT_DIR + "/alecu.newgame.no-sound.vs2"
    _write(package_path, STRIPPED_FIXTURE)

    slug = installer.install_from_file(package_path, root=ROOT_DIR)

    assert slug == "alecu.newgame", slug
    assert _read(ROOT_DIR + "/games/alecu/newgame/meta.json") == b'{"api": "vs2", "order": 7}'
    assert _read(ROOT_DIR + "/games/alecu/newgame/code/newgame.py").startswith(b"def main()")
    assert _exists(ROOT_DIR + "/roms/alecu.newgame.rom.gz")
    # Icon merged: plain menu rom written, the shadowing .gz dropped.
    assert not _exists(ROOT_DIR + "/roms/menu.rom.gz")
    menu = _read(ROOT_DIR + "/roms/menu.rom")
    strips, palettes = menurom.parse(menu)
    names = [strip[0] for strip in strips]
    assert b"alecu/newgame/menu.png" in names, names
    assert len(palettes) == 2, len(palettes)


def test_reinstall_replaces_previous_version():
    # Continues from the previous test's tree: plant a stale file and rerun.
    stale = ROOT_DIR + "/games/alecu/newgame/code/stale.py"
    _write(stale, b"OLD = True\n")
    slug = installer.install_from_file(
        ROOT_DIR + "/alecu.newgame.no-sound.vs2", root=ROOT_DIR)
    assert slug == "alecu.newgame"
    assert not _exists(stale)
    assert _exists(ROOT_DIR + "/games/alecu/newgame/code/newgame.py")
    # Re-merging the same icon must not grow the menu rom's palette count.
    strips, palettes = menurom.parse(_read(ROOT_DIR + "/roms/menu.rom"))
    assert len(palettes) == 2, len(palettes)


def main():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    installer._rmtree(ROOT_DIR)
    print("installer micropython: %d checks passed" % len(tests))
    return 0


if __name__ == "__main__":
    sys.exit(main())
