import gzip
import io
import json
import pathlib
import struct
import sys
import tempfile
import unittest
import unittest.mock
import urllib.error
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "emulator"))
sys.path.insert(0, str(ROOT / "apps" / "micropython"))
sys.path.insert(0, str(ROOT / "tests"))

import package_manager
import upgrade_server
from test_menurom import build_palette, build_rom, icon_fixture

SLUG = "alecu.testgame"


def make_package_bytes(slug=SLUG, code=b"def main():\n    return None\n",
                       with_rom=True, extra_members=()):
    out = io.BytesIO()
    name = slug.split(".", 1)[1]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("meta.json", json.dumps({"api": "vs2", "title": "Test Game"}))
        archive.writestr("menu.png", b"\x89PNG fake")
        archive.writestr("code/%s.py" % name, code)
        if with_rom:
            rom = build_rom([("ship.png", 8, 8, 2, 0, 5)], [build_palette(20)])
            archive.writestr("roms/%s.rom" % slug, rom)
        archive.writestr("menu-icon.rom",
                         icon_fixture(name=slug.replace(".", "/") + "/menu.png"))
        info = zipfile.ZipInfo("sounds/blip.mp3")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, b"ID3 fake mp3 bytes")
        for member, data in extra_members:
            archive.writestr(member, data)
    return out.getvalue()


class DevicePathTests(unittest.TestCase):
    """upgrade_server's _device_path()/_file_entry() drive the system OTA
    manifest; a sprite rom must get the same length-prefixed ".romz" form
    build_micropython_fs.py flashes, so a dev-loop OTA and a fresh flash
    agree byte-for-byte. MSX cartridge/BIOS dumps keep the old bare-gzip
    ".rom.gz" form, since fMSX reads those directly via zlib's gzFile."""

    def test_sprite_rom_gets_length_prefixed_romz(self):
        rom = build_rom([("ship.png", 8, 8, 2, 0, 5)], [build_palette(20)])
        with tempfile.TemporaryDirectory() as tmp:
            rom_path = pathlib.Path(tmp) / "alecu.testgame.rom"
            rom_path.write_bytes(rom)

            remote_path = "roms/alecu.testgame.rom"
            device_path = upgrade_server._device_path(remote_path)
            self.assertEqual(device_path, "roms/alecu.testgame.romz")

            entry = upgrade_server._file_entry(device_path, remote_path, rom_path)
            self.assertIsNotNone(entry["gz"])
            size = struct.unpack("<I", entry["gz"][:4])[0]
            self.assertEqual(size, len(rom))
            self.assertEqual(gzip.decompress(entry["gz"][4:]), rom)
            self.assertEqual(entry["size"], len(entry["gz"]))

    def test_msx_rom_keeps_bare_gzip(self):
        with tempfile.TemporaryDirectory() as tmp:
            rom_path = pathlib.Path(tmp) / "game.rom"
            rom_path.write_bytes(b"fake msx cartridge dump")

            remote_path = "roms/msx/game.rom"
            device_path = upgrade_server._device_path(remote_path)
            self.assertEqual(device_path, "roms/msx/game.rom.gz")

            entry = upgrade_server._file_entry(device_path, remote_path, rom_path)
            self.assertEqual(gzip.decompress(entry["gz"]), b"fake msx cartridge dump")


class PackageServerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = pathlib.Path(self._tmp.name)
        self._patches = [
            unittest.mock.patch.object(
                package_manager, "PACKAGES_DIR", tmp / "installed_packages"),
            unittest.mock.patch.object(
                package_manager, "BOARD_FILES_DIR", tmp / "board_files"),
            unittest.mock.patch.object(upgrade_server, "_register_mdns",
                                       lambda port: None),
            # HTTPServer.server_bind resolves the machine's FQDN, which can
            # block ~5s per server on macOS reverse-DNS; irrelevant here.
            unittest.mock.patch("socket.getfqdn", lambda name="": "localhost"),
        ]
        for patch in self._patches:
            patch.start()
        package_manager.install_status.clear()
        package_manager._active_slug = None
        upgrade_server.trigger_install = None
        upgrade_server.on_package_saved = None
        self.server = upgrade_server.start(port=0)
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        for patch in self._patches:
            patch.stop()
        self._tmp.cleanup()

    def _post(self, path, data=b""):
        request = urllib.request.Request(self.base + path, data=data, method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()

    def _get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as response:
            return response.status, response.read()

    def _upload(self, data=None):
        return self._post("/packages/%s.vs2" % SLUG, data or make_package_bytes())

    def test_upload_stores_package_and_lists_it(self):
        status, body = self._upload()
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])
        self.assertTrue(package_manager.package_path(SLUG).is_file())

        _status, body = self._get("/packages")
        listing = json.loads(body)["packages"]
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["slug"], SLUG)
        self.assertEqual(listing[0]["title"], "Test Game")
        self.assertEqual(listing[0]["status"]["state"], "uploaded")

    def test_upload_calls_saved_hook(self):
        calls = []
        upgrade_server.on_package_saved = calls.append
        self._upload()
        self.assertEqual(calls, [SLUG])

    def test_upload_rejects_bad_member(self):
        bad = make_package_bytes(extra_members=[("images/sprite.png", b"png")])
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._upload(bad)
        self.assertEqual(ctx.exception.code, 400)
        self.assertIn("unexpected member", ctx.exception.read().decode())

    def test_upload_rejects_rom_slug_mismatch(self):
        bad = make_package_bytes(extra_members=[("roms/other.game.rom", b"rom")])
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._upload(bad)
        self.assertEqual(ctx.exception.code, 400)

    def test_board_file_member_set_and_transform(self):
        self._upload()
        status, body = self._get("/packages/%s.no-sound.vs2" % SLUG)
        self.assertEqual(status, 200)

        with zipfile.ZipFile(io.BytesIO(body)) as stripped:
            names = sorted(stripped.namelist())
            self.assertEqual(names, [
                "games/alecu/testgame/code/testgame.py",
                "games/alecu/testgame/meta.json",
                "menu-icon.rom",
                "roms/%s.romz" % SLUG,
            ])
            rom_info = stripped.getinfo("roms/%s.romz" % SLUG)
            self.assertEqual(rom_info.compress_type, zipfile.ZIP_STORED)
            original_rom = build_rom([("ship.png", 8, 8, 2, 0, 5)],
                                     [build_palette(20)])
            payload = stripped.read(rom_info)
            size = struct.unpack("<I", payload[:4])[0]
            self.assertEqual(size, len(original_rom))
            self.assertEqual(gzip.decompress(payload[4:]), original_rom)

        # Serving the board file marks the install as being fetched.
        self.assertEqual(package_manager.get_install_status(SLUG)["state"],
                         "serving")
        # And the HTTP body matches what trigger_install hashes.
        data, sha, size = package_manager.get_board_file(SLUG)
        self.assertEqual(data, body)
        self.assertEqual(size, len(body))
        self.assertEqual(len(sha), 64)

    def test_reupload_invalidates_board_file_cache(self):
        self._upload()
        _status, first = self._get("/packages/%s.no-sound.vs2" % SLUG)
        self._upload(make_package_bytes(code=b"def main():\n    return 42\n"))
        _status, second = self._get("/packages/%s.no-sound.vs2" % SLUG)
        self.assertNotEqual(first, second)
        with zipfile.ZipFile(io.BytesIO(second)) as stripped:
            self.assertIn(b"return 42",
                          stripped.read("games/alecu/testgame/code/testgame.py"))

    def test_install_endpoint_without_board_link_is_503(self):
        self._upload()
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post("/packages/%s/install" % SLUG)
        self.assertEqual(ctx.exception.code, 503)

    def test_install_endpoint_triggers_hook_and_status_flows(self):
        self._upload()
        triggered = []

        def fake_trigger(slug):
            triggered.append(slug)
            package_manager.note_install_triggered(slug)

        upgrade_server.trigger_install = fake_trigger
        status, body = self._post("/packages/%s/install" % SLUG)
        self.assertEqual(status, 200)
        self.assertEqual(triggered, [SLUG])
        self.assertEqual(json.loads(body)["state"], "triggered")

        # Board-side lines (relayed by comms.py) advance the status record.
        package_manager.note_install_progress("downloading", "pkg", "40")
        record = json.loads(self._get("/packages/%s/status" % SLUG)[1])
        self.assertEqual(record["state"], "installing")
        self.assertEqual(record["stage"], "downloading")

        package_manager.note_install_done(SLUG)
        record = json.loads(self._get("/packages/%s/status" % SLUG)[1])
        self.assertEqual(record["state"], "done")

    def test_install_endpoint_unknown_package_is_404(self):
        upgrade_server.trigger_install = lambda slug: None
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post("/packages/no.such/install")
        self.assertEqual(ctx.exception.code, 404)

    def test_serves_the_editor_index(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"<", body[:200])

    def test_listdir_lists_tree_game_sounds(self):
        status, body = self._get("/api/listdir?path=games/alecu/vyruss_vs2/sounds")
        self.assertEqual(status, 200)
        names = [entry["name"] for entry in json.loads(body)["entries"]]
        self.assertIn("shoot1.mp3", names)

    def test_listdir_rejects_paths_outside_games_and_system(self):
        for bad in ("emulator", "..", "games/../emulator", ""):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self._get("/api/listdir?path=" + bad)
            self.assertEqual(ctx.exception.code, 400, bad)

    def test_safe_relative_path_blocks_traversal(self):
        self.assertIsNone(upgrade_server._safe_relative_path("/a/../../b"))
        self.assertEqual(upgrade_server._safe_relative_path("/a/./b//c"),
                         ["a", "b", "c"])

    def test_manifest_and_files_endpoints_still_work(self):
        # One stub file instead of the real LFS set: hashing/gzipping the
        # whole tree takes over a minute and is not what's under test here
        # (the routing around the new endpoints is).
        sample = pathlib.Path(self._tmp.name) / "sample.py"
        sample.write_bytes(b"print('hi')\n")
        with unittest.mock.patch.object(
                upgrade_server, "_lfs_files",
                lambda: [("sample.py", sample)]):
            status, body = self._get("/manifest")
            self.assertEqual(status, 200)
            manifest = json.loads(body)
            self.assertEqual(manifest["files"][0]["path"], "sample.py")
            status, body = self._get("/files/sample.py")
            self.assertEqual(status, 200)
            self.assertEqual(body, b"print('hi')\n")


if __name__ == "__main__":
    unittest.main()
