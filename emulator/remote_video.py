"""H.264 WebRTC video transport for the remote physical workbench.

The physical framebuffer is laid out as 256 consecutive rotor columns, each
containing 54 RGB LEDs. Browser-compatible H.264 is normally 4:2:0, so sending
those RGB texels literally would blend the chroma of neighbouring LEDs. The
encoder instead stores the R, G and B components as three guarded planes of
neutral-luma samples. Keeping each plane spatially smooth avoids the one-pixel
high-frequency pattern produced by interleaved components, which browser H.264
encoders can blur. The browser uploads the decoded picture directly to WebGL
and the ring shader reconstructs the color with three texture samples.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from fractions import Fraction
import time
from typing import Any, Awaitable, Callable, Iterable


VIDEO_WIDTH = 54
VIDEO_HEIGHT = 256
VIDEO_COMPONENTS = 3
VIDEO_MACROBLOCK_WIDTH = 16


def _coded_width(logical_width: int) -> int:
    packed_width = (logical_width + VIDEO_PLANE_GUARD) * VIDEO_COMPONENTS
    return (
        (packed_width + VIDEO_MACROBLOCK_WIDTH - 1)
        // VIDEO_MACROBLOCK_WIDTH
        * VIDEO_MACROBLOCK_WIDTH
    )


# Two black luma samples after each component plane separate the planes. The
# three guarded planes occupy 168 samples, followed by eight explicit black
# samples so the published frame is exactly 176 pixels wide. H.264 otherwise
# pads a 168-pixel picture to a 176-pixel macroblock surface and signals a
# crop. Some mobile hardware-decoder/WebGL paths sample that uncropped surface,
# progressively shifting the green and blue planes. Publishing the full
# macroblock width leaves no implicit crop for the browser to misapply.
VIDEO_PLANE_GUARD = 2
VIDEO_PLANE_STRIDE = VIDEO_WIDTH + VIDEO_PLANE_GUARD
VIDEO_PACKED_WIDTH = VIDEO_PLANE_STRIDE * VIDEO_COMPONENTS
VIDEO_CODED_WIDTH = _coded_width(VIDEO_WIDTH)
VIDEO_TAIL_GUARD = VIDEO_CODED_WIDTH - VIDEO_PACKED_WIDTH
VIDEO_CODED_HEIGHT = VIDEO_HEIGHT
# The suffix is part of the browser/gateway compatibility contract. Bump it
# whenever the coded texture layout changes so a stale tab fails visibly
# instead of interpreting one layout with another layout's shader.
VIDEO_PACKING = "rgb-luma-macroblock-planes-v4"
VIDEO_CLOCK_RATE = 90_000
VIDEO_TIME_BASE = Fraction(1, VIDEO_CLOCK_RATE)
DEFAULT_ICE_SERVERS = ({"urls": ["stun:stun.l.google.com:19302"]},)


@dataclass(frozen=True)
class VideoSnapshot:
    sequence: int
    rgb: bytes
    captured_at: float


class LatestVideoFrame:
    """A fan-out source which keeps only the newest complete RGB frame."""

    def __init__(self, width: int = VIDEO_WIDTH, height: int = VIDEO_HEIGHT):
        self.width = width
        self.height = height
        self._condition = asyncio.Condition()
        self._snapshot: VideoSnapshot | None = None

    async def publish(self, sequence: int, rgb: bytes, captured_at: float | None = None) -> None:
        expected = self.width * self.height * 3
        if len(rgb) != expected:
            raise ValueError("video RGB frame has an invalid length")
        snapshot = VideoSnapshot(
            sequence=sequence & 0xFFFFFFFF,
            rgb=bytes(rgb),
            captured_at=time.monotonic() if captured_at is None else captured_at,
        )
        async with self._condition:
            self._snapshot = snapshot
            self._condition.notify_all()

    async def next_after(self, sequence: int | None) -> VideoSnapshot:
        async with self._condition:
            await self._condition.wait_for(
                lambda: self._snapshot is not None and self._snapshot.sequence != sequence
            )
            assert self._snapshot is not None
            return self._snapshot


def ice_server_payload(servers: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the browser-safe subset of configured ICE server fields."""

    payload = []
    for server in servers:
        urls = server.get("urls")
        if isinstance(urls, str):
            urls = [urls]
        if not isinstance(urls, list) or not urls or not all(isinstance(url, str) and url for url in urls):
            raise ValueError("each ICE server requires one or more URLs")
        entry: dict[str, Any] = {"urls": urls}
        for key in ("username", "credential"):
            value = server.get(key)
            if value is not None:
                if not isinstance(value, str):
                    raise ValueError("ICE server %s must be a string" % key)
                entry[key] = value
        payload.append(entry)
    if not payload:
        raise ValueError("at least one ICE server is required")
    return payload


def _aiortc_ice_servers(servers: Iterable[dict[str, Any]]) -> list[Any]:
    from aiortc import RTCIceServer

    servers = tuple(servers)
    if not servers:
        return []
    return [
        RTCIceServer(
            urls=server["urls"],
            username=server.get("username"),
            credential=server.get("credential"),
        )
        for server in ice_server_payload(servers)
    ]


def h264_codec_capabilities() -> list[Any]:
    from aiortc import RTCRtpSender

    return [
        codec for codec in RTCRtpSender.getCapabilities("video").codecs
        if codec.mimeType.casefold() == "video/h264"
    ]


class WorkbenchVideoTrack:
    """Factory wrapper which delays importing PyAV / aiortc until serving."""

    @staticmethod
    def create(source: LatestVideoFrame) -> Any:
        import av
        import numpy
        from aiortc import VideoStreamTrack

        class Track(VideoStreamTrack):
            def __init__(self) -> None:
                super().__init__()
                self._last_sequence: int | None = None
                self._origin: float | None = None
                self._last_pts = -1

            async def recv(self) -> Any:
                snapshot = await source.next_after(self._last_sequence)
                self._last_sequence = snapshot.sequence
                if self._origin is None:
                    self._origin = snapshot.captured_at
                pts = int((snapshot.captured_at - self._origin) * VIDEO_CLOCK_RATE)
                pts = max(self._last_pts + 1, pts)
                self._last_pts = pts
                pixels = numpy.frombuffer(snapshot.rgb, dtype=numpy.uint8).reshape(
                    source.height, source.width, 3
                )
                # Put each component in a guarded neutral-grey plane. The
                # planar layout avoids the fragile R/G/B/R/G/B one-pixel luma
                # pattern while preserving all 8 bits through H.264 4:2:0.
                plane_stride = source.width + VIDEO_PLANE_GUARD
                coded_width = _coded_width(source.width)
                components = numpy.zeros(
                    (source.height, coded_width), dtype=numpy.uint8
                )
                for component in range(VIDEO_COMPONENTS):
                    start = component * plane_stride
                    components[:, start:start + source.width] = pixels[:, :, component]
                packed = numpy.repeat(components[:, :, None], VIDEO_COMPONENTS, axis=2)
                frame = av.VideoFrame.from_ndarray(packed, format="rgb24")
                frame.pts = pts
                frame.time_base = VIDEO_TIME_BASE
                return frame

        return Track()


class WebRtcVideoPeer:
    """One authenticated browser peer sending only the H.264 video track."""

    def __init__(
        self,
        source: LatestVideoFrame,
        ice_servers: Iterable[dict[str, Any]],
        on_state: Callable[[str], Awaitable[None]] | None = None,
    ):
        from aiortc import RTCBundlePolicy, RTCConfiguration, RTCPeerConnection

        self.source = source
        self.on_state = on_state
        self.pc = RTCPeerConnection(RTCConfiguration(
            iceServers=_aiortc_ice_servers(ice_servers),
            bundlePolicy=RTCBundlePolicy.MAX_BUNDLE,
        ))
        self.track = WorkbenchVideoTrack.create(source)
        self._closed = False

        @self.pc.on("connectionstatechange")
        async def connection_state_changed() -> None:
            state = self.pc.connectionState
            if self.on_state is not None:
                await self.on_state(state)
            if state in {"failed", "closed"}:
                await self.close()

    async def accept_offer(self, sdp: str, description_type: str = "offer") -> dict[str, str]:
        from aiortc import RTCRtpSender, RTCSessionDescription

        if description_type != "offer" or not isinstance(sdp, str) or not sdp:
            raise ValueError("invalid WebRTC offer")
        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=description_type))
        sender = self.pc.addTrack(self.track)
        transceiver = next(
            item for item in self.pc.getTransceivers() if item.sender is sender
        )
        h264 = [
            codec for codec in RTCRtpSender.getCapabilities("video").codecs
            if codec.mimeType.casefold() == "video/h264"
        ]
        if not h264:
            raise RuntimeError("this host has no H.264 WebRTC encoder")
        transceiver.setCodecPreferences(h264)
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        if self.pc.localDescription is None:
            raise RuntimeError("WebRTC answer was not created")
        return {
            "type": self.pc.localDescription.type,
            "sdp": self.pc.localDescription.sdp,
            "codec": "H264",
            "width": _coded_width(self.source.width),
            "height": self.source.height,
            "logicalWidth": self.source.width,
            "logicalHeight": self.source.height,
            "packing": VIDEO_PACKING,
        }

    async def stats(self) -> dict[str, int | float | str]:
        report = await self.pc.getStats()
        result: dict[str, int | float | str] = {"state": self.pc.connectionState}
        for item in report.values():
            if item.type == "outbound-rtp" and getattr(item, "kind", None) == "video":
                result.update({
                    "bytes_sent": int(getattr(item, "bytesSent", 0)),
                    "packets_sent": int(getattr(item, "packetsSent", 0)),
                })
            elif item.type == "remote-inbound-rtp" and getattr(item, "kind", None) == "video":
                result.update({
                    "packets_lost": int(getattr(item, "packetsLost", 0)),
                    "round_trip_time": float(getattr(item, "roundTripTime", 0.0) or 0.0),
                })
        return result

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.track.stop()
        await self.pc.close()
