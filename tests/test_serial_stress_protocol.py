"""Serial stress test wire format and diagnosis.

Runs under CPython and the MicroPython unix port (plain asserts): both ends
of the link must derive the same test bytes, so the pattern checksums below
are pinned and checked on both interpreters.
"""

import binascii
import sys

sys.path.insert(0, "apps/micropython")

from ventilastation import serial_stress as sst


def test_patterns_are_identical_on_both_interpreters():
    binary = sst.binary_pattern()
    text = sst.ascii_pattern()
    assert len(binary) == 2 * sst.PATTERN_SIZE
    assert binary[:sst.PATTERN_SIZE] == binary[sst.PATTERN_SIZE:]
    assert len(set(binary)) == 256
    assert len(text) == 2 * sst.PATTERN_SIZE
    assert all(0x21 <= ord(ch) <= 0x7E and ch != "*" for ch in text)
    # Pinned: a change here breaks every base/rotor pair not updated together.
    assert binascii.crc32(binary) & 0xFFFFFFFF == 0xBA0F593F, hex(binascii.crc32(binary))
    assert binascii.crc32(text.encode()) & 0xFFFFFFFF == 0x4058BFBF, hex(binascii.crc32(text.encode()))


def test_frames_are_functions_of_phase_and_seq():
    first = bytes(sst.up_payload(3, 17, 512))
    assert first == bytes(sst.up_payload(3, 17, 512))
    assert first != bytes(sst.up_payload(3, 18, 512))
    assert first != bytes(sst.up_payload(4, 17, 512))
    assert len(bytes(sst.up_payload(0, 4095, sst.MAX_UP_FRAME))) == sst.MAX_UP_FRAME
    assert sst.up_header(512, 3, 17) == b"serialtest_up 512 3 17"


def test_downlink_lines_fit_the_input_parser():
    line = sst.down_line(len(sst.PHASES) - 1, 4095, sst.MAX_DOWN_PAYLOAD)
    assert len(line) + 1 <= 256, len(line)
    command, phase, seq, payload = line.split(" ")
    assert (command, phase, seq) == (sst.DOWN, str(len(sst.PHASES) - 1), "4095")
    assert payload == sst.down_payload(len(sst.PHASES) - 1, 4095, sst.MAX_DOWN_PAYLOAD)


def test_plan_loads():
    assert sst.line_rate(115200) == 11520
    assert sst.phase_load(sst.phase_index("up50"), 115200) == (5760, 256, 0, 0)
    assert sst.phase_index("down60") not in sst.PLAN
    assert sst.phase_index("idle") == sst.PLAN[0]
    assert sst.phase_index("nope") is None
    for name, _up, up_frame, _down, down_chars, _in_plan in sst.PHASES:
        assert up_frame <= sst.MAX_UP_FRAME, name
        assert down_chars <= sst.MAX_DOWN_PAYLOAD, name


def test_fields_round_trip_and_tolerate_garbage():
    text = sst.format_fields((("frames", 12), ("kind", "x")))
    assert text == "frames=12 kind=x"
    assert sst.parse_fields(text.split(" ")) == {"frames": 12, "kind": "x"}
    assert sst.parse_fields(["=3", "noequals", "a=", "b=7"]) == {"a": "", "b": 7}


def payload(n=200):
    return bytes(sst.up_payload(1, 2, n))


def test_diagnose_in_place_corruption():
    good = payload()
    assert sst.diagnose(good, good) == (sst.OK, 0, 0, 0)

    flipped = bytearray(good)
    flipped[10] ^= 0x04
    flipped[150] ^= 0x81
    assert sst.diagnose(good, bytes(flipped)) == (sst.BITFLIP, 10, 2, 3)

    zeroed = bytearray(good)
    zeroed[60] = 0
    zeroed[61] = 0 if good[61] else 1
    kind, offset, nbytes, _bits = sst.diagnose(good, bytes(zeroed))
    if good[61]:
        assert (kind, offset) == (sst.ZEROED, 60), (kind, offset)
    else:
        assert kind == sst.BITFLIP


def test_diagnose_lost_bytes():
    good = payload()
    # Read as its own frame: shorter, the rest realigns.
    assert sst.diagnose(good, good[:70] + good[86:]) == (sst.DROPPED, 70, 16, 0)
    # Read by trusting the header's length: padded with the next frame.
    padded = good[:70] + good[86:] + b"serialtest_up 25"
    assert sst.diagnose(good, padded) == (sst.DROPPED, 70, 16, 0)
    assert sst.diagnose(good, good[:70] + b"xyz" + good[70:]) == (sst.INSERTED, 70, 3, 0)
    assert sst.diagnose(good, good[:195]) == (sst.SHORT, 195, 5, 0)
    assert sst.diagnose(good, good[:20] + bytes(range(180))) == (sst.GARBLED, 20, 180, 0)


def test_phase_counter():
    counter = sst.PhaseCounter(2)
    for seq in range(5):
        expected = sst.up_payload(2, seq, 64)
        received = bytes(expected)
        if seq == 3:
            received = received[:10] + bytes([received[10] ^ 1]) + received[11:]
        if seq == 1:
            continue  # lost
        assert counter.check(2, seq, expected, received) in (sst.OK, sst.BITFLIP)
    assert counter.check(2, 4, sst.up_payload(2, 4, 64), bytes(sst.up_payload(2, 4, 64))) == "dup"
    assert counter.check(1, 0, sst.up_payload(1, 0, 64), bytes(sst.up_payload(1, 0, 64))) == "stale"
    assert counter.check(2, 99999, b"", b"x") == sst.GARBLED
    assert (counter.ok, counter.bad, counter.dup, counter.stale) == (3, 2, 1, 1)
    assert counter.kinds == {sst.BITFLIP: 1, sst.GARBLED: 1}
    assert counter.wire_errors() == 1
    assert counter.bits == 1
    # Seq 1 never came, but the garbled frame (its header corrupted) may
    # have been it: frames are only lost when no bad frame can account for them.
    assert counter.lost() == 0
    assert counter.lost(sent=5) == 0
    assert counter.lost(sent=6) == 1
    assert counter.bytes_ok == 3 * 64
    assert sst.describe_example(counter.examples[0]).startswith("seq 3: 1 bytes changed in place")


def test_phase_counter_counts_gaps_without_sender_total():
    counter = sst.PhaseCounter(0)
    for seq in (0, 2, 3):
        counter.check(0, seq, b"a", b"a")
    assert counter.lost() == 1


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("serial stress protocol: %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
