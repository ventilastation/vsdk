"""Tests for the workbench latest-column UDP receiver."""

import os
import socket
import sys
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

from workbench_telemetry import (  # noqa: E402
    CHUNK_PAYLOAD_BYTES,
    FRAME_BYTES,
    HEADER_BYTES,
    LatestColumnBuffer,
    MAGIC,
    NUM_CHUNKS,
    PACKET_BYTES,
    WorkbenchTelemetryClient,
    resolve_workbench_ipv4,
    seq_ge,
)


def packet(sequence, chunk_index, fill):
    return bytes((MAGIC,)) + sequence.to_bytes(4, "little") + bytes((chunk_index,)) + bytes((fill,)) * CHUNK_PAYLOAD_BYTES


class WorkbenchTelemetryTests(unittest.TestCase):
    def test_mdns_uses_zeroconf_when_os_resolver_is_missing(self):
        with (
            mock.patch("workbench_telemetry.socket.getaddrinfo", side_effect=socket.gaierror("missing")),
            mock.patch("workbench_telemetry.discover_workbench_ipv4", return_value="192.0.2.42") as discover,
        ):
            self.assertEqual(
                resolve_workbench_ipv4("ventilastation-workbench.local", 5005),
                "192.0.2.42",
            )
        discover.assert_called_once()

    def test_unknown_hostname_does_not_use_workbench_mdns_service(self):
        with (
            mock.patch("workbench_telemetry.socket.getaddrinfo", side_effect=socket.gaierror("missing")),
            mock.patch("workbench_telemetry.discover_workbench_ipv4") as discover,
            self.assertRaises(socket.gaierror),
        ):
            resolve_workbench_ipv4("other-board.invalid", 5005)
        discover.assert_not_called()

    def test_client_connects_to_resolved_ipv4(self):
        fake_socket = mock.MagicMock()
        with (
            mock.patch("workbench_telemetry.resolve_workbench_ipv4", return_value="192.0.2.42"),
            mock.patch("workbench_telemetry.socket.socket", return_value=fake_socket),
        ):
            client = WorkbenchTelemetryClient("ventilastation-workbench.local", 5005)
            client.setup(timeout=0.25)
        fake_socket.connect.assert_called_once_with(("192.0.2.42", 5005))
        fake_socket.settimeout.assert_called_once_with(0.25)
        self.assertEqual(client.resolved_host, "192.0.2.42")

    def test_packet_shape_matches_firmware_protocol(self):
        self.assertEqual(PACKET_BYTES, 870)
        self.assertEqual(FRAME_BYTES, 256 * 54 * 4)
        self.assertEqual(NUM_CHUNKS, 64)
        self.assertEqual(HEADER_BYTES, 6)

    def test_updates_only_the_received_chunk(self):
        receiver = LatestColumnBuffer()
        self.assertTrue(receiver.ingest(packet(5, 3, 0xA5)))

        snapshot = receiver.snapshot()
        start = 3 * CHUNK_PAYLOAD_BYTES
        self.assertEqual(snapshot.apa102[start:start + CHUNK_PAYLOAD_BYTES], bytes((0xA5,)) * CHUNK_PAYLOAD_BYTES)
        self.assertEqual(snapshot.apa102[0:CHUNK_PAYLOAD_BYTES], bytes(CHUNK_PAYLOAD_BYTES))
        self.assertEqual(snapshot.newest_sequence, 5)
        self.assertEqual(snapshot.chunk_sequences[3], 5)
        self.assertEqual(snapshot.stale_chunks, NUM_CHUNKS - 1)

    def test_old_chunk_cannot_stomp_newer_columns(self):
        receiver = LatestColumnBuffer()
        self.assertTrue(receiver.ingest(packet(10, 0, 0x11)))
        self.assertTrue(receiver.ingest(packet(11, 0, 0x22)))
        self.assertFalse(receiver.ingest(packet(10, 0, 0x33)))

        snapshot = receiver.snapshot()
        self.assertEqual(snapshot.apa102[:CHUNK_PAYLOAD_BYTES], bytes((0x22,)) * CHUNK_PAYLOAD_BYTES)
        self.assertEqual(receiver.stale_packets, 1)

    def test_wraparound_sequence_is_newer(self):
        receiver = LatestColumnBuffer()
        self.assertTrue(receiver.ingest(packet(0xFFFFFFFF, 1, 0x44)))
        self.assertTrue(receiver.ingest(packet(0, 1, 0x55)))
        self.assertFalse(receiver.ingest(packet(0xFFFFFFFE, 1, 0x66)))
        self.assertTrue(seq_ge(0, 0xFFFFFFFF))

    def test_malformed_packets_are_rejected_without_mutating_frame(self):
        receiver = LatestColumnBuffer()
        self.assertFalse(receiver.ingest(b"short"))
        malformed = bytearray(packet(1, 0, 0xFF))
        malformed[0] = 0
        self.assertFalse(receiver.ingest(bytes(malformed)))
        self.assertEqual(receiver.snapshot().apa102, bytes(FRAME_BYTES))
        self.assertEqual(receiver.rejected_packets, 2)


if __name__ == "__main__":
    unittest.main()
