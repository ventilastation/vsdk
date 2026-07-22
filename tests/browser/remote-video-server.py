#!/usr/bin/env python3
"""Local aiortc sender for the browser-side packed-video alignment smoke."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

import numpy
from websockets.legacy.server import serve


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "emulator"))

from remote_video import LatestVideoFrame, WebRtcVideoPeer  # noqa: E402


def alignment_pattern() -> bytes:
    """Return identical RGB channels with unambiguous x/y geometry."""
    y, x = numpy.indices((256, 54))
    pixels = numpy.zeros((256, 54), dtype=numpy.uint8)
    pixels[((x * 7 + y * 3) % 29) < 4] = 255
    pixels[((x - 9) ** 2 + ((y - 73) // 3) ** 2) < 90] = 180
    pixels[(x >= 37) & (x <= 40) & (y >= 150) & (y <= 231)] = 96
    return numpy.repeat(pixels[:, :, None], 3, axis=2).tobytes()


async def main() -> None:
    source = LatestVideoFrame()
    peers: set[WebRtcVideoPeer] = set()

    async def publish() -> None:
        sequence = 0
        rgb = alignment_pattern()
        while True:
            sequence += 1
            await source.publish(sequence, rgb)
            await asyncio.sleep(1 / 30)

    async def signal(websocket) -> None:
        request = json.loads(await websocket.recv())
        peer = WebRtcVideoPeer(source, [])
        peers.add(peer)
        try:
            answer = await peer.accept_offer(request["sdp"], request.get("type", "offer"))
            await websocket.send(json.dumps(answer))
            await websocket.wait_closed()
        finally:
            peers.discard(peer)
            await peer.close()

    publisher = asyncio.create_task(publish())
    try:
        async with serve(signal, "127.0.0.1", 8770):
            print("server-ready", flush=True)
            await asyncio.Future()
    finally:
        publisher.cancel()
        await asyncio.gather(publisher, return_exceptions=True)
        await asyncio.gather(*(peer.close() for peer in peers), return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
