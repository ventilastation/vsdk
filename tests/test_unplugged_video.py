"""Synthetic disconnected-display and USB hot-plug behavior."""

import asyncio
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "emulator"))

from remote_gateway import (  # noqa: E402
    BrowserSession,
    GatewayConfig,
    INPUT,
    LEASE_REQUEST,
    Principal,
    RemoteGatewayService,
    SerialBridge,
    decode_message,
    encode_message,
)
from unplugged_video import (  # noqa: E402
    COLUMNS,
    LEDS,
    MESSAGE_COLOR,
    TINY_FONT,
    UnpluggedFrameStream,
    render_unplugged_frame,
)


class UnpluggedFrameTests(unittest.TestCase):
    def test_glyph_subset_matches_rom_menu_source(self):
        from PIL import Image

        image = Image.open(
            ROOT / "system/shared/other/images/tinyfont_white.png"
        ).convert("RGBA")
        for character, expected_rows in TINY_FONT.items():
            actual_rows = []
            for y in range(6):
                bits = 0
                for x in range(3):
                    red, _green, _blue, alpha = image.getpixel((ord(character) * 4 + x, y))
                    if alpha > 0 and red > 0:
                        bits |= 1 << (2 - x)
                actual_rows.append(bits)
            self.assertEqual(tuple(actual_rows), expected_rows, character)

    def test_frame_uses_native_rgb_geometry_and_warning_color(self):
        frame = render_unplugged_frame()
        self.assertEqual(len(frame), COLUMNS * LEDS * 3)
        pixels = [frame[index:index + 3] for index in range(0, len(frame), 3)]
        lit = [pixel for pixel in pixels if pixel != b"\0\0\0"]
        self.assertTrue(lit)
        self.assertEqual(set(lit), {bytes(MESSAGE_COLOR)})

    def test_animation_stops_after_a_minute_and_resets_after_replug(self):
        stream = UnpluggedFrameStream()
        self.assertTrue(stream.set_connected(False, 100.0))
        first = stream.next_frame(100.0)
        self.assertIsNotNone(first)
        self.assertIsNone(stream.next_frame(100.49))
        second = stream.next_frame(100.5)
        self.assertIsNotNone(second)
        self.assertNotEqual(first, second)
        final = stream.next_frame(160.0)
        self.assertEqual(final, render_unplugged_frame(from_outermost_led=True))
        self.assertNotEqual(final, bytes(COLUMNS * LEDS * 3))
        self.assertIsNone(stream.next_frame(160.1))
        self.assertEqual(stream.current_frame(300.0), final)
        self.assertIsNone(stream.next_frame(300.0))
        self.assertTrue(stream.set_connected(True, 170.0))
        self.assertIsNone(stream.current_frame(170.0))
        self.assertIsNone(stream.next_frame(170.0))
        self.assertTrue(stream.set_connected(False, 200.0))
        self.assertEqual(stream.next_frame(200.0), first)

    def test_final_message_starts_at_outermost_led(self):
        frame = render_unplugged_frame(from_outermost_led=True)
        outermost_led = LEDS - 1
        self.assertTrue(any(
            frame[(column * LEDS + outermost_led) * 3:
                  (column * LEDS + outermost_led) * 3 + 3]
            == bytes(MESSAGE_COLOR)
            for column in range(COLUMNS)
        ))

    def test_control_request_restart_starts_a_fresh_minute(self):
        stream = UnpluggedFrameStream()
        stream.set_connected(False, 100.0)
        stream.next_frame(160.0)
        self.assertIsNone(stream.next_frame(160.1))

        self.assertTrue(stream.restart(200.0))
        self.assertEqual(stream.next_frame(200.0), render_unplugged_frame(0))
        self.assertIsNotNone(stream.next_frame(259.5))
        self.assertEqual(
            stream.next_frame(260.0),
            render_unplugged_frame(from_outermost_led=True),
        )

        stream.set_connected(True, 300.0)
        self.assertFalse(stream.restart(301.0))
        self.assertIsNone(stream.next_frame(301.0))


class _FakeSerial:
    def __init__(self):
        self.writes = []
        self.fail = False
        self.closed = False

    def read(self, _size):
        if self.fail:
            raise OSError("unplugged")
        time.sleep(0.002)
        return b""

    def write(self, payload):
        if self.fail:
            raise OSError("unplugged")
        self.writes.append(payload)

    def close(self):
        self.closed = True


class SerialBridgeTests(unittest.TestCase):
    def test_auto_port_waits_for_one_serial_device(self):
        bridge = SerialBridge(
            "auto", lambda _event: None, lambda _error: None, lambda _state: None
        )
        with mock.patch("remote_gateway.glob.glob", return_value=[]):
            with self.assertRaises(OSError):
                bridge._resolved_port()
        with mock.patch(
            "remote_gateway.glob.glob",
            side_effect=[["/dev/cu.usbmodem1"], [], []],
        ):
            self.assertEqual(bridge._resolved_port(), "/dev/cu.usbmodem1")

    def test_bridge_retries_and_reconnects_after_unplug(self):
        available = threading.Event()
        connections = []
        states = []

        def factory(_port, _baud, timeout):
            self.assertEqual(timeout, 0.1)
            if not available.is_set():
                raise OSError("absent")
            connection = _FakeSerial()
            connections.append(connection)
            return connection

        bridge = SerialBridge(
            "/dev/test",
            lambda _event: None,
            lambda error: self.fail(str(error)),
            states.append,
            serial_factory=factory,
            retry_interval_s=0.005,
        )
        bridge.start()
        try:
            self.assertEqual(states, [False])
            available.set()
            self.assertTrue(self._wait_for(lambda: bridge.connected))
            bridge.write(b"input")
            self.assertEqual(connections[-1].writes, [b"input"])

            available.clear()
            connections[-1].fail = True
            self.assertTrue(self._wait_for(lambda: not bridge.connected))
            self.assertEqual(states[-1], False)

            available.set()
            self.assertTrue(self._wait_for(lambda: bridge.connected and len(connections) == 2))
            self.assertEqual(states[-1], True)
        finally:
            bridge.close()

    @staticmethod
    def _wait_for(predicate, timeout=1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.005)
        return False


class _FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)


class DisconnectedInputTests(unittest.IsolatedAsyncioTestCase):
    async def test_telemetry_resolution_failure_does_not_stop_gateway_task(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RemoteGatewayService(GatewayConfig(
                board="workbench-1",
                audience="test",
                ticket_key=b"k" * 32,
                state_path=Path(directory) / "state.sqlite3",
                workbench_host="missing.local",
                workbench_port=5005,
                serial_port="/dev/absent",
                allowed_origins=("https://example.test",),
                auth_mode="trusted-proxy",
            ))
            service.telemetry.setup = mock.Mock(side_effect=OSError("name not known"))
            task = asyncio.create_task(service._telemetry_connection_loop())
            try:
                await asyncio.sleep(0.05)
                self.assertFalse(task.done())
                self.assertEqual(service._telemetry_connect_error, "name not known")
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                service.store.close()

    async def test_usb_connection_keeps_warning_until_fresh_telemetry(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RemoteGatewayService(GatewayConfig(
                board="workbench-1",
                audience="test",
                ticket_key=b"k" * 32,
                state_path=Path(directory) / "state.sqlite3",
                workbench_host="192.0.2.1",
                workbench_port=5005,
                serial_port="/dev/absent",
                allowed_origins=("https://example.test",),
                auth_mode="trusted-proxy",
            ))
            service._unplugged_video.set_connected(False, time.monotonic())
            published = []

            async def publish(rgb):
                published.append(rgb)

            service._publish_rgb = publish
            service._publish_snapshot = mock.AsyncMock()
            try:
                await service._set_serial_connection(True)
                self.assertFalse(service._unplugged_video.connected)

                await service._publish_capture_or_fallback(
                    service.telemetry.snapshot(), time.monotonic()
                )
                self.assertEqual(published, [render_unplugged_frame(0)])

                packet = (
                    bytes((0xA1, 1, 0, 0, 0, 0))
                    + bytes(4 * LEDS * 4)
                )
                self.assertTrue(service.telemetry.receiver.ingest(packet))
                now = time.monotonic()
                service._last_telemetry_at = now
                snapshot = service.telemetry.snapshot()
                self.assertTrue(service._telemetry_is_live(snapshot, now))
                await service._publish_capture_or_fallback(snapshot, now)
                self.assertTrue(service._unplugged_video.connected)
                service._publish_snapshot.assert_awaited_once_with(snapshot)
            finally:
                service.store.close()

    async def test_buffered_telemetry_is_not_treated_as_live_forever(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RemoteGatewayService(GatewayConfig(
                board="workbench-1",
                audience="test",
                ticket_key=b"k" * 32,
                state_path=Path(directory) / "state.sqlite3",
                workbench_host="192.0.2.1",
                workbench_port=5005,
                serial_port="/dev/absent",
                allowed_origins=("https://example.test",),
                auth_mode="trusted-proxy",
            ))
            try:
                packet = (
                    bytes((0xA1, 1, 0, 0, 0, 0))
                    + bytes(4 * LEDS * 4)
                )
                self.assertTrue(service.telemetry.receiver.ingest(packet))
                service._last_telemetry_at = 100.0
                self.assertFalse(
                    service._telemetry_is_live(service.telemetry.snapshot(), 102.1)
                )
            finally:
                service.store.close()

    async def test_control_request_restarts_disconnected_video_immediately(self):
        with tempfile.TemporaryDirectory() as directory:
            service = RemoteGatewayService(GatewayConfig(
                board="workbench-1",
                audience="test",
                ticket_key=b"k" * 32,
                state_path=Path(directory) / "state.sqlite3",
                workbench_host="192.0.2.1",
                workbench_port=5005,
                serial_port="/dev/absent",
                allowed_origins=("https://example.test",),
                auth_mode="trusted-proxy",
            ))
            websocket = _FakeWebSocket()
            principal = Principal("subject", "player@example.com", "controller")
            session = BrowserSession("session", websocket, principal)
            service.sessions[session.session_id] = session
            service._unplugged_video.set_connected(False, time.monotonic() - 61.0)
            service._unplugged_video.next_frame(time.monotonic())
            published = []

            async def publish(rgb):
                published.append(rgb)

            service._publish_rgb = publish
            try:
                before_request = time.monotonic()
                await service._handle_browser_message(
                    session,
                    decode_message(encode_message(
                        LEASE_REQUEST,
                        1,
                        b'{"action":"request"}',
                    )),
                )
                after_request = time.monotonic()
            finally:
                service.store.close()

            self.assertEqual(published, [render_unplugged_frame(0)])
            self.assertGreaterEqual(
                service._unplugged_video.disconnected_at,
                before_request,
            )
            self.assertLessEqual(
                service._unplugged_video.disconnected_at,
                after_request,
            )

    async def test_non_neutral_input_is_audited_and_generates_menu_sound(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.sqlite3"
            service = RemoteGatewayService(GatewayConfig(
                board="workbench-1",
                audience="test",
                ticket_key=b"k" * 32,
                state_path=state_path,
                workbench_host="192.0.2.1",
                workbench_port=5005,
                serial_port="/dev/absent",
                allowed_origins=("https://example.test",),
                auth_mode="trusted-proxy",
            ))
            websocket = _FakeWebSocket()
            principal = Principal("subject", "player@example.com", "controller")
            session = BrowserSession("session", websocket, principal)
            service.sessions[session.session_id] = session
            lease = service.core.leases.request(
                service.config.board, principal, session.session_id, now=time.monotonic()
            )
            payload = bytes((1, 0, 0, 0)) + lease.generation.to_bytes(4, "little")
            try:
                await service._handle_browser_message(
                    session, decode_message(encode_message(INPUT, 1, payload))
                )
            finally:
                service.store.close()

            with sqlite3.connect(state_path) as connection:
                actions = connection.execute(
                    "SELECT action, detail FROM audit ORDER BY rowid"
                ).fetchall()
            self.assertIn(("input", "01,00,00,exit=0"), actions)
            self.assertIn(("host_event", "sound"), actions)
            self.assertTrue(websocket.messages)


if __name__ == "__main__":
    unittest.main()
