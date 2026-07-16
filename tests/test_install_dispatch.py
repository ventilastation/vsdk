"""installer.run(): the /install_request boot path, with the frozen updater
module's network helpers faked out (same pattern as test_updater.py)."""

import hashlib
import os
import sys
import tempfile
import types
import unittest
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from ventilastation import installer
from test_installer import write_stripped_package


def _install_fake_updater(payload, resolved_suffix=""):
    fake = types.ModuleType("updater")
    fake.calls = []

    def _wifi_connect():
        fake.calls.append("wifi_connect")
        return True

    def _wifi_disconnect():
        fake.calls.append("wifi_disconnect")

    def _resolve_base_url(url):
        fake.calls.append("resolve")
        return url + resolved_suffix

    def _http_stream(url, callback, total_size):
        fake.calls.append(("get", url))
        for offset in range(0, len(payload), 1024):
            callback(payload[offset:offset + 1024])
            yield min(100, (offset + 1024) * 100 // max(total_size, 1))

    fake._wifi_connect = _wifi_connect
    fake._wifi_disconnect = _wifi_disconnect
    fake._resolve_base_url = _resolve_base_url
    fake._http_stream = _http_stream
    sys.modules["updater"] = fake
    return fake


class InstallerRunTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.packages_dir = os.path.join(self._tmp.name, "packages")
        source = write_stripped_package(
            os.path.join(self._tmp.name, "source.no-sound.vs2"))
        with open(source, "rb") as f:
            self.payload = f.read()
        self.sha = hashlib.sha256(self.payload).hexdigest()
        self.sent = []
        self._patches = [
            unittest.mock.patch.object(installer, "PACKAGES_DIR", self.packages_dir),
        ]
        for patch in self._patches:
            patch.start()

    def tearDown(self):
        for patch in self._patches:
            patch.stop()
        sys.modules.pop("updater", None)
        self._tmp.cleanup()

    def _send(self, line):
        self.sent.append(bytes(line))

    def _request(self, sha=None, size=None):
        return "http://base:5653/packages/alecu.testgame.no-sound.vs2 %s %d" % (
            sha or self.sha, len(self.payload) if size is None else size)

    def test_downloads_verifies_installs_and_reports_done(self):
        fake = _install_fake_updater(self.payload)
        installed = []
        with unittest.mock.patch.object(
                installer, "install_from_file",
                lambda path: installed.append(path) or "alecu.testgame"):
            ok = installer.run(self._request(), self._send)

        self.assertTrue(ok)
        expected_path = os.path.join(
            self.packages_dir, "alecu.testgame.no-sound.vs2")
        self.assertEqual(installed, [expected_path])
        with open(expected_path, "rb") as f:
            self.assertEqual(f.read(), self.payload)
        self.assertIn(b"install_done alecu.testgame\n", self.sent)
        self.assertIn("wifi_connect", fake.calls)
        self.assertIn("wifi_disconnect", fake.calls)

    def test_sha_mismatch_reports_error_and_keeps_nothing(self):
        _install_fake_updater(self.payload)
        installed = []
        with unittest.mock.patch.object(
                installer, "install_from_file",
                lambda path: installed.append(path)):
            ok = installer.run(self._request(sha="0" * 64), self._send)

        self.assertFalse(ok)
        self.assertEqual(installed, [])
        self.assertFalse(os.listdir(self.packages_dir))
        self.assertTrue(any(line.startswith(b"install_error sha256_mismatch")
                            for line in self.sent))

    def test_malformed_request_reports_error(self):
        _install_fake_updater(self.payload)
        ok = installer.run("http://base/only-a-url", self._send)
        self.assertFalse(ok)
        self.assertTrue(any(line.startswith(b"install_error bad_install_request")
                            for line in self.sent))

    def test_wifi_failure_reports_error(self):
        fake = _install_fake_updater(self.payload)

        def _fail():
            raise OSError("no credentials")
        fake._wifi_connect = _fail

        ok = installer.run(self._request(), self._send)
        self.assertFalse(ok)
        self.assertTrue(any(line.startswith(b"install_error wifi_connect_failed")
                            for line in self.sent))

    def test_install_failure_reports_error(self):
        _install_fake_updater(self.payload)

        def _boom(path):
            raise ValueError("package holds no game files")
        with unittest.mock.patch.object(installer, "install_from_file", _boom):
            ok = installer.run(self._request(), self._send)
        self.assertFalse(ok)
        self.assertTrue(any(line.startswith(b"install_error install_failed")
                            for line in self.sent))


if __name__ == "__main__":
    unittest.main()
