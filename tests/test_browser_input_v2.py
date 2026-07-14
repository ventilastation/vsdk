"""Browser input-protocol v2 tests for the MicroPython unix port.

Runs under the MicroPython unix port:

    micropython tests/test_browser_input_v2.py
"""

import sys

sys.path.insert(0, "apps/micropython")

from ventilastation.platforms.browser import BrowserComms


class WorkerHost:
    def __init__(self):
        self.joy1 = 0
        self.joy2 = 0
        self.extra = 0
        self.exit = False

    def get_joy1(self):
        return self.joy1

    def get_joy2(self):
        return self.joy2

    def get_extra(self):
        return self.extra

    def consume_exit(self):
        pending = self.exit
        self.exit = False
        return pending


def test_v2_input_is_received_from_worker_host():
    comms = BrowserComms()
    host = WorkerHost()
    host.joy1 = 0x7F
    host.joy2 = 0x55
    host.extra = 0x7F
    comms.set_worker_host(host)

    assert comms.receive(1) == bytes((0x7F,))
    assert comms.next_joy2() == 0x55
    assert comms.next_extra() == 0x7F
    assert comms.input_sequence == 1

    # Re-reading unchanged input must not manufacture a new input edge.
    comms.receive(1)
    assert comms.input_sequence == 1

    host.joy1 = 0x80  # The browser protocol reserves the high bit.
    host.joy2 = 0x82
    host.extra = 0x81
    assert comms.receive(1) == bytes((0x00,))
    assert comms.next_joy2() == 0x02
    assert comms.next_extra() == 0x01
    assert comms.input_sequence == 2


def test_exit_is_consumed_once():
    comms = BrowserComms()
    host = WorkerHost()
    comms.set_worker_host(host)

    assert comms.next_command() is None
    host.exit = True
    assert comms.next_command() == "exit"
    assert comms.next_command() is None

    # The adapter's direct Python fallback carries EXIT too.
    comms.set_input(0, 0, 0, True)
    assert comms.next_command() == "exit"
    assert comms.next_command() is None


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("browser input v2: %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
