"""Incremental parser for the runtime-to-host byte-stream protocol.

The desktop emulator currently dispatches parsed commands directly from
``comms.py``.  The remote gateway needs the same framing without importing the
desktop renderer or audio implementation, so this module turns bytes into
typed, bounded events only.
"""

from __future__ import annotations

from dataclasses import dataclass


class HostProtocolError(ValueError):
    """A command line declares an invalid payload length or shape."""


@dataclass(frozen=True)
class HostEvent:
    command: str
    args: tuple[str, ...]
    payload: bytes = b""


def _integer(value: str, command: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise HostProtocolError("%s has invalid length" % command) from error
    if result < 0:
        raise HostProtocolError("%s has negative length" % command)
    return result


def payload_length(command: str, args: tuple[str, ...]) -> int:
    """Return the exact payload length declared by a host command."""
    if command == "frame_rgb":
        return 256 * 54 * 3
    if command == "frame_apa102":
        return 256 * 54 * 4
    if command == "sprites":
        return 100 * 5
    if command == "debug":
        return 512
    if command in {"vs2_scene", "amap", "traceback", "info"}:
        return _integer(args[0] if args else "", command)
    if command == "povcal_state":
        return _integer(args[2] if len(args) == 3 else "", command)
    if command == "palette":
        return 1024 * _integer(args[0] if args else "", command)
    if command == "imagestrip":
        return _integer(args[1] if len(args) == 2 else "", command)
    if command == "achip":
        return _integer(args[1], command) if len(args) > 1 else 0
    if command == "aframe":
        return _integer(args[0] if args else "", command)
    return 0


class HostProtocolParser:
    """Parse arbitrary byte fragments into line-plus-payload ``HostEvent``s."""

    def __init__(self, max_line_bytes: int = 4096, max_payload_bytes: int = 512 * 1024):
        self.max_line_bytes = max_line_bytes
        self.max_payload_bytes = max_payload_bytes
        self._buffer = bytearray()
        self._pending: tuple[str, tuple[str, ...], int] | None = None

    def feed(self, data: bytes) -> list[HostEvent]:
        self._buffer.extend(data)
        events: list[HostEvent] = []
        while True:
            if self._pending is not None:
                command, args, length = self._pending
                if len(self._buffer) < length:
                    break
                payload = bytes(self._buffer[:length])
                del self._buffer[:length]
                self._pending = None
                events.append(HostEvent(command, args, payload))
                continue

            newline = self._buffer.find(b"\n")
            if newline < 0:
                if len(self._buffer) > self.max_line_bytes:
                    self._buffer.clear()
                    raise HostProtocolError("host command line exceeds limit")
                break

            raw_line = bytes(self._buffer[:newline]).strip()
            del self._buffer[:newline + 1]
            if not raw_line:
                continue
            try:
                parts = raw_line.decode("ascii").split()
            except UnicodeDecodeError as error:
                raise HostProtocolError("host command is not ASCII") from error
            command, *values = parts
            args = tuple(values)
            length = payload_length(command, args)
            if length > self.max_payload_bytes:
                raise HostProtocolError("%s payload exceeds limit" % command)
            if length:
                self._pending = (command, args, length)
                continue
            events.append(HostEvent(command, args))
        return events
