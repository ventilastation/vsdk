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


def test_resync_recognized_cleanly_between_frames():
    parser = InputParser()
    assert parser.pop_resync() is False
    parser.feed(b"\n\n\xd2ESYNC\n")
    assert parser.pop_resync() is True
    # Consuming it clears the flag until the marker is seen again.
    assert parser.pop_resync() is False
    # The marker's own "ESYNC" text must not leak into the command queue.
    assert parser.pop_command() is None


def test_resync_recognized_mid_joystick_frame():
    parser = InputParser()
    parser.feed(b"*\x51")  # mid-frame: only 1 of 3 joystick bytes received
    parser.feed(b"\n\n\xd2ESYNC\n")
    assert parser.pop_resync() is True
    # Normal parsing resumes cleanly afterwards.
    parser.feed(b"*\x11\x22\x33")
    assert (parser.joy1, parser.joy2, parser.extra) == (0x11, 0x22, 0x33)


def test_resync_recognized_mid_command():
    parser = InputParser()
    parser.feed(b"sound foo")  # mid-command, no terminating '\n' yet
    parser.feed(b"\n\n\xd2ESYNC\n")
    assert parser.pop_resync() is True
    # The marker's leading '\n' terminates whatever command was in flight
    # exactly like a real newline would (it doesn't retroactively un-queue
    # it) -- harmless, since the device resets right after anyway. Only the
    # marker's own "ESYNC" text is guaranteed not to leak into the queue.
    assert parser.pop_command() == "sound foo"
    assert parser.pop_command() is None
    # Normal parsing resumes cleanly afterwards.
    parser.feed(b"exit\n")
    assert parser.pop_command() == "exit"


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("input protocol v2: %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
