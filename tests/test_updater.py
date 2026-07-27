import hashlib
import json
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
            # Faking every open() call in _sync_lfs_files() now also covers
            # the text-mode LFS hash cache load/save, not just the binary
            # download-write path -- branch the buffer type on mode like a
            # real file would.
            def __init__(self, path, mode):
                self.buf = bytearray() if "b" in mode else ""

            def write(self, data):
                self.buf += data

            def read(self, *a):
                return self.buf

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

        progress_lines = [s for s in sent if s.startswith(b"ota_progress downloading big_file.bin")]
        self.assertTrue(progress_lines, "expected at least one heartbeat during the slow download")


class LfsHashCacheTests(unittest.TestCase):
    """_sync_lfs_files() caches each path's last-verified sha256 (mirroring
    the NVS partition-hash cache tier-3 already uses) so an unchanged file
    is trusted without re-reading and re-hashing its content on every
    session -- this is what makes repeat scans of an otherwise-unchanged
    tree fast instead of hashing the full LFS content every time."""

    def setUp(self):
        sys.modules.pop("updater", None)

    def _run_sync(self, files, fake_fs, sha256_calls, download_content=b"new content"):
        class FakeUtime:
            @staticmethod
            def ticks_ms():
                return 0

            @staticmethod
            def ticks_diff(a, b):
                return 0

        sys.modules["utime"] = FakeUtime

        import updater

        class FakeFile:
            def __init__(self, path, mode):
                self.path = path
                self.mode = mode
                self.write_buf = bytearray() if "b" in mode else ""

            def read(self, *a):
                return fake_fs.get(self.path, b"" if "b" in self.mode else "")

            def write(self, data):
                self.write_buf += data

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                if "w" in self.mode:
                    fake_fs[self.path] = self.write_buf
                return False

        def fake_sha256_file(path):
            sha256_calls.append(path)
            content = fake_fs.get(path)
            if content is None:
                return None
            data = content if isinstance(content, (bytes, bytearray)) else content.encode()
            return hashlib.sha256(data).hexdigest()

        def fake_rename(a, b):
            fake_fs[b] = fake_fs.pop(a)

        def fake_http_stream(url, callback, total_size):
            callback(download_content)
            yield 100

        with unittest.mock.patch("builtins.open", FakeFile), \
                unittest.mock.patch.object(updater, "_sha256_file", fake_sha256_file), \
                unittest.mock.patch.object(updater, "_makedirs", lambda path: None), \
                unittest.mock.patch.object(updater.os, "rename", fake_rename), \
                unittest.mock.patch.object(updater, "_http_stream", fake_http_stream):
            updater._sync_lfs_files("http://base", files)
        return updater

    def test_second_sync_skips_rehashing_an_unchanged_file(self):
        content = b"hello world"
        sha = hashlib.sha256(content).hexdigest()
        fake_fs = {"/a.py": content}
        files = [{"path": "a.py", "size": len(content), "sha256": sha}]

        first_calls = []
        self._run_sync(files, fake_fs, first_calls)
        self.assertIn("/a.py", first_calls, "first-ever sync has no cache yet, must hash")

        second_calls = []
        self._run_sync(files, fake_fs, second_calls)
        self.assertNotIn("/a.py", second_calls, "cache hit should skip re-hashing unchanged content")

    def test_changed_file_downloads_and_refreshes_the_cache(self):
        old_content = b"old"
        old_sha = hashlib.sha256(old_content).hexdigest()
        fake_fs = {"/a.py": old_content}
        files = [{"path": "a.py", "size": len(old_content), "sha256": old_sha}]
        self._run_sync(files, fake_fs, [])  # seed the cache with the old hash

        new_content = b"brand new content"
        new_sha = hashlib.sha256(new_content).hexdigest()
        files[0]["sha256"] = new_sha
        files[0]["size"] = len(new_content)

        self._run_sync(files, fake_fs, [], download_content=new_content)
        self.assertEqual(fake_fs["/a.py"], new_content)

        # Cache should now hold the new hash, so a third, unchanged sync
        # doesn't re-hash it either.
        third_calls = []
        self._run_sync(files, fake_fs, third_calls)
        self.assertNotIn("/a.py", third_calls)

    def test_cache_drops_paths_no_longer_in_the_manifest(self):
        content_a = b"a-content"
        content_b = b"b-content"
        fake_fs = {
            "/a.py": content_a,
            "/b.py": content_b,
        }
        files = [
            {"path": "a.py", "size": len(content_a), "sha256": hashlib.sha256(content_a).hexdigest()},
            {"path": "b.py", "size": len(content_b), "sha256": hashlib.sha256(content_b).hexdigest()},
        ]
        self._run_sync(files, fake_fs, [])

        cached = json.loads(fake_fs["/.vsdk_lfs_cache.json"])
        self.assertEqual(set(cached), {"a.py", "b.py"})

        self._run_sync(files[:1], fake_fs, [])  # b.py dropped from the manifest
        cached = json.loads(fake_fs["/.vsdk_lfs_cache.json"])
        self.assertEqual(set(cached), {"a.py"})


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


class PartitionProgressRingTests(unittest.TestCase):
    """_update_partitions() feeds vsdk_ota_rings (the on-device LED-ring
    display, see vsdk_ota_rings.py) a running done/total block count across
    every partition in this session, not a per-partition percentage -- these
    check that math, independent of the ring module's own rendering (see
    test_vsdk_ota_rings.py)."""

    def setUp(self):
        for name in ("machine", "esp32", "updater"):
            sys.modules.pop(name, None)

    def tearDown(self):
        for name in ("machine", "esp32"):
            sys.modules.pop(name, None)

    def test_total_blocks_excludes_already_up_to_date_partitions(self):
        content = b"x" * 8192  # exactly 2 blocks
        expected_sha = hashlib.sha256(content).hexdigest()

        machine, esp32, _nvs = _install_fakes(
            running_label="factory",
            nvs_blobs={"fmsx_sha": "matches"},  # fmsx already up to date
        )
        import updater

        recorded = []
        updater.vsdk_ota_rings = types.SimpleNamespace(
            set_partition_progress=lambda done, total: recorded.append(("progress", done, total)),
            pulse_partition_activity=lambda: recorded.append(("pulse",)),
            hide_partition_rings=lambda: recorded.append(("hide",)),
        )

        class FakeWritePartition:
            def writeblocks(self, block_num, buf):
                pass

        write_targets = {"prboom-go": [FakeWritePartition()]}
        esp32.Partition.find = staticmethod(lambda type_, label=None: list(write_targets.get(label, [])))

        def fake_http_stream(url, callback, total_size):
            callback(content)
            yield 100

        partitions_manifest = {
            "fmsx": {"sha256": "matches", "size": 4096, "url": "/fmsx"},
            "prboom-go": {"sha256": expected_sha, "size": len(content), "url": "/prboom-go"},
        }

        with unittest.mock.patch.object(updater, "_http_stream", fake_http_stream):
            updater._update_partitions("http://base", partitions_manifest)

        progress_calls = [r for r in recorded if r[0] == "progress"]
        # Upfront total counts only prboom-go's 2 blocks -- fmsx's stored
        # hash already matches the manifest, so it's not "work to do".
        self.assertEqual(progress_calls[0], ("progress", 0, 2))
        self.assertEqual(progress_calls[-1], ("progress", 2, 2))
        self.assertEqual(len([r for r in recorded if r[0] == "pulse"]), 2)
        # Gray/yellow shouldn't linger at their last position once this tier
        # is done -- see vsdk_ota_rings.hide_partition_rings()'s docstring.
        self.assertEqual(recorded[-1], ("hide",))

    def test_total_blocks_rounds_partial_final_block_up(self):
        content = b"x" * 4097  # one full block plus one byte -- rounds up to 2
        expected_sha = hashlib.sha256(content).hexdigest()

        machine, esp32, _nvs = _install_fakes(running_label="factory", nvs_blobs={})
        import updater

        recorded = []
        updater.vsdk_ota_rings = types.SimpleNamespace(
            set_partition_progress=lambda done, total: recorded.append((done, total)),
            pulse_partition_activity=lambda: None,
            hide_partition_rings=lambda: None,
        )

        class FakeWritePartition:
            def writeblocks(self, block_num, buf):
                pass

        esp32.Partition.find = staticmethod(
            lambda type_, label=None: [FakeWritePartition()] if label == "prboom-go" else []
        )

        def fake_http_stream(url, callback, total_size):
            callback(content)
            yield 100

        partitions_manifest = {
            "prboom-go": {"sha256": expected_sha, "size": len(content), "url": "/prboom-go"},
        }

        with unittest.mock.patch.object(updater, "_http_stream", fake_http_stream):
            updater._update_partitions("http://base", partitions_manifest)

        self.assertEqual(recorded[0], (0, 2))
        self.assertEqual(recorded[-1], (2, 2))


class FileProgressRingTests(unittest.TestCase):
    """_sync_lfs_files()'s equivalent for tier 1: a running done/total byte
    count across every file that needs syncing, fed to vsdk_ota_rings."""

    def setUp(self):
        sys.modules.pop("updater", None)

    def _run_sync(self, files, fake_fs, download_content=b"new content"):
        class FakeUtime:
            @staticmethod
            def ticks_ms():
                return 0

            @staticmethod
            def ticks_diff(a, b):
                return 0

        sys.modules["utime"] = FakeUtime

        import updater

        recorded = []
        hide_calls = []
        updater.vsdk_ota_rings = types.SimpleNamespace(
            set_file_progress=lambda done, total: recorded.append((done, total)),
            pulse_file_activity=lambda: None,
            hide_file_rings=lambda: hide_calls.append(True),
        )

        class FakeFile:
            def __init__(self, path, mode):
                self.path = path
                self.mode = mode
                self.write_buf = bytearray() if "b" in mode else ""

            def read(self, *a):
                return fake_fs.get(self.path, b"" if "b" in self.mode else "")

            def write(self, data):
                self.write_buf += data

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                if "w" in self.mode:
                    fake_fs[self.path] = self.write_buf
                return False

        def fake_sha256_file(path):
            content = fake_fs.get(path)
            if content is None:
                return None
            data = content if isinstance(content, (bytes, bytearray)) else content.encode()
            return hashlib.sha256(data).hexdigest()

        def fake_rename(a, b):
            fake_fs[b] = fake_fs.pop(a)

        def fake_http_stream(url, callback, total_size):
            callback(download_content)
            yield 100

        with unittest.mock.patch("builtins.open", FakeFile), \
                unittest.mock.patch.object(updater, "_sha256_file", fake_sha256_file), \
                unittest.mock.patch.object(updater, "_makedirs", lambda path: None), \
                unittest.mock.patch.object(updater.os, "rename", fake_rename), \
                unittest.mock.patch.object(updater, "_http_stream", fake_http_stream):
            updater._sync_lfs_files("http://base", files)
        self._hide_calls = hide_calls
        return recorded

    def test_total_bytes_excludes_files_already_cached(self):
        cached_content = b"already correct"
        cached_sha = hashlib.sha256(cached_content).hexdigest()
        new_content = b"needs downloading"
        new_sha = hashlib.sha256(new_content).hexdigest()

        # Seed the on-device hash cache so cached.py is a cache hit.
        import json as _json
        fake_fs = {
            "/cached.py": cached_content,
            "/.vsdk_lfs_cache.json": _json.dumps({"cached.py": cached_sha}),
        }

        files = [
            {"path": "cached.py", "size": len(cached_content), "sha256": cached_sha},
            {"path": "new.py", "size": len(new_content), "sha256": new_sha},
        ]

        recorded = self._run_sync(files, fake_fs, download_content=new_content)

        # Upfront total only counts new.py -- cached.py is a cache hit, not
        # "work to do" (see _sync_lfs_files()'s overcount note for why a
        # cache *miss* that turns out unchanged is still counted: that path
        # isn't exercised here since new.py always needs a real download).
        self.assertEqual(recorded[0], (0, len(new_content)))
        self.assertEqual(recorded[-1], (len(new_content), len(new_content)))

    def test_hide_file_rings_called_once_sync_completes(self):
        # White/green shouldn't linger at their last position once tier 2/3
        # starts -- see vsdk_ota_rings.hide_file_rings()'s own docstring.
        self._run_sync([], {})
        self.assertEqual(self._hide_calls, [True])


class WifiConnectRetryTests(unittest.TestCase):
    """_wifi_connect() never gives up on a slow/unreachable AP, but switches
    the on-device ring/label to a red "wifi problem" indicator after a few
    quiet attempts -- see vsdk_ota_rings.show_wifi_problem()."""

    def setUp(self):
        for name in ("machine", "esp32", "updater", "network", "utime"):
            sys.modules.pop(name, None)

    def tearDown(self):
        for name in ("machine", "esp32", "network", "utime"):
            sys.modules.pop(name, None)

    def _install_network(self, connect_on_attempt):
        """connect_on_attempt: 1-based attempt number on which isconnected()
        starts reporting True; None means it never connects."""
        network = types.ModuleType("network")
        network.STA_IF = "STA_IF"
        state = {"attempt": 0}

        class FakeWLAN:
            def __init__(self, mode):
                pass

            def active(self, value=None):
                pass

            def isconnected(self):
                return connect_on_attempt is not None and state["attempt"] >= connect_on_attempt

            def connect(self, ssid, password):
                state["attempt"] += 1

            def ifconfig(self):
                return ("1.2.3.4",)

        network.WLAN = FakeWLAN
        sys.modules["network"] = network
        sys.modules["utime"] = types.SimpleNamespace(sleep_ms=lambda ms: None)
        return state

    def test_calls_show_wifi_problem_from_third_attempt_onward(self):
        _machine, _esp32, _nvs = _install_fakes(
            running_label="micropython",
            nvs_blobs={"ssid": "myssid", "password": "mypass"},
        )
        self._install_network(connect_on_attempt=5)  # fails 4 times, connects on the 5th

        import updater
        calls = []
        updater.vsdk_ota_rings = types.SimpleNamespace(
            show_wifi_problem=lambda: calls.append("problem"),
            show_wifi_connecting=lambda: calls.append("connecting"),
        )

        self.assertTrue(updater._wifi_connect())
        # Attempts 1-2 show the calm "connecting" state; attempts 3-5 (the
        # last one succeeds, but the switch happens before that attempt's
        # own connect() call -- see the ordering in _wifi_connect()) show
        # "problem" -- called every attempt from there on, not just once,
        # so ensure_started() keeps getting retried -- see that comment.
        self.assertEqual(calls, ["connecting", "connecting", "problem", "problem", "problem"])

    def test_no_wifi_problem_call_when_it_connects_right_away(self):
        _machine, _esp32, _nvs = _install_fakes(
            running_label="micropython",
            nvs_blobs={"ssid": "myssid", "password": "mypass"},
        )
        self._install_network(connect_on_attempt=1)

        import updater
        calls = []
        updater.vsdk_ota_rings = types.SimpleNamespace(
            show_wifi_problem=lambda: calls.append("problem"),
            show_wifi_connecting=lambda: calls.append("connecting"),
        )

        self.assertTrue(updater._wifi_connect())
        self.assertEqual(calls, ["connecting"])

    def test_survives_connect_raising_instead_of_just_never_connecting(self):
        # Confirmed on hardware: a bad password made connect() itself raise
        # (not just leave isconnected() False), which used to escape
        # _wifi_connect() entirely and abort the retry loop via run()'s own
        # `except OSError`. Must count as a failed attempt, not a fatal one.
        _machine, _esp32, _nvs = _install_fakes(
            running_label="micropython",
            nvs_blobs={"ssid": "myssid", "password": "mypass"},
        )
        network = types.ModuleType("network")
        network.STA_IF = "STA_IF"
        state = {"attempt": 0}

        class FlakyWLAN:
            def __init__(self, mode):
                pass

            def active(self, value=None):
                pass

            def isconnected(self):
                return state["attempt"] >= 4

            def connect(self, ssid, password):
                state["attempt"] += 1
                if state["attempt"] <= 2:
                    raise OSError("Wifi Internal Error")

            def ifconfig(self):
                return ("1.2.3.4",)

        network.WLAN = FlakyWLAN
        sys.modules["network"] = network
        sys.modules["utime"] = types.SimpleNamespace(sleep_ms=lambda ms: None)

        import updater
        updater.vsdk_ota_rings = types.SimpleNamespace(
            show_wifi_problem=lambda: None,
            show_wifi_connecting=lambda: None,
        )

        self.assertTrue(updater._wifi_connect())


if __name__ == "__main__":
    unittest.main()
