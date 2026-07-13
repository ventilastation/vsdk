import importlib.util
import json
import os
import pathlib
import socket
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "micropython"))


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


upgrade_server = _load_module("upgrade_server", ROOT / "emulator" / "upgrade_server.py")
import updater  # noqa: E402  (needs apps/micropython on sys.path, set above)


class BundleServerSpecialCharsTests(unittest.TestCase):
    """Reproduces a real bug: filenames with spaces/parens/commas (e.g. many
    console ROM names) broke http.server's own request-line parsing when the
    device built the request from a raw, unencoded path -- a literal space
    in the request line is indistinguishable from the whitespace that
    separates METHOD/PATH/VERSION, so the server rejected it with a 400
    before ever reaching application code. Fixed by percent-encoding on the
    client (updater._url_quote) and decoding on the server (do_GET)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        bundle_dir = pathlib.Path(self.tmp.name)
        (bundle_dir / "files" / "roms" / "sms").mkdir(parents=True)
        self.filename = "After Burner (World).zip"
        self.file_rel_path = "roms/sms/" + self.filename
        (bundle_dir / "files" / self.file_rel_path).write_bytes(b"fake rom bytes")

        manifest = {
            "files": [{"path": self.file_rel_path, "size": 14, "sha256": "x"}],
            "partitions": {},
        }
        (bundle_dir / "manifest.json").write_text(json.dumps(manifest))

        self.server = upgrade_server.start(port=0, bundle_dir=str(bundle_dir))
        self.port = self.server.server_address[1]
        time.sleep(0.1)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        upgrade_server._unregister_mdns()
        self.tmp.cleanup()

    def _fetch(self, url):
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read()

    def _raw_get(self, path, host="127.0.0.1"):
        # Bypasses http.client's own client-side URL validation (which
        # would refuse to even send a request containing a raw space) to
        # reproduce exactly what updater.py's hand-rolled socket code sends:
        # "GET %s HTTP/1.0\r\nHost: %s\r\n\r\n" % (path, host).
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((host, self.port))
        s.send(("GET %s HTTP/1.0\r\nHost: %s\r\n\r\n" % (path, host)).encode())
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        s.close()
        return data

    def test_unencoded_space_gets_rejected_with_400(self):
        # This is what updater.py used to send before the fix: the raw path
        # embedded directly in the request line, exactly reproducing the
        # reported bug ("Bad request syntax") via a raw socket -- Python's
        # own http.client refuses to even construct such a request, unlike
        # updater.py's hand-rolled socket code, which sent it as-is.
        response = self._raw_get("/files/" + self.file_rel_path)
        self.assertIn(b"400", response.split(b"\r\n")[0])

    def test_client_quoted_path_succeeds(self):
        # This is what updater.py sends now: _url_quote()'d, matching
        # exactly what a real device does in _sync_lfs_files().
        url = "http://127.0.0.1:%d/files/%s" % (self.port, updater._url_quote(self.file_rel_path))
        status, body = self._fetch(url)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"fake rom bytes")

    def test_comma_and_multiple_parens_also_succeed(self):
        bundle_dir = pathlib.Path(self.tmp.name)
        rel = "roms/sms/Asterix (Europe) (En,Fr) (Rev 1).zip"
        (bundle_dir / "files" / rel).write_bytes(b"asterix bytes")
        manifest = {
            "files": [
                {"path": self.file_rel_path, "size": 14, "sha256": "x"},
                {"path": rel, "size": 13, "sha256": "y"},
            ],
            "partitions": {},
        }
        (bundle_dir / "manifest.json").write_text(json.dumps(manifest))

        url = "http://127.0.0.1:%d/files/%s" % (self.port, updater._url_quote(rel))
        status, body = self._fetch(url)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"asterix bytes")


class MdnsAdvertisementTests(unittest.TestCase):
    """upgrade_server.start() advertises ventilastation-base.local over mDNS
    so the desktop dev loop works without any manual dns-sd/avahi-publish
    step -- a production base gets this for free from Avahi once its OS
    hostname is set, but a dev machine's own Bonjour name is whatever its
    computer name already is."""

    def tearDown(self):
        upgrade_server._unregister_mdns()

    def test_missing_zeroconf_warns_and_does_not_crash(self):
        original = upgrade_server.Zeroconf
        upgrade_server.Zeroconf = None
        try:
            upgrade_server._register_mdns(5653)  # must not raise
            self.assertIsNone(upgrade_server._mdns_zc)
        finally:
            upgrade_server.Zeroconf = original

    @unittest.skipUnless(
        importlib.util.find_spec("zeroconf") is not None,
        "zeroconf not installed in this interpreter",
    )
    def test_registers_and_unregisters_a_real_service(self):
        upgrade_server._register_mdns(5653)
        try:
            self.assertIsNotNone(upgrade_server._mdns_zc)
            self.assertEqual(upgrade_server._mdns_info.port, 5653)
            self.assertEqual(upgrade_server._mdns_info.server, "ventilastation-base.local.")
        finally:
            upgrade_server._unregister_mdns()
        self.assertIsNone(upgrade_server._mdns_zc)
        self.assertIsNone(upgrade_server._mdns_info)


if __name__ == "__main__":
    unittest.main()
