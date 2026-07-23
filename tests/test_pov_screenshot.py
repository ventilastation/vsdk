import os
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

import pov_screenshot as shot  # noqa: E402

try:
    import numpy  # noqa: F401
    from PIL import Image  # noqa: F401
    HAVE_IMAGING = True
except ImportError:
    HAVE_IMAGING = False


class ButtonMapTests(unittest.TestCase):
    def test_a_is_joy1_bit4(self):
        self.assertEqual(shot.BUTTONS["a"], (0x10, 0))

    def test_start_is_extra_bit2(self):
        self.assertEqual(shot.BUTTONS["start"], (0, 0x04))

    def test_back_and_select_alias(self):
        self.assertEqual(shot.BUTTONS["back"], shot.BUTTONS["select"])

    def test_dpad_bits(self):
        self.assertEqual(
            (shot.BUTTONS["left"], shot.BUTTONS["right"],
             shot.BUTTONS["up"], shot.BUTTONS["down"]),
            ((0x01, 0), (0x02, 0), (0x04, 0), (0x08, 0)),
        )


def _solid_frame(gb, b, g, r):
    """A full frame where every LED carries the same [GB, B, G, R] datum."""
    led = bytes([gb, b, g, r])
    return led * (shot.COLUMNS * shot.PIXELS)


@unittest.skipUnless(HAVE_IMAGING, "numpy/PIL not installed")
class RenderPolarTests(unittest.TestCase):
    def test_shape_and_black_corners(self):
        img = shot.render_polar(_solid_frame(0xE0, 0, 0, 0), size=64)
        self.assertEqual(img.size, (64, 64))
        px = img.load()
        # A corner is outside the inscribed ring -> untouched (black).
        self.assertEqual(px[0, 0], (0, 0, 0))

    def test_lit_frame_fills_the_ring(self):
        # Full-brightness red everywhere -> the inscribed disc should be non-black.
        img = shot.render_polar(_solid_frame(0xFF, 0, 0, 0xFF), size=64)
        px = img.load()
        centre = px[32, 32]
        self.assertNotEqual(centre, (0, 0, 0))
        self.assertGreater(centre[0], centre[1])  # red dominant
        self.assertGreater(centre[0], centre[2])

    def test_lit_fraction(self):
        self.assertAlmostEqual(shot.lit_fraction(_solid_frame(0xE0, 0, 0, 0)), 0.0)
        self.assertAlmostEqual(shot.lit_fraction(_solid_frame(0xFF, 1, 2, 3)), 1.0)


class CaptureFrameParseTests(unittest.TestCase):
    def test_reassembles_a_complete_frame_over_a_fake_socket(self):
        # Build 64 chunks for one frame_seq and feed them through a fake socket.
        payload_total = shot.COLUMNS * shot.PIXELS * 4
        chunk_len = payload_total // shot.WB_CHUNKS
        body = bytes((i % 251) for i in range(payload_total))
        packets = []
        for ci in range(shot.WB_CHUNKS):
            header = bytes([0xA1]) + struct.pack("<I", 7) + bytes([ci])
            packets.append(header + body[ci * chunk_len:(ci + 1) * chunk_len])

        class FakeSock:
            def __init__(self, pkts):
                self._pkts = list(pkts)

            def settimeout(self, _):
                pass

            def sendto(self, *_):
                pass

            def recvfrom(self, _n):
                if self._pkts:
                    return self._pkts.pop(0), ("h", 0)
                raise TimeoutError

            def close(self):
                pass

        import socket as _socket
        real = _socket.socket
        _socket.socket = lambda *a, **k: FakeSock(packets)
        try:
            raw = shot.capture_frame("host", timeout=1.0)
        finally:
            _socket.socket = real
        self.assertEqual(raw, body)


if __name__ == "__main__":
    unittest.main()
