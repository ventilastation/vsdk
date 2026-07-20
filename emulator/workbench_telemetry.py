"""Shared receiver for the workbench's latest-column UDP telemetry.

The workbench sends one 870-byte datagram for each four-column chunk of a
captured APA102 frame.  This module deliberately does *not* assemble complete
frames or request retransmission: a missing packet should leave only its
columns stale, not stall a live preview.  It is used by both the desktop
emulator and the remote-workbench gateway.
"""

from __future__ import annotations

from dataclasses import dataclass
import socket
import threading
import time
from typing import Optional


MAGIC = 0xA1
HEADER_BYTES = 6  # magic(1) + frame_seq(4, little-endian) + chunk_index(1)
COLUMNS = 256
LEDS = 54
BYTES_PER_LED = 4
COLUMNS_PER_CHUNK = 4
NUM_CHUNKS = COLUMNS // COLUMNS_PER_CHUNK
CHUNK_PAYLOAD_BYTES = COLUMNS_PER_CHUNK * LEDS * BYTES_PER_LED
PACKET_BYTES = HEADER_BYTES + CHUNK_PAYLOAD_BYTES
FRAME_BYTES = COLUMNS * LEDS * BYTES_PER_LED
HELLO_INTERVAL_S = 1.0
SNAPSHOT_INTERVAL_S = 1 / 30


def seq_ge(candidate: int, previous: int) -> bool:
    """Compare wrapping uint32 workbench sequence numbers."""
    return ((candidate - previous) & 0xFFFFFFFF) < 0x80000000


@dataclass(frozen=True)
class TelemetrySnapshot:
    """A coherent copy of the latest known columns plus freshness metadata."""

    apa102: bytes
    newest_sequence: Optional[int]
    chunk_sequences: tuple[Optional[int], ...]

    @property
    def stale_chunks(self) -> int:
        if self.newest_sequence is None:
            return NUM_CHUNKS
        return sum(sequence != self.newest_sequence for sequence in self.chunk_sequences)


class LatestColumnBuffer:
    """Thread-safe persistent APA102 buffer with per-chunk freshness guards."""

    def __init__(self) -> None:
        self._apa102 = bytearray(FRAME_BYTES)
        self._last_sequence: list[Optional[int]] = [None] * NUM_CHUNKS
        self._newest_sequence: Optional[int] = None
        self._lock = threading.Lock()
        self.accepted_packets = 0
        self.rejected_packets = 0
        self.stale_packets = 0

    def ingest(self, packet: bytes) -> bool:
        """Apply one valid, not-stale chunk. Return whether it changed state."""
        if len(packet) != PACKET_BYTES or packet[0] != MAGIC:
            self.rejected_packets += 1
            return False

        chunk_index = packet[5]
        if chunk_index >= NUM_CHUNKS:
            self.rejected_packets += 1
            return False

        sequence = int.from_bytes(packet[1:5], "little")
        with self._lock:
            previous = self._last_sequence[chunk_index]
            if previous is not None and not seq_ge(sequence, previous):
                self.stale_packets += 1
                return False

            offset = chunk_index * CHUNK_PAYLOAD_BYTES
            self._apa102[offset:offset + CHUNK_PAYLOAD_BYTES] = packet[HEADER_BYTES:]
            self._last_sequence[chunk_index] = sequence
            if self._newest_sequence is None or seq_ge(sequence, self._newest_sequence):
                self._newest_sequence = sequence
            self.accepted_packets += 1
            return True

    def snapshot(self) -> TelemetrySnapshot:
        """Copy the latest column state without waiting for a complete frame."""
        with self._lock:
            return TelemetrySnapshot(
                apa102=bytes(self._apa102),
                newest_sequence=self._newest_sequence,
                chunk_sequences=tuple(self._last_sequence),
            )


class WorkbenchTelemetryClient:
    """UDP client lifecycle shared by the desktop emulator and gateway.

    This class only owns the UDP socket and latest-column receiver.  Callers
    decide how/when snapshots are decoded and distributed.
    """

    def __init__(self, host: str, port: int, receiver: LatestColumnBuffer | None = None) -> None:
        self.host = host
        self.port = port
        self.receiver = receiver or LatestColumnBuffer()
        self.sock: socket.socket | None = None
        self.last_hello_at = 0.0

    def setup(self, timeout: float = 0.5) -> None:
        self.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # connect() sends no UDP packet. It records the intended peer and lets
        # recv()/send() filter and use the resolved workbench address.
        sock.connect((self.host, self.port))
        sock.settimeout(timeout)
        self.sock = sock
        self.last_hello_at = 0.0

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
        self.sock = None

    def send(self, payload: bytes) -> None:
        if self.sock is None:
            return
        self.sock.send(payload)

    def send_hello_if_due(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if now - self.last_hello_at < HELLO_INTERVAL_S:
            return False
        self.send(b"hello\n")
        self.last_hello_at = now
        return True

    def receive_once(self, size: int = 2048) -> bool:
        if self.sock is None:
            return False
        return self.receiver.ingest(self.sock.recv(size))

    def snapshot(self) -> TelemetrySnapshot:
        return self.receiver.snapshot()
