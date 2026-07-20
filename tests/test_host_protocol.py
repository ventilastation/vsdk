"""Host protocol parser tests independent of desktop renderer dependencies."""

import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

from host_protocol import HostProtocolError, HostProtocolParser  # noqa: E402


class HostProtocolParserTests(unittest.TestCase):
    def test_line_and_payload_can_be_fragmented_arbitrarily(self):
        parser = HostProtocolParser()
        self.assertEqual(parser.feed(b"aframe 4 12\na"), [])
        events = parser.feed(b"bcdmusic song loop\n")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].payload, b"abcd")
        self.assertEqual(events[1].command, "music")

    def test_payload_events_preserve_command_args_and_bytes(self):
        parser = HostProtocolParser()
        events = parser.feed(b"aframe 4 12\nabcdmusic song loop\n")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].command, "aframe")
        self.assertEqual(events[0].args, ("4", "12"))
        self.assertEqual(events[0].payload, b"abcd")
        self.assertEqual(events[1].command, "music")
        self.assertEqual(events[1].args, ("song", "loop"))

    def test_unknown_commands_remain_complete_line_events(self):
        parser = HostProtocolParser()
        event, = parser.feed(b"future hello world\n")
        self.assertEqual((event.command, event.args, event.payload), ("future", ("hello", "world"), b""))

    def test_invalid_length_is_rejected(self):
        parser = HostProtocolParser()
        with self.assertRaises(HostProtocolError):
            parser.feed(b"aframe -1 0\n")


if __name__ == "__main__":
    unittest.main()
