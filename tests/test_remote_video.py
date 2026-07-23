"""Tests for the physical workbench's H.264 WebRTC frame source."""

from __future__ import annotations

import asyncio
from fractions import Fraction
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "emulator"))

from remote_video import (  # noqa: E402
    LatestVideoFrame,
    VIDEO_CODED_HEIGHT,
    VIDEO_CODED_WIDTH,
    VIDEO_HEIGHT,
    VIDEO_PACKING,
    VIDEO_PACKED_WIDTH,
    VIDEO_PLANE_GUARD,
    VIDEO_PLANE_STRIDE,
    VIDEO_TAIL_GUARD,
    VIDEO_WIDTH,
    WorkbenchVideoTrack,
    WebRtcVideoPeer,
    h264_codec_capabilities,
    ice_server_payload,
)


class LatestVideoFrameTests(unittest.IsolatedAsyncioTestCase):
    async def test_track_packs_rgb_into_neutral_luma_samples(self) -> None:
        import numpy

        source = LatestVideoFrame()
        track = WorkbenchVideoTrack.create(source)
        rgb = bytes((index % 251 for index in range(VIDEO_WIDTH * VIDEO_HEIGHT * 3)))

        receive = asyncio.create_task(track.recv())
        await source.publish(7, rgb, captured_at=100.0)
        frame = await asyncio.wait_for(receive, timeout=1)

        self.assertEqual(frame.width, VIDEO_CODED_WIDTH)
        self.assertEqual(frame.height, VIDEO_CODED_HEIGHT)
        pixels = numpy.frombuffer(rgb, dtype=numpy.uint8).reshape(VIDEO_HEIGHT, VIDEO_WIDTH, 3)
        planes = numpy.zeros((VIDEO_HEIGHT, VIDEO_CODED_WIDTH), dtype=numpy.uint8)
        for component in range(3):
            start = component * VIDEO_PLANE_STRIDE
            planes[:, start:start + VIDEO_WIDTH] = pixels[:, :, component]
        expected = numpy.repeat(planes[:, :, None], 3, axis=2)
        numpy.testing.assert_array_equal(frame.to_ndarray(format="rgb24"), expected)
        for component in range(3):
            guard = planes[:,
                           component * VIDEO_PLANE_STRIDE + VIDEO_WIDTH:
                           (component + 1) * VIDEO_PLANE_STRIDE]
            self.assertEqual(guard.shape[1], VIDEO_PLANE_GUARD)
            self.assertFalse(guard.any())
        tail = planes[:, VIDEO_PACKED_WIDTH:]
        self.assertEqual(tail.shape[1], VIDEO_TAIL_GUARD)
        self.assertFalse(tail.any())
        self.assertEqual(VIDEO_CODED_WIDTH % 16, 0)
        self.assertEqual(frame.pts, 0)
        track.stop()

    async def test_h264_packing_retains_adversarial_saturated_colors(self) -> None:
        import av
        import numpy

        source = LatestVideoFrame()
        track = WorkbenchVideoTrack.create(source)
        y, x = numpy.indices((VIDEO_HEIGHT, VIDEO_WIDTH))
        palette = numpy.array([
            [255, 0, 0], [0, 255, 0], [0, 0, 255],
            [255, 255, 0], [255, 0, 255], [0, 255, 255],
        ], dtype=numpy.uint8)
        original = palette[(x + 3 * y) % len(palette)]
        receive = asyncio.create_task(track.recv())
        await source.publish(1, original.tobytes(), captured_at=100.0)
        packed = await asyncio.wait_for(receive, timeout=1)

        encoder = av.CodecContext.create("libx264", "w")
        encoder.width = VIDEO_CODED_WIDTH
        encoder.height = VIDEO_CODED_HEIGHT
        encoder.bit_rate = 1_000_000
        encoder.pix_fmt = "yuv420p"
        encoder.framerate = Fraction(30, 1)
        encoder.time_base = Fraction(1, 30)
        encoder.options = {"level": "31", "tune": "zerolatency"}
        encoder.profile = "Baseline"
        packed.pts = 0
        packed.time_base = Fraction(1, 30)
        packets = encoder.encode(packed) + encoder.encode(None)
        decoder = av.CodecContext.create("h264", "r")
        decoded = []
        for packet in packets:
            decoded.extend(decoder.decode(packet))
        decoded.extend(decoder.decode(None))
        luma_planes = decoded[-1].to_ndarray(format="rgb24")[:, :, 0]
        reconstructed = numpy.stack((
            luma_planes[:, :VIDEO_WIDTH],
            luma_planes[:, VIDEO_PLANE_STRIDE:VIDEO_PLANE_STRIDE + VIDEO_WIDTH],
            luma_planes[:, VIDEO_PLANE_STRIDE * 2:VIDEO_PLANE_STRIDE * 2 + VIDEO_WIDTH],
        ), axis=2)
        error = numpy.abs(reconstructed.astype(numpy.int16) - original.astype(numpy.int16))
        self.assertLess(float(error.mean()), 0.5)
        self.assertLessEqual(int(error.max()), 3)
        track.stop()

    async def test_source_replaces_stale_frames(self) -> None:
        source = LatestVideoFrame(width=2, height=2)
        await source.publish(1, bytes([1] * 12))
        await source.publish(2, bytes([2] * 12))
        snapshot = await source.next_after(None)
        self.assertEqual(snapshot.sequence, 2)
        self.assertEqual(snapshot.rgb, bytes([2] * 12))

    async def test_rejects_wrong_frame_size(self) -> None:
        source = LatestVideoFrame(width=2, height=2)
        with self.assertRaisesRegex(ValueError, "invalid length"):
            await source.publish(1, b"short")

    async def test_h264_offer_negotiates_packed_track(self) -> None:
        from aiortc import RTCConfiguration, RTCPeerConnection, RTCRtpReceiver

        source = LatestVideoFrame()
        receiver = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        transceiver = receiver.addTransceiver("video", direction="recvonly")
        transceiver.setCodecPreferences([
            codec for codec in RTCRtpReceiver.getCapabilities("video").codecs
            if codec.mimeType.casefold() == "video/h264"
        ])
        await receiver.setLocalDescription(await receiver.createOffer())
        peer = WebRtcVideoPeer(source, [])
        try:
            answer = await peer.accept_offer(
                receiver.localDescription.sdp,
                receiver.localDescription.type,
            )
            self.assertIn("H264/90000", answer["sdp"])
            self.assertEqual((answer["width"], answer["height"]), (VIDEO_CODED_WIDTH, VIDEO_CODED_HEIGHT))
            self.assertEqual((answer["logicalWidth"], answer["logicalHeight"]), (VIDEO_WIDTH, VIDEO_HEIGHT))
            self.assertEqual(answer["packing"], VIDEO_PACKING)
            await receiver.setRemoteDescription(type(receiver.localDescription)(
                sdp=answer["sdp"],
                type=answer["type"],
            ))
        finally:
            await peer.close()
            await receiver.close()


class WebRtcConfigurationTests(unittest.TestCase):
    def test_only_h264_encoder_capabilities_are_selected(self) -> None:
        codecs = h264_codec_capabilities()
        self.assertTrue(codecs)
        self.assertTrue(all(codec.mimeType.casefold() == "video/h264" for codec in codecs))

    def test_ice_server_payload_accepts_turn_credentials(self) -> None:
        payload = ice_server_payload([{
            "urls": "turn:relay.example.test:3478",
            "username": "user",
            "credential": "secret",
        }])
        self.assertEqual(payload, [{
            "urls": ["turn:relay.example.test:3478"],
            "username": "user",
            "credential": "secret",
        }])


if __name__ == "__main__":
    unittest.main()
