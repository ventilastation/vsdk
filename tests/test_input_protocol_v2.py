"""Input protocol v2 parser checks (runs on CPython)."""

import sys

sys.path.insert(0, "apps/micropython")

from ventilastation.input_parser import InputParser


def test_parser_keeps_two_joysticks_and_command_order():
    parser = InputParser()
    parser.feed(b"\xff\x00*\x51\x62\x35exit\n")
    assert (parser.joy1, parser.joy2, parser.extra) == (0x51, 0x62, 0x35)
    assert parser.pop_command() == "exit"
    assert parser.pop_command() is None

    parser.feed(b"*\x00\x00\x00")
    assert (parser.joy1, parser.joy2, parser.extra) == (0, 0, 0)

    # The high bit is never meaningful on the wire and must not leak into
    # consumer button state even if a corrupt sender transmits it.
    parser.feed(b"*\xd1\xe2\xf5")
    assert (parser.joy1, parser.joy2, parser.extra) == (0x51, 0x62, 0x75)


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("input protocol v2: %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
