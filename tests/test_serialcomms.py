"""serialcomms receive-side diagnostics, with machine/esp32 faked (CPython)."""

import importlib
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))


class FakeUART:
    def __init__(self, *_args, **_kwargs):
        self.rx = bytearray()
        self.written = []

    def any(self):
        return len(self.rx)

    def read(self, size):
        chunk = bytes(self.rx[:size])
        del self.rx[:size]
        return chunk or None

    def write(self, data):
        # machine.UART.write takes str as well as buffers.
        self.written.append(data.encode() if isinstance(data, str) else bytes(data))

    def __repr__(self):
        return ("UART(1, baudrate=115200, bits=8, parity=None, stop=1, tx=17, rx=18, "
                "rts=-1, cts=-1, txbuf=256, rxbuf=256, timeout=0, timeout_char=0, irq=0)")


class FakeNVS:
    def __init__(self, _namespace):
        pass

    def get_i32(self, _key):
        return 1


def import_serialcomms():
    sys.modules["machine"] = types.SimpleNamespace(UART=FakeUART)
    sys.modules["esp32"] = types.SimpleNamespace(NVS=FakeNVS)
    resync = types.ModuleType("ventilastation.console_resync")
    resync.ConsoleResyncScanner = lambda: types.SimpleNamespace(poll_pending=lambda: False)
    sys.modules["ventilastation.console_resync"] = resync
    # A fresh module (and UART) per test: drop the package attribute too, or
    # the import would hand back the previous test's module.
    sys.modules.pop("ventilastation.serialcomms", None)
    import ventilastation
    if hasattr(ventilastation, "serialcomms"):
        del ventilastation.serialcomms
    return importlib.import_module("ventilastation.serialcomms")


class LinkStatsTests(unittest.TestCase):
    def setUp(self):
        self.serialcomms = import_serialcomms()
        self.uart = self.serialcomms.uart

    def test_high_water_mark_tracks_the_fullest_drain(self):
        stats = self.serialcomms.link_stats()
        self.assertEqual(stats["rx_buf"], 256)
        self.assertEqual(stats["rx_hwm"], 0)

        self.uart.rx.extend(b"*\x00\x00\x00" * 50)  # 200 bytes waiting
        self.serialcomms.receive(1)
        self.assertEqual(self.serialcomms.link_stats()["rx_hwm"], 200)

        self.serialcomms.receive(1)  # 136 left: the mark keeps the peak
        self.assertEqual(self.serialcomms.link_stats(reset=True)["rx_hwm"], 200)
        self.assertEqual(self.serialcomms.link_stats()["rx_hwm"], 0)

    def test_parser_drops_are_reported(self):
        self.uart.rx.extend(b"sound \xffoo\nexit\n")
        self.assertEqual(self.serialcomms.next_command(), "exit")
        stats = self.serialcomms.link_stats()
        self.assertEqual((stats["nonascii"], stats["overlong"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
