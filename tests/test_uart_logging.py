import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))

from ventilastation.uart_logging import InfoWriter


class InfoWriterTests(unittest.TestCase):
    def test_print_parts_become_one_length_delimited_info_frame(self):
        sent = []
        writer = InfoWriter(lambda line, data: sent.append((line, data)))

        print("hola", "mundo", file=writer)

        self.assertEqual(sent, [(b"info 10", b"hola mundo")])

    def test_lines_preserve_utf8_and_empty_output(self):
        sent = []
        writer = InfoWriter(lambda line, data: sent.append((line, data)))

        writer.write("  Ñandú  \n\n")

        self.assertEqual(sent, [
            (b"info 11", "  Ñandú  ".encode("utf-8")),
            (b"info 0", b""),
        ])

    def test_flush_emits_a_partial_line(self):
        sent = []
        writer = InfoWriter(lambda line, data: sent.append((line, data)))

        writer.write("booting")
        writer.flush()

        self.assertEqual(sent, [(b"info 7", b"booting")])


if __name__ == "__main__":
    unittest.main()
