import os
import sys
import types
import unittest

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
