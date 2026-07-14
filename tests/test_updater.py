import hashlib
import os
import sys
import types
import unittest
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))


class _FakeReset(Exception):
    """Raised by the fake machine.reset() so tests can observe it fired."""


def _install_fakes(running_label, nvs_blobs=None, find_results=None):
    """Install minimal esp32/machine stand-ins for updater.py's tier-3 tests.

    running_label  — what esp32.Partition(RUNNING).info()[4] reports.
    nvs_blobs      — seed values for the "vsdk_ota" NVS namespace (str keys).
    find_results   — dict label -> list of fake partition objects returned by
                     esp32.Partition.find(TYPE_APP, label=...).
    """
    nvs_blobs = dict(nvs_blobs or {})
    find_results = dict(find_results or {})

    machine = types.ModuleType("machine")
    machine.reset_calls = []

    def _reset():
        machine.reset_calls.append(True)
        raise _FakeReset()
    machine.reset = _reset
    sys.modules["machine"] = machine

    esp32 = types.ModuleType("esp32")

    class FakeRunningPartition:
        def info(self):
            return (0, 0, 0, 0, running_label, False)

    class FakeNVS:
        def __init__(self, namespace):
            self.namespace = namespace

        def get_blob(self, key, buf):
            value = nvs_blobs.get(key)
            if value is None:
                raise OSError("no such key")
            data = value.encode()
            buf[:len(data)] = data
            return len(data)

        def set_blob(self, key, value):
            nvs_blobs[key] = value.decode() if isinstance(value, (bytes, bytearray)) else value

        def commit(self):
            pass

    class FakePartition:
        TYPE_APP = 0
        RUNNING = "RUNNING"

        def __init__(self, which):
            self._which = which

        def info(self):
            return FakeRunningPartition().info()

        @staticmethod
        def find(type_, label=None):
            return list(find_results.get(label, []))

    esp32.NVS = FakeNVS
    esp32.Partition = FakePartition
    sys.modules["esp32"] = esp32

    return machine, esp32, nvs_blobs


class UpdaterTier3Tests(unittest.TestCase):
    def setUp(self):
        for name in ("machine", "esp32", "updater"):
            sys.modules.pop(name, None)

    def tearDown(self):
        for name in ("machine", "esp32"):
            sys.modules.pop(name, None)

    def _partitions_manifest(self, sha="deadbeef"):
        return {
            "micropython": {"sha256": sha, "size": 100, "url": "/micropython.bin"},
        }

    def test_hands_off_to_factory_when_running_micropython_and_stale(self):
        set_boot_calls = []
        factory_part = types.SimpleNamespace(set_boot=lambda: set_boot_calls.append(True))
        machine, esp32, _nvs = _install_fakes(
            running_label="micropython",
            nvs_blobs={"mp_sha": "old_sha"},
            find_results={"factory": [factory_part]},
        )
        import updater

        with self.assertRaises(_FakeReset):
            updater._update_partitions("http://base", self._partitions_manifest("new_sha"))

        self.assertEqual(set_boot_calls, [True])
        self.assertEqual(machine.reset_calls, [True])

    def test_hands_off_when_no_stored_hash_yet(self):
        set_boot_calls = []
        factory_part = types.SimpleNamespace(set_boot=lambda: set_boot_calls.append(True))
        machine, esp32, _nvs = _install_fakes(
            running_label="micropython",
            nvs_blobs={},
            find_results={"factory": [factory_part]},
        )
        import updater

        with self.assertRaises(_FakeReset):
            updater._update_partitions("http://base", self._partitions_manifest("new_sha"))

        self.assertEqual(set_boot_calls, [True])
        self.assertEqual(machine.reset_calls, [True])

    def test_skips_without_handoff_when_running_micropython_and_up_to_date(self):
        set_boot_calls = []
        factory_part = types.SimpleNamespace(set_boot=lambda: set_boot_calls.append(True))
        machine, esp32, _nvs = _install_fakes(
            running_label="micropython",
            nvs_blobs={"mp_sha": "current_sha"},
            find_results={"factory": [factory_part]},
        )
        import updater

        # Must not raise/reset: nothing to do.
        updater._update_partitions("http://base", self._partitions_manifest("current_sha"))

        self.assertEqual(set_boot_calls, [])
        self.assertEqual(machine.reset_calls, [])

    def test_handoff_noop_when_factory_partition_missing(self):
        machine, esp32, _nvs = _install_fakes(
            running_label="micropython",
            nvs_blobs={"mp_sha": "old_sha"},
            find_results={"factory": []},
        )
        import updater

        # Must not raise: logs and continues rather than crashing.
        updater._update_partitions("http://base", self._partitions_manifest("new_sha"))

        self.assertEqual(machine.reset_calls, [])


class _FakeFlashPartition:
    """In-memory stand-in for esp32.Partition, readblocks() only."""

    def __init__(self, data):
        self.data = data

    def readblocks(self, block_num, buf):
        offset = block_num * len(buf)
        chunk = self.data[offset:offset + len(buf)]
        buf[:len(chunk)] = chunk
        if len(chunk) < len(buf):
            buf[len(chunk):] = b"\xff" * (len(buf) - len(chunk))


class PartitionMatchesTests(unittest.TestCase):
    """_partition_matches() is what stops a stale NVS-cached hash from
    hiding a partition that was rewritten (wiped, reflashed, corrupted)
    outside the updater -- see _update_partitions()'s skip-check."""

    def setUp(self):
        sys.modules.pop("updater", None)

    def test_matches_when_content_equals_expected_hash(self):
        import updater
        content = b"a valid firmware image" + b"\x00" * 100
        expected = hashlib.sha256(content).hexdigest()
        part = _FakeFlashPartition(content)

        self.assertTrue(updater._partition_matches(part, len(content), expected))

    def test_does_not_match_when_partition_was_wiped(self):
        import updater
        content = b"a valid firmware image" + b"\x00" * 100
        expected = hashlib.sha256(content).hexdigest()
        wiped = _FakeFlashPartition(b"\x00" * len(content))

        self.assertFalse(updater._partition_matches(wiped, len(content), expected))

    def test_ignores_bytes_beyond_the_declared_size(self):
        import updater
        real_content = b"x" * 5000  # spans more than one 4096-byte block
        expected = hashlib.sha256(real_content).hexdigest()
        # Trailing garbage past `size` (e.g. a previous, larger image's
        # leftovers) must not affect the hash.
        on_flash = real_content + b"garbage-from-a-previous-image"
        part = _FakeFlashPartition(on_flash)

        self.assertTrue(updater._partition_matches(part, len(real_content), expected))


class SyncLfsFilesHeartbeatTests(unittest.TestCase):
    """A large file's download can outlast the watchdog timeout with nothing
    else feeding it (unlike _update_partitions()'s per-chunk feed) -- see the
    real crash this caught: task_wdt firing mid-transfer of a multi-MB WAD."""

    def setUp(self):
        sys.modules.pop("updater", None)
        self._had_utime = "utime" in sys.modules
        self._prev_utime = sys.modules.get("utime")

    def tearDown(self):
        if self._had_utime:
            sys.modules["utime"] = self._prev_utime
        else:
            sys.modules.pop("utime", None)

    def test_sends_progress_heartbeat_during_a_slow_download(self):
        fake_time = [0]

        class FakeUtime:
            @staticmethod
            def ticks_ms():
                return fake_time[0]

            @staticmethod
            def ticks_diff(a, b):
                return a - b

        sys.modules["utime"] = FakeUtime

        import updater

        content = b"y" * 100
        expected_sha = hashlib.sha256(content).hexdigest()
        files = [{"path": "big/file.bin", "size": len(content), "sha256": expected_sha}]

        def fake_http_stream(url, callback, total_size):
            # 4 chunks, each "taking" 1200ms of fake clock time -- crosses
            # the 3000ms heartbeat threshold partway through the transfer.
            chunk_size = 25
            for i in range(0, len(content), chunk_size):
                callback(content[i:i + chunk_size])
                fake_time[0] += 1200
                yield min(i + chunk_size, len(content)) * 100 // total_size

        class FakeFile:
            def __init__(self, path, mode):
                self.buf = bytearray()

            def write(self, data):
                self.buf += data

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        sent = []
        updater._comms_send = lambda line: sent.append(line)
        updater._sha256_file = lambda path: None  # local file doesn't exist yet

        with unittest.mock.patch.object(updater, "_http_stream", fake_http_stream), \
                unittest.mock.patch.object(updater, "_makedirs", lambda path: None), \
                unittest.mock.patch("builtins.open", FakeFile), \
                unittest.mock.patch.object(updater.os, "rename", lambda a, b: None):
            updater._sync_lfs_files("http://base", files)

        progress_lines = [s for s in sent if s.startswith(b"ota_progress file big_file.bin")]
        self.assertTrue(progress_lines, "expected at least one heartbeat during the slow download")


class ResolveBaseUrlTests(unittest.TestCase):
    """_resolve_base_url() replaces the hostname with a numeric IP once per
    session, so hundreds of per-file connections during tier 1 don't each
    repeat a fresh (and occasionally hanging) mDNS/DNS lookup."""

    def setUp(self):
        sys.modules.pop("updater", None)

    def test_leaves_ipv4_literal_untouched_and_skips_lookup(self):
        import updater

        def _unexpected(*a):
            raise AssertionError("getaddrinfo should not be called for an IP literal")

        with unittest.mock.patch.object(updater.socket, "getaddrinfo", _unexpected):
            self.assertEqual(
                updater._resolve_base_url("http://192.168.1.5:5653"),
                "http://192.168.1.5:5653",
            )

    def test_resolves_hostname_to_ip_once(self):
        import updater
        calls = []

        def fake_getaddrinfo(host, port):
            calls.append((host, port))
            return [(0, 0, 0, "", ("192.168.1.42", port))]

        with unittest.mock.patch.object(updater.socket, "getaddrinfo", fake_getaddrinfo):
            resolved = updater._resolve_base_url("http://ventilastation-base.local:5653")
        self.assertEqual(resolved, "http://192.168.1.42:5653")
        self.assertEqual(calls, [("ventilastation-base.local", 5653)])


class UrlQuoteTests(unittest.TestCase):
    def setUp(self):
        sys.modules.pop("updater", None)

    def test_leaves_safe_characters_alone(self):
        import updater
        self.assertEqual(
            updater._url_quote("roms/sms/plain_name-1.0.zip"),
            "roms/sms/plain_name-1.0.zip",
        )

    def test_encodes_space_and_parens_and_comma(self):
        import updater
        # The exact filenames from the reported bug.
        self.assertEqual(
            updater._url_quote("roms/sms/After Burner (World).zip"),
            "roms/sms/After%20Burner%20%28World%29.zip",
        )
        self.assertEqual(
            updater._url_quote("roms/sms/Asterix (Europe) (En,Fr) (Rev 1).zip"),
            "roms/sms/Asterix%20%28Europe%29%20%28En%2CFr%29%20%28Rev%201%29.zip",
        )

    def test_round_trips_through_stdlib_unquote(self):
        import updater
        import urllib.parse
        for name in [
            "After Burner (World).zip",
            "Asterix (Europe) (En,Fr) (Rev 1).zip",
            "plain.zip",
            "unicode_café.zip",
        ]:
            quoted = updater._url_quote(name)
            self.assertEqual(urllib.parse.unquote(quoted), name)
            # And critically: no raw space survives, so an HTTP request line
            # built from this path won't confuse whitespace-based parsing.
            self.assertNotIn(" ", quoted)


if __name__ == "__main__":
    unittest.main()
