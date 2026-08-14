import os
import sys
import time
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
sys.modules.setdefault("uos", os)
if "utime" not in sys.modules:
    class _Utime:
        @staticmethod
        def ticks_ms():
            return int(time.time() * 1000)

        @staticmethod
        def ticks_add(value, delta):
            return value + delta

        @staticmethod
        def ticks_diff(end, start):
            return end - start

        @staticmethod
        def sleep_ms(ms):
            time.sleep(ms / 1000.0)

    sys.modules["utime"] = _Utime


class _FakeReset(Exception):
    """Raised by the fake machine.reset() so tests can observe it fired
    without the process actually resetting (there's nothing to reset here)."""


def _install_fakes(partitions=()):
    """Install minimal machine/esp32 stand-ins. `partitions` is what
    esp32.Partition.find() returns for label="micropython". Recovery no
    longer touches the POV display itself (that's vsdk_ota_rings, driven
    directly by updater.py -- see test_vsdk_ota_rings.py), so unlike before
    there's nothing display-related to fake here."""
    machine = types.ModuleType("machine")
    machine.reset_calls = []

    def _reset():
        machine.reset_calls.append(True)
        raise _FakeReset()
    machine.reset = _reset

    class FakeWDT:
        # Real machine.WDT's keyword is "timeout" (see extmod/machine_wdt.c),
        # not "timeout_ms" -- matching that here is what caught vsdk_recovery
        # 's _arm_wdt() passing the wrong keyword and never actually arming
        # a watchdog on real hardware.
        def __init__(self, timeout=None):
            self.timeout = timeout
            self.feed_count = 0

        def feed(self):
            self.feed_count += 1

    machine.WDT = FakeWDT
    sys.modules["machine"] = machine

    esp32 = types.ModuleType("esp32")

    class FakePartition:
        TYPE_APP = 0

        @staticmethod
        def find(type_, label=None):
            if label == "micropython":
                return list(partitions)
            return []

    esp32.Partition = FakePartition
    sys.modules["esp32"] = esp32

    return machine, esp32


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        for name in ("machine", "esp32", "updater", "vsdk_recovery"):
            sys.modules.pop(name, None)

    def tearDown(self):
        for name in ("machine", "esp32"):
            sys.modules.pop(name, None)

    def test_progress_handler_forwards_lines_over_uart_and_feeds_wdt(self):
        machine, _esp32 = _install_fakes()
        import vsdk_recovery as recovery

        wdt = machine.WDT(timeout=30000)
        sent = []
        import vsdk_uart_log
        original_send = vsdk_uart_log.send
        vsdk_uart_log.send = lambda raw: sent.append(raw)
        try:
            handle, outcome = recovery._make_progress_handler(wdt)
            handle(b"ota_progress start fetching_manifest 0\n")
            handle(b"ota_progress downloading some_file 10\n")
        finally:
            vsdk_uart_log.send = original_send

        self.assertEqual(wdt.feed_count, 2)
        self.assertEqual(sent, [b"ota_progress start fetching_manifest 0", b"ota_progress downloading some_file 10"])
        self.assertIsNone(outcome["ok"])

    def test_progress_handler_records_error_outcome(self):
        _install_fakes()
        import vsdk_recovery as recovery

        handle, outcome = recovery._make_progress_handler(wdt=None)
        handle(b"ota_error manifest_fetch_failed: timeout\n")

        self.assertFalse(outcome["ok"])

    def test_progress_handler_records_success_outcome(self):
        _install_fakes()
        import vsdk_recovery as recovery

        handle, outcome = recovery._make_progress_handler(wdt=None)
        handle(b"ota_done ok\n")

        self.assertTrue(outcome["ok"])

    def test_boot_into_micropython_hands_off_when_partition_exists(self):
        set_boot_calls = []
        fake_partition = types.SimpleNamespace(set_boot=lambda: set_boot_calls.append(True))
        machine, _esp32 = _install_fakes(partitions=[fake_partition])
        import vsdk_recovery as recovery

        with self.assertRaises(_FakeReset):
            recovery._boot_into_micropython_if_ready()

        self.assertEqual(machine.reset_calls, [True])
        self.assertEqual(set_boot_calls, [True])

    def test_boot_into_micropython_noop_when_no_partition(self):
        machine, _esp32 = _install_fakes(partitions=[])
        import vsdk_recovery as recovery

        result = recovery._boot_into_micropython_if_ready()

        self.assertFalse(result)
        self.assertEqual(machine.reset_calls, [])

    def test_run_resets_on_fatal_error_before_any_backoff_sleep(self):
        _install_fakes(partitions=[])
        import vsdk_recovery as recovery
        import updater

        recovery._BOOT_GRACE_MS = 0  # skip the real boot grace period in tests
        def _boom(url, send_fn, **kwargs):
            raise RuntimeError("network stack exploded")
        original_run = updater.run
        updater.run = _boom
        try:
            with self.assertRaises(_FakeReset):
                recovery.run()
        finally:
            updater.run = original_run

    def test_boot_grace_period_feeds_wdt_and_is_skippable(self):
        machine, _esp32 = _install_fakes()
        import vsdk_recovery as recovery

        wdt = machine.WDT(timeout=30000)
        recovery._BOOT_GRACE_MS = 1000
        recovery._boot_grace_period(wdt)

        self.assertGreaterEqual(wdt.feed_count, 2)

        recovery._BOOT_GRACE_MS = 0
        wdt2 = machine.WDT(timeout=30000)
        recovery._boot_grace_period(wdt2)
        self.assertEqual(wdt2.feed_count, 0)


if __name__ == "__main__":
    unittest.main()
