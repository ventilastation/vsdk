"""Authenticated remote gateway for a physical Ventilastation workbench.

The process is intentionally headless and loopback-only.  An authenticated
edge proxy publishes ``/auth/start`` and forwards a verified identity; the
gateway then mints a one-use ticket for the browser WebSocket at ``/ws``.  The
workbench's UDP and USB serial links never leave this computer.

Runtime dependencies are deliberately imported at the edges so the policy,
ticket, lease, and wire-protocol core remains testable with the Python standard
library alone.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import dataclass
import glob
from http import HTTPStatus
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import struct
import threading
import time
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

try:  # ``python -m emulator.remote_gateway``
    from .host_protocol import HostEvent, HostProtocolError, HostProtocolParser
    from .workbench_telemetry import (
        COLUMNS,
        LEDS,
        SNAPSHOT_INTERVAL_S,
        TelemetrySnapshot,
        WorkbenchTelemetryClient,
    )
    from .remote_video import (
        DEFAULT_ICE_SERVERS,
        LatestVideoFrame,
        VIDEO_CODED_HEIGHT,
        VIDEO_CODED_WIDTH,
        VIDEO_PACKING,
        WebRtcVideoPeer,
        ice_server_payload,
    )
    from .unplugged_video import UnpluggedFrameStream
except ImportError:  # direct ``python emulator/remote_gateway.py`` for bench use
    from host_protocol import HostEvent, HostProtocolError, HostProtocolParser
    from workbench_telemetry import (
        COLUMNS,
        LEDS,
        SNAPSHOT_INTERVAL_S,
        TelemetrySnapshot,
        WorkbenchTelemetryClient,
    )
    from remote_video import (
        DEFAULT_ICE_SERVERS,
        LatestVideoFrame,
        VIDEO_CODED_HEIGHT,
        VIDEO_CODED_WIDTH,
        VIDEO_PACKING,
        WebRtcVideoPeer,
        ice_server_payload,
    )
    from unplugged_video import UnpluggedFrameStream


PROTOCOL_MAGIC = b"VSRW"
PROTOCOL_VERSION = 1
HEADER = struct.Struct("<4sBBHIII")
MAX_MESSAGE_BYTES = 1024 * 1024
MAX_CONTROL_BYTES = 128 * 1024

HELLO = 0x01
HOST_EVENT = 0x03
STATUS = 0x04
ERROR = 0x05
LEASE = 0x06

INPUT = 0x10
HEARTBEAT = 0x12
LEASE_REQUEST = 0x13
OPERATOR_COMMAND = 0x14

VIDEO_OFFER = 0x20
VIDEO_ANSWER = 0x21
VIDEO_STATUS = 0x22
VIDEO_STOP = 0x23

INPUT_EXIT_EDGE = 0x01

ROLE_VIEWER = "viewer"
ROLE_CONTROLLER = "controller"
ROLE_OPERATOR = "operator"
ROLE_ADMIN = "admin"
ROLES = (ROLE_VIEWER, ROLE_CONTROLLER, ROLE_OPERATOR, ROLE_ADMIN)
CONTROL_ROLES = {ROLE_CONTROLLER, ROLE_OPERATOR, ROLE_ADMIN}
OPERATOR_ROLES = {ROLE_OPERATOR, ROLE_ADMIN}


class GatewayError(ValueError):
    """A request is valid syntax but cannot be safely accepted."""


class ProtocolError(GatewayError):
    """A WebSocket application message is malformed or unsupported."""


class AuthenticationError(GatewayError):
    """Identity or ticket verification failed."""


class AuthorizationError(GatewayError):
    """An authenticated identity lacks the requested board capability."""


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    if not value or any(character.isspace() for character in value):
        raise AuthenticationError("malformed token")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as error:
        raise AuthenticationError("malformed token") from error


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _json_payload(payload: bytes, limit: int = MAX_CONTROL_BYTES) -> dict[str, Any]:
    if len(payload) > limit:
        raise ProtocolError("control payload exceeds limit")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError("control payload is not valid JSON") from error
    if not isinstance(value, dict):
        raise ProtocolError("control payload must be an object")
    return value


def encode_message(message_type: int, sequence: int, payload: bytes = b"", flags: int = 0, timestamp_ms: int | None = None) -> bytes:
    if not 0 <= message_type <= 0xFF:
        raise ValueError("message type out of range")
    if len(payload) > MAX_MESSAGE_BYTES:
        raise ValueError("payload exceeds protocol limit")
    if timestamp_ms is None:
        timestamp_ms = int(time.monotonic() * 1000)
    return HEADER.pack(
        PROTOCOL_MAGIC,
        PROTOCOL_VERSION,
        message_type,
        flags & 0xFFFF,
        sequence & 0xFFFFFFFF,
        timestamp_ms & 0xFFFFFFFF,
        len(payload),
    ) + payload


@dataclass(frozen=True)
class WireMessage:
    message_type: int
    flags: int
    sequence: int
    timestamp_ms: int
    payload: bytes


def decode_message(data: bytes) -> WireMessage:
    if not isinstance(data, (bytes, bytearray)) or len(data) < HEADER.size:
        raise ProtocolError("message is shorter than header")
    magic, version, message_type, flags, sequence, timestamp_ms, length = HEADER.unpack(data[:HEADER.size])
    if magic != PROTOCOL_MAGIC:
        raise ProtocolError("invalid message magic")
    if version != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol version")
    if length > MAX_MESSAGE_BYTES or len(data) != HEADER.size + length:
        raise ProtocolError("message length mismatch")
    return WireMessage(message_type, flags, sequence, timestamp_ms, bytes(data[HEADER.size:]))


@dataclass(frozen=True)
class Principal:
    subject: str
    email: str
    role: str


@dataclass(frozen=True)
class TicketClaims:
    subject: str
    email: str
    role: str
    board: str
    audience: str
    issued_at: int
    expires_at: int
    jti: str

    def payload(self) -> dict[str, Any]:
        return {
            "sub": self.subject,
            "email": self.email,
            "role": self.role,
            "board": self.board,
            "aud": self.audience,
            "iat": self.issued_at,
            "exp": self.expires_at,
            "jti": self.jti,
        }


class TicketSigner:
    """Short-lived HMAC tickets used after edge identity validation."""

    def __init__(self, key: bytes, audience: str, board: str):
        if len(key) < 32:
            raise ValueError("ticket key must contain at least 32 random bytes")
        self.key = key
        self.audience = audience
        self.board = board

    def issue(self, principal: Principal, lifetime_s: int = 60, now: int | None = None) -> str:
        if principal.role not in ROLES:
            raise AuthorizationError("unknown role")
        if not 1 <= lifetime_s <= 60:
            raise ValueError("ticket lifetime must be from 1 to 60 seconds")
        now = int(time.time() if now is None else now)
        claims = TicketClaims(
            subject=principal.subject,
            email=principal.email,
            role=principal.role,
            board=self.board,
            audience=self.audience,
            issued_at=now,
            expires_at=now + lifetime_s,
            jti=secrets.token_urlsafe(24),
        )
        body = _b64url_encode(_json_bytes(claims.payload()))
        signature = _b64url_encode(hmac.new(self.key, body.encode("ascii"), hashlib.sha256).digest())
        return body + "." + signature

    def verify(self, token: str, now: int | None = None) -> TicketClaims:
        try:
            body, signature = token.split(".", 1)
        except ValueError as error:
            raise AuthenticationError("malformed ticket") from error
        expected = hmac.new(self.key, body.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature)):
            raise AuthenticationError("invalid ticket signature")
        try:
            payload = json.loads(_b64url_decode(body).decode("utf-8"))
            claims = TicketClaims(
                subject=str(payload["sub"]),
                email=str(payload["email"]).casefold(),
                role=str(payload["role"]),
                board=str(payload["board"]),
                audience=str(payload["aud"]),
                issued_at=int(payload["iat"]),
                expires_at=int(payload["exp"]),
                jti=str(payload["jti"]),
            )
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AuthenticationError("malformed ticket claims") from error
        now = int(time.time() if now is None else now)
        if claims.audience != self.audience or claims.board != self.board:
            raise AuthenticationError("ticket audience or board mismatch")
        if claims.role not in ROLES or not claims.subject or not claims.email or not claims.jti:
            raise AuthenticationError("invalid ticket claims")
        if claims.issued_at > now + 30 or claims.expires_at <= now or claims.expires_at - claims.issued_at > 60:
            raise AuthenticationError("ticket expired or not yet valid")
        return claims


class GatewayStore:
    """Local ACL, one-use ticket, and audit storage. All policy is default-deny."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS acl (
                board TEXT NOT NULL,
                email TEXT NOT NULL,
                role TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (board, email)
            );
            CREATE TABLE IF NOT EXISTS used_tickets (
                jti TEXT PRIMARY KEY,
                expires_at INTEGER NOT NULL,
                consumed_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit (
                at INTEGER NOT NULL,
                board TEXT NOT NULL,
                email TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT ''
            );
            """
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    @staticmethod
    def _email(email: str) -> str:
        value = email.strip().casefold()
        if not value or "@" not in value:
            raise ValueError("email is required")
        return value

    def grant(self, board: str, email: str, role: str, now: int | None = None) -> None:
        if role not in ROLES:
            raise ValueError("unknown role")
        now = int(time.time() if now is None else now)
        email = self._email(email)
        with self._lock:
            self._connection.execute(
                """INSERT INTO acl(board, email, role, enabled, updated_at)
                   VALUES (?, ?, ?, 1, ?)
                   ON CONFLICT(board, email) DO UPDATE SET role=excluded.role,
                   enabled=1, updated_at=excluded.updated_at""",
                (board, email, role, now),
            )
            self._audit_locked(now, board, email, "acl_grant", role)
            self._connection.commit()

    def revoke(self, board: str, email: str, now: int | None = None) -> None:
        now = int(time.time() if now is None else now)
        email = self._email(email)
        with self._lock:
            self._connection.execute(
                "UPDATE acl SET enabled=0, updated_at=? WHERE board=? AND email=?",
                (now, board, email),
            )
            self._audit_locked(now, board, email, "acl_revoke", "")
            self._connection.commit()

    def role_for(self, board: str, email: str) -> str | None:
        email = self._email(email)
        with self._lock:
            row = self._connection.execute(
                "SELECT role FROM acl WHERE board=? AND email=? AND enabled=1",
                (board, email),
            ).fetchone()
        return row[0] if row else None

    def consume_ticket(self, jti: str, expires_at: int, now: int | None = None) -> bool:
        now = int(time.time() if now is None else now)
        with self._lock:
            self._connection.execute("DELETE FROM used_tickets WHERE expires_at < ?", (now,))
            try:
                self._connection.execute(
                    "INSERT INTO used_tickets(jti, expires_at, consumed_at) VALUES (?, ?, ?)",
                    (jti, expires_at, now),
                )
            except sqlite3.IntegrityError:
                self._connection.commit()
                return False
            self._connection.commit()
            return True

    def audit(self, board: str, email: str, action: str, detail: str = "", now: int | None = None) -> None:
        now = int(time.time() if now is None else now)
        with self._lock:
            self._audit_locked(now, board, self._email(email), action, detail)
            self._connection.commit()

    def _audit_locked(self, now: int, board: str, email: str, action: str, detail: str) -> None:
        self._connection.execute(
            "INSERT INTO audit(at, board, email, action, detail) VALUES (?, ?, ?, ?, ?)",
            (now, board, email, action, detail[:256]),
        )


@dataclass(frozen=True)
class Lease:
    board: str
    email: str
    session_id: str
    generation: int
    # Maximum lease tenure. A controller must reconnect/reacquire after this
    # point even if it continues to send heartbeats.
    expires_at: float
    # Short liveness deadline extended by each accepted browser heartbeat.
    heartbeat_deadline: float


class LeaseManager:
    """Exclusive in-memory control leases, scoped to one physical board."""

    def __init__(self, duration_s: float = 600, heartbeat_timeout_s: float = 10):
        self.duration_s = duration_s
        self.heartbeat_timeout_s = heartbeat_timeout_s
        self._leases: dict[str, Lease] = {}
        self._generation = 0
        self._lock = threading.Lock()

    def request(self, board: str, principal: Principal, session_id: str, now: float | None = None) -> Lease:
        if principal.role not in CONTROL_ROLES:
            raise AuthorizationError("role cannot control this board")
        now = time.monotonic() if now is None else now
        with self._lock:
            current = self._leases.get(board)
            active = current and current.expires_at > now and current.heartbeat_deadline > now
            if active and current.session_id != session_id:
                raise AuthorizationError("board is controlled by another session")
            if active and current.session_id == session_id:
                lease = Lease(
                    board,
                    principal.email,
                    session_id,
                    current.generation,
                    min(now + self.duration_s, current.expires_at),
                    min(now + self.heartbeat_timeout_s, current.expires_at),
                )
            else:
                self._generation += 1
                lease = Lease(
                    board,
                    principal.email,
                    session_id,
                    self._generation,
                    now + self.duration_s,
                    now + self.heartbeat_timeout_s,
                )
            self._leases[board] = lease
            return lease

    def heartbeat(self, board: str, session_id: str, generation: int, now: float | None = None) -> Lease:
        now = time.monotonic() if now is None else now
        with self._lock:
            current = self._leases.get(board)
            if current is None or current.session_id != session_id or current.generation != generation:
                raise AuthorizationError("control lease is not current")
            if current.expires_at <= now or current.heartbeat_deadline <= now:
                self._leases.pop(board, None)
                raise AuthorizationError("control lease expired")
            lease = Lease(
                board,
                current.email,
                session_id,
                generation,
                current.expires_at,
                min(now + self.heartbeat_timeout_s, current.expires_at),
            )
            self._leases[board] = lease
            return lease

    def validate(self, board: str, session_id: str, generation: int, now: float | None = None) -> Lease:
        now = time.monotonic() if now is None else now
        with self._lock:
            current = self._leases.get(board)
            if current is None or current.expires_at <= now or current.heartbeat_deadline <= now:
                raise AuthorizationError("control lease expired")
            if current.session_id != session_id or current.generation != generation:
                raise AuthorizationError("control lease is not current")
            return current

    def release(self, board: str, session_id: str | None = None) -> Lease | None:
        with self._lock:
            current = self._leases.get(board)
            if current is None or (session_id is not None and current.session_id != session_id):
                return None
            return self._leases.pop(board)

    def expired(self, now: float | None = None) -> list[Lease]:
        now = time.monotonic() if now is None else now
        with self._lock:
            expired = [
                lease for lease in self._leases.values()
                if lease.expires_at <= now or lease.heartbeat_deadline <= now
            ]
            for lease in expired:
                self._leases.pop(lease.board, None)
            return expired

    def current(self, board: str) -> Lease | None:
        with self._lock:
            return self._leases.get(board)


class RemoteGatewayCore:
    """Policy layer independent of HTTP, WebSocket, serial, and UDP I/O."""

    def __init__(self, board: str, audience: str, ticket_key: bytes, store: GatewayStore, leases: LeaseManager | None = None):
        self.board = board
        self.store = store
        self.signer = TicketSigner(ticket_key, audience, board)
        self.leases = leases or LeaseManager()

    def ticket_for(self, subject: str, email: str, now: int | None = None) -> str:
        role = self.store.role_for(self.board, email)
        if role is None:
            raise AuthorizationError("identity is not allowed to use this board")
        principal = Principal(subject=subject, email=email.casefold(), role=role)
        self.store.audit(self.board, principal.email, "ticket_issue", role, now)
        return self.signer.issue(principal, now=now)

    def accept_ticket(self, token: str, now: int | None = None) -> Principal:
        claims = self.signer.verify(token, now)
        # Re-check the ACL at upgrade time: a ticket cannot preserve a role
        # that was revoked or downgraded after it was issued.
        role = self.store.role_for(self.board, claims.email)
        if role is None:
            raise AuthorizationError("identity is no longer allowed to use this board")
        if not self.store.consume_ticket(claims.jti, claims.expires_at, now):
            raise AuthenticationError("ticket was already used")
        principal = Principal(claims.subject, claims.email, role)
        self.store.audit(self.board, principal.email, "websocket_accept", role, now)
        return principal


class CloudflareAccessVerifier:
    """Validate the Access JWT assertion supplied by Cloudflare at /auth/start."""

    def __init__(self, team_domain: str, audience: str, issuer: str | None = None):
        self.team_domain = team_domain
        self.audience = audience
        self.issuer = issuer or "https://%s" % team_domain
        self._jwk_client = None

    def verify(self, assertion: str) -> tuple[str, str]:
        if not assertion:
            raise AuthenticationError("missing Cloudflare Access assertion")
        try:
            import jwt
        except ImportError as error:
            raise AuthenticationError("PyJWT[crypto] is required for Cloudflare Access validation") from error
        if self._jwk_client is None:
            self._jwk_client = jwt.PyJWKClient("https://%s/cdn-cgi/access/certs" % self.team_domain)
        try:
            key = self._jwk_client.get_signing_key_from_jwt(assertion).key
            claims = jwt.decode(
                assertion,
                key,
                algorithms=["RS256", "ES256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "sub", "email"]},
            )
            return str(claims["sub"]), str(claims["email"]).casefold()
        except Exception as error:
            raise AuthenticationError("invalid Cloudflare Access assertion") from error


class TrustedProxyIdentityVerifier:
    """Accept an identity injected by the private, authenticated edge proxy.

    This mode is deliberately safe only when the gateway is loopback-only and
    its sole ingress is a private reverse tunnel from the configured proxy.
    The edge removes client-supplied versions of these headers and copies them
    from its authenticated identity before forwarding the request. Some edges
    (including ngrok's managed Google OAuth action) expose a verified email
    but no stable subject header; in that case the verified email is used as
    the ticket subject. The ACL remains keyed by that same verified email.
    """

    def __init__(self, email_header: str, subject_header: str):
        self.email_header = email_header
        self.subject_header = subject_header

    def verify(self, headers: Any) -> tuple[str, str]:
        email = str(headers.get(self.email_header, "")).strip().casefold()
        subject = str(headers.get(self.subject_header, "")).strip()
        if not email or "@" not in email or len(email) > 254:
            raise AuthenticationError("missing trusted-proxy email")
        if subject and len(subject) > 512:
            raise AuthenticationError("invalid trusted-proxy subject")
        if not subject:
            subject = email
        return subject, email


def apa102_to_rgb(raw: bytes) -> bytes:
    """Decode calibrated APA102 capture data to RGB888 for the browser."""
    try:
        try:
            from .apa102 import decode_frame
        except ImportError:
            from apa102 import decode_frame
    except ImportError as error:
        raise RuntimeError("numpy is required for frame decoding") from error
    packed = decode_frame(raw)
    # decode_frame packs 0xAABBGGRR. On the supported little-endian hosts its
    # byte view is exactly R,G,B,A, so discard alpha without a Python pixel loop.
    return packed.view("uint8").reshape(-1, 4)[:, :3].tobytes()


@dataclass
class BrowserSession:
    session_id: str
    websocket: Any
    principal: Principal
    exit_pressed: bool = False
    last_audited_input: tuple[int, int, int, bool] | None = None
    video_peer: WebRtcVideoPeer | None = None


class SerialBridge:
    """Reconnectable writer/parser for the hot-pluggable USB workbench."""

    def __init__(
        self,
        port: str,
        on_event: Callable[[HostEvent], None],
        on_error: Callable[[Exception], None],
        on_connection: Callable[[bool], None],
        serial_factory: Callable[..., Any] | None = None,
        retry_interval_s: float = 0.5,
    ):
        self.port = port
        self.on_event = on_event
        self.on_error = on_error
        self.on_connection = on_connection
        self.serial_factory = serial_factory
        self.retry_interval_s = retry_interval_s
        self._serial = None
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._reported_connection: bool | None = None
        self._thread: threading.Thread | None = None
        self._write_lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def start(self) -> None:
        if self.serial_factory is None:
            try:
                import serial
            except ImportError as error:
                raise RuntimeError("pyserial is required for the workbench serial bridge") from error
            self.serial_factory = serial.Serial
        self._report_connection(False)
        self._thread = threading.Thread(target=self._reader, name="remote-workbench-serial", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        with self._write_lock:
            connection = self._serial
            self._serial = None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1)

    def write(self, payload: bytes) -> None:
        connection = None
        try:
            with self._write_lock:
                connection = self._serial
                if connection is None:
                    raise OSError("workbench serial is not connected")
                connection.write(payload)
        except Exception as error:
            if connection is not None:
                self._disconnect(connection)
            if isinstance(error, OSError):
                raise
            raise OSError("workbench serial write failed") from error

    def _report_connection(self, connected: bool) -> None:
        if connected:
            self._connected.set()
        else:
            self._connected.clear()
        if connected != self._reported_connection:
            self._reported_connection = connected
            self.on_connection(connected)

    def _disconnect(self, connection: Any) -> None:
        with self._write_lock:
            if self._serial is not connection:
                return
            self._serial = None
        try:
            connection.close()
        except Exception:
            pass
        self._report_connection(False)

    def _reader(self) -> None:
        parser = HostProtocolParser()
        while not self._stop.is_set():
            connection = self._serial
            if connection is None:
                try:
                    assert self.serial_factory is not None
                    connection = self.serial_factory(self._resolved_port(), 115200, timeout=0.1)
                except Exception:
                    self._report_connection(False)
                    self._stop.wait(self.retry_interval_s)
                    continue
                if self._stop.is_set():
                    connection.close()
                    break
                with self._write_lock:
                    self._serial = connection
                parser = HostProtocolParser()
                self._report_connection(True)
            try:
                data = connection.read(1024)
                if not data:
                    continue
                for event in parser.feed(data):
                    self.on_event(event)
            except HostProtocolError as error:
                self.on_error(error)
                parser = HostProtocolParser()
            except Exception:
                self._disconnect(connection)
                self._stop.wait(self.retry_interval_s)

    def _resolved_port(self) -> str:
        if self.port != "auto":
            return self.port
        matches: list[str] = []
        for pattern in ("/dev/cu.usbmodem*", "/dev/ttyACM*", "/dev/ttyUSB*"):
            matches.extend(glob.glob(pattern))
        matches = sorted(set(matches))
        if len(matches) != 1:
            raise OSError("waiting for one USB workbench serial device")
        return matches[0]


@dataclass(frozen=True)
class GatewayConfig:
    board: str
    audience: str
    ticket_key: bytes
    state_path: Path
    workbench_host: str
    workbench_port: int
    serial_port: str
    allowed_origins: tuple[str, ...]
    auth_mode: str = "cloudflare-access"
    access_team_domain: str = ""
    access_audience: str = ""
    trusted_email_header: str = "X-Remote-Email"
    trusted_subject_header: str = "X-Remote-Subject"
    bind_host: str = "127.0.0.1"
    bind_port: int = 8765
    ice_servers: tuple[dict[str, Any], ...] = DEFAULT_ICE_SERVERS


class RemoteGatewayService:
    """Loopback HTTP/WSS service, serial host, and workbench UDP subscriber."""

    def __init__(self, config: GatewayConfig):
        self.config = config
        self.store = GatewayStore(config.state_path)
        self.core = RemoteGatewayCore(config.board, config.audience, config.ticket_key, self.store)
        if config.auth_mode == "cloudflare-access":
            self.identity = CloudflareAccessVerifier(config.access_team_domain, config.access_audience)
        elif config.auth_mode == "trusted-proxy":
            self.identity = TrustedProxyIdentityVerifier(config.trusted_email_header, config.trusted_subject_header)
        else:
            raise RuntimeError("unsupported REMOTE_WORKBENCH_AUTH_MODE")
        self.telemetry = WorkbenchTelemetryClient(config.workbench_host, config.workbench_port)
        self.video_source = LatestVideoFrame(width=LEDS, height=COLUMNS)
        self.sessions: dict[str, BrowserSession] = {}
        self._sequence = 0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._unplugged_video = UnpluggedFrameStream()
        self._serial = SerialBridge(
            config.serial_port,
            self._serial_event,
            self._serial_error,
            self._serial_connection,
        )
        self._tasks: list[asyncio.Task[Any]] = []

    async def serve_forever(self) -> None:
        try:
            from websockets.legacy.server import serve
        except ImportError as error:
            raise RuntimeError("install websockets>=12,<13 to run the remote gateway") from error
        self._loop = asyncio.get_running_loop()
        self.telemetry.setup(timeout=0.2)
        self.telemetry.sock.setblocking(False)
        self._unplugged_video.set_connected(False, time.monotonic())
        self._serial.start()
        self._tasks = [
            asyncio.create_task(self._telemetry_loop()),
            asyncio.create_task(self._lease_loop()),
        ]
        try:
            async with serve(
                self._websocket_handler,
                self.config.bind_host,
                self.config.bind_port,
                process_request=self._process_request,
                max_size=MAX_MESSAGE_BYTES,
                ping_interval=20,
                ping_timeout=20,
            ):
                await asyncio.Future()
        finally:
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            await asyncio.gather(
                *(self._close_video_peer(session) for session in list(self.sessions.values())),
                return_exceptions=True,
            )
            self._serial.close()
            self.telemetry.close()
            self.store.close()

    async def _process_request(self, path: str, headers: Any):
        parsed = urlparse(path)
        if parsed.path != "/auth/start":
            if parsed.path == "/ws":
                return None
            return HTTPStatus.NOT_FOUND, [("Content-Type", "text/plain")], b"Not found\n"
        try:
            if self.config.auth_mode == "cloudflare-access":
                subject, email = self.identity.verify(headers.get("Cf-Access-Jwt-Assertion", ""))
            else:
                subject, email = self.identity.verify(headers)
            ticket = self.core.ticket_for(subject, email)
            body = self._auth_complete_page(ticket)
            return HTTPStatus.OK, [("Content-Type", "text/html; charset=utf-8"), ("Cache-Control", "no-store")], body
        except GatewayError as error:
            return HTTPStatus.FORBIDDEN, [("Content-Type", "text/plain; charset=utf-8"), ("Cache-Control", "no-store")], ("Access denied: %s\n" % error).encode("utf-8")

    def _auth_complete_page(self, ticket: str) -> bytes:
        origin = self.config.allowed_origins[0]
        script_ticket = json.dumps(ticket)
        script_origin = json.dumps(origin)
        document = """<!doctype html><meta charset=\"utf-8\"><title>Ventilastation connected</title>
<p>Authentication completed. You can return to the emulator.</p>
<script>
const ticket = %s;
const target = %s;
if (window.opener) {
  window.opener.postMessage({type: 'ventilastation-remote-ticket', ticket}, target);
  window.close();
} else {
  window.location.replace(target + '#remote_ticket=' + encodeURIComponent(ticket));
}
</script>""" % (script_ticket, script_origin)
        return document.encode("utf-8")

    async def _websocket_handler(self, websocket: Any, path: str) -> None:
        parsed = urlparse(path)
        if parsed.path != "/ws":
            await websocket.close(code=1008, reason="invalid endpoint")
            return
        origin = websocket.request_headers.get("Origin")
        if origin not in self.config.allowed_origins:
            await websocket.close(code=1008, reason="invalid origin")
            return
        ticket = parse_qs(parsed.query).get("ticket", [""])[0]
        try:
            principal = self.core.accept_ticket(ticket)
        except GatewayError:
            await websocket.close(code=1008, reason="authentication failed")
            return
        session = BrowserSession(secrets.token_urlsafe(18), websocket, principal)
        self.sessions[session.session_id] = session
        self.store.audit(self.config.board, principal.email, "connect", principal.role)
        await self._send_status(session, "connected")
        await self._send_hello(session)
        try:
            async for raw in websocket:
                if not isinstance(raw, bytes):
                    raise ProtocolError("text WebSocket messages are not accepted")
                await self._handle_browser_message(session, decode_message(raw))
        except (ProtocolError, GatewayError):
            await websocket.close(code=1008, reason="invalid request")
        finally:
            self.sessions.pop(session.session_id, None)
            released = self.core.leases.release(self.config.board, session.session_id)
            if released is not None:
                await self._neutralize(released.email, "disconnect")
                await self._broadcast_lease()
            await self._close_video_peer(session)
            self.store.audit(self.config.board, principal.email, "disconnect", "")

    async def _handle_browser_message(self, session: BrowserSession, message: WireMessage) -> None:
        if message.message_type == INPUT:
            if len(message.payload) != 8:
                raise ProtocolError("invalid input payload")
            joy1, joy2, extra, flags, generation = struct.unpack("<BBBBI", message.payload)
            if joy1 & 0x80 or joy2 & 0x80 or extra & 0x80 or flags & ~INPUT_EXIT_EDGE:
                raise ProtocolError("invalid input bits")
            self.core.leases.validate(self.config.board, session.session_id, generation)
            delivered = await self._write_serial(bytes((0x2A, joy1, joy2, extra)))
            exit_edge = bool(flags & INPUT_EXIT_EDGE)
            input_state = (joy1, joy2, extra, exit_edge)
            if input_state != session.last_audited_input:
                self.store.audit(
                    self.config.board,
                    session.principal.email,
                    "input",
                    "%02x,%02x,%02x,exit=%d" % (joy1, joy2, extra, exit_edge),
                )
                session.last_audited_input = input_state
                if not delivered and any(input_state):
                    # Make the disconnected smoke path exercise audible host
                    # events too, using the ROM menu's normal movement sound.
                    await self._broadcast_host_event(HostEvent(
                        "sound", ("alecu.vyruss/shoot3",)
                    ))
            if delivered and exit_edge and not session.exit_pressed:
                await self._write_serial(b"exit\n")
            session.exit_pressed = exit_edge
            return
        if message.message_type == VIDEO_OFFER:
            request = _json_payload(message.payload)
            await self._start_video_peer(session, request)
            return
        if message.message_type == VIDEO_STOP:
            if message.payload:
                raise ProtocolError("video stop payload must be empty")
            await self._close_video_peer(session)
            await self._send_video_status(session, "stopped")
            return
        if message.message_type == HEARTBEAT:
            if len(message.payload) != 8:
                raise ProtocolError("invalid heartbeat")
            generation, _last_server_sequence = struct.unpack("<II", message.payload)
            self.core.leases.heartbeat(self.config.board, session.session_id, generation)
            return
        if message.message_type == LEASE_REQUEST:
            request = _json_payload(message.payload)
            action = request.get("action")
            if action == "request":
                lease = self.core.leases.request(self.config.board, session.principal, session.session_id)
                self.store.audit(self.config.board, session.principal.email, "lease_grant", str(lease.generation))
                await self._broadcast_lease()
            elif action == "release":
                lease = self.core.leases.release(self.config.board, session.session_id)
                if lease is not None:
                    await self._neutralize(session.principal.email, "release")
                    await self._broadcast_lease()
            else:
                raise ProtocolError("invalid lease action")
            return
        if message.message_type == OPERATOR_COMMAND:
            request = _json_payload(message.payload)
            if session.principal.role not in OPERATOR_ROLES:
                raise AuthorizationError("role cannot operate this board")
            generation = request.get("lease_generation")
            if not isinstance(generation, int):
                raise ProtocolError("operator command requires lease generation")
            self.core.leases.validate(self.config.board, session.session_id, generation)
            if request.get("action") == "reset":
                self.telemetry.send(b"reset\n")
                self.store.audit(self.config.board, session.principal.email, "reset", "")
            elif request.get("action") == "rpm":
                rpm = request.get("rpm")
                if not isinstance(rpm, int) or not 0 <= rpm <= 700:
                    raise ProtocolError("rpm must be an integer from 0 to 700")
                self.telemetry.send(("rpm %d\n" % rpm).encode("ascii"))
                self.store.audit(self.config.board, session.principal.email, "rpm", str(rpm))
            else:
                raise ProtocolError("invalid operator action")
            return
        raise ProtocolError("unsupported browser message")

    async def _start_video_peer(self, session: BrowserSession, request: dict[str, Any]) -> None:
        description_type = request.get("type")
        sdp = request.get("sdp")
        if description_type != "offer" or not isinstance(sdp, str) or not sdp:
            raise ProtocolError("invalid WebRTC offer")
        if len(sdp.encode("utf-8")) > MAX_CONTROL_BYTES:
            raise ProtocolError("WebRTC offer exceeds limit")
        await self._close_video_peer(session)
        peer: WebRtcVideoPeer | None = None

        async def on_state(state: str) -> None:
            if peer is not None and session.video_peer is peer:
                self.store.audit(self.config.board, session.principal.email, "video_state", state)
                await self._send_video_status(session, state)

        try:
            peer = WebRtcVideoPeer(self.video_source, self.config.ice_servers, on_state=on_state)
            session.video_peer = peer
            answer = await peer.accept_offer(sdp, description_type)
        except Exception as error:
            if peer is not None:
                await peer.close()
            session.video_peer = None
            raise ProtocolError("could not negotiate H.264 WebRTC video") from error
        self.store.audit(self.config.board, session.principal.email, "video_offer", "H264")
        self._sequence = (self._sequence + 1) & 0xFFFFFFFF
        await session.websocket.send(encode_message(
            VIDEO_ANSWER,
            self._sequence,
            _json_bytes(answer),
        ))
        await self._send_video_status(session, "connecting")

    async def _close_video_peer(self, session: BrowserSession) -> None:
        peer = session.video_peer
        session.video_peer = None
        if peer is not None:
            await peer.close()

    async def _send_video_status(self, session: BrowserSession, state: str) -> None:
        if session.session_id not in self.sessions:
            return
        payload: dict[str, Any] = {
            "state": state,
            "codec": "H264",
            "width": VIDEO_CODED_WIDTH,
            "height": VIDEO_CODED_HEIGHT,
            "logicalWidth": LEDS,
            "logicalHeight": COLUMNS,
            "packing": VIDEO_PACKING,
        }
        if state == "connected" and session.video_peer is not None:
            try:
                payload["stats"] = await session.video_peer.stats()
            except Exception:
                pass
        self._sequence = (self._sequence + 1) & 0xFFFFFFFF
        try:
            await session.websocket.send(encode_message(
                VIDEO_STATUS,
                self._sequence,
                _json_bytes(payload),
            ))
        except Exception:
            pass

    async def _telemetry_loop(self) -> None:
        loop = asyncio.get_running_loop()
        last_snapshot = 0.0
        while True:
            now = time.monotonic()
            try:
                self.telemetry.send_hello_if_due(now)
                if self._serial.connected and now - last_snapshot >= SNAPSHOT_INTERVAL_S:
                    snapshot = self.telemetry.snapshot()
                    await self._publish_snapshot(snapshot)
                    last_snapshot = now
                elif not self._serial.connected:
                    synthetic = self._unplugged_video.next_frame(now)
                    if synthetic is not None:
                        await self._publish_rgb(synthetic)
                try:
                    packet = await asyncio.wait_for(loop.sock_recv(self.telemetry.sock, 2048), timeout=0.02)
                except asyncio.TimeoutError:
                    continue
                self.telemetry.receiver.ingest(packet)
            except (OSError, RuntimeError):
                await asyncio.sleep(0.2)

    async def _publish_snapshot(self, snapshot: TelemetrySnapshot) -> None:
        if (
            snapshot.newest_sequence is None
            or not any(session.video_peer is not None for session in self.sessions.values())
        ):
            return
        rgb = await asyncio.to_thread(apa102_to_rgb, snapshot.apa102)
        await self._publish_rgb(rgb)

    async def _publish_rgb(self, rgb: bytes) -> None:
        self._sequence = (self._sequence + 1) & 0xFFFFFFFF
        await self.video_source.publish(self._sequence, rgb)

    async def _write_serial(self, payload: bytes) -> bool:
        if not self._serial.connected:
            return False
        try:
            await asyncio.to_thread(self._serial.write, payload)
            return True
        except OSError:
            return False

    async def _lease_loop(self) -> None:
        while True:
            await asyncio.sleep(1)
            # An ACL change is authoritative immediately. The edge proxy
            # prevents future login, while this check closes already-open
            # sockets and releases their control lease.
            for session in list(self.sessions.values()):
                current_role = self.store.role_for(self.config.board, session.principal.email)
                if current_role != session.principal.role:
                    await session.websocket.close(code=1008, reason="access changed")
            for lease in self.core.leases.expired():
                await self._neutralize(lease.email, "timeout")
                await self._broadcast_lease()

    async def _neutralize(self, email: str, reason: str) -> None:
        # Send three canonical neutral frames, as specified, through the one
        # serial writer before another lease may become useful.
        for _ in range(3):
            try:
                await asyncio.to_thread(self._serial.write, b"\x2a\x00\x00\x00")
            except OSError:
                break
        self.store.audit(self.config.board, email, "neutralize", reason)

    async def _send_hello(self, session: BrowserSession) -> None:
        lease = self.core.leases.current(self.config.board)
        payload = _json_bytes({
            "board": self.config.board,
            "board_connected": self._serial.connected,
            "email": session.principal.email,
            "role": session.principal.role,
            "width": COLUMNS,
            "height": LEDS,
            "video": {
                "transport": "webrtc",
                "codec": "H264",
                "width": VIDEO_CODED_WIDTH,
                "height": VIDEO_CODED_HEIGHT,
                "logicalWidth": LEDS,
                "logicalHeight": COLUMNS,
                "packing": VIDEO_PACKING,
                "fps": round(1 / SNAPSHOT_INTERVAL_S),
                "iceServers": ice_server_payload(self.config.ice_servers),
            },
            "lease_generation": lease.generation if lease and lease.session_id == session.session_id else None,
            "lease_holder": lease.email if lease else None,
        })
        self._sequence = (self._sequence + 1) & 0xFFFFFFFF
        await session.websocket.send(encode_message(HELLO, self._sequence, payload))

    async def _send_status(self, session: BrowserSession, state: str) -> None:
        self._sequence = (self._sequence + 1) & 0xFFFFFFFF
        await session.websocket.send(encode_message(STATUS, self._sequence, _json_bytes({"state": state})))

    async def _broadcast_lease(self) -> None:
        lease = self.core.leases.current(self.config.board)
        payload = _json_bytes({
            "holder": lease.email if lease else None,
            "generation": lease.generation if lease else None,
            "expires_at": lease.expires_at if lease else None,
        })
        self._sequence = (self._sequence + 1) & 0xFFFFFFFF
        message = encode_message(LEASE, self._sequence, payload)
        await asyncio.gather(*(session.websocket.send(message) for session in self.sessions.values()), return_exceptions=True)

    def _serial_event(self, event: HostEvent) -> None:
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._broadcast_host_event(event), self._loop)

    def _serial_error(self, error: Exception) -> None:
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._broadcast_error("serial", str(error)), self._loop)

    def _serial_connection(self, connected: bool) -> None:
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._set_serial_connection(connected), self._loop
            )

    async def _set_serial_connection(self, connected: bool) -> None:
        now = time.monotonic()
        if not self._unplugged_video.set_connected(connected, now):
            return
        state = "connected" if connected else "unplugged"
        for email in {session.principal.email for session in self.sessions.values()}:
            self.store.audit(self.config.board, email, "board_connection", state)
        self._sequence = (self._sequence + 1) & 0xFFFFFFFF
        message = encode_message(STATUS, self._sequence, _json_bytes({
            "state": "board",
            "board_connected": connected,
            "synthetic_seconds": 0 if connected else int(self._unplugged_video.duration_s),
        }))
        await asyncio.gather(
            *(session.websocket.send(message) for session in self.sessions.values()),
            return_exceptions=True,
        )
        if connected:
            # Replace a synthetic warning immediately when a real capture is
            # already buffered; fresh UDP chunks will continue replacing it.
            await self._publish_snapshot(self.telemetry.snapshot())

    async def _broadcast_host_event(self, event: HostEvent) -> None:
        allowed = {"sound", "music", "musicstop", "notes", "base", "info", "traceback", "achip", "aframe", "amap", "astop"}
        if event.command not in allowed:
            return
        # Chip-audio payloads are accepted by the parser but not sent unless a
        # browser implementation declares support in a later protocol version.
        if event.command in {"achip", "aframe", "amap", "astop"}:
            return
        for email in {session.principal.email for session in self.sessions.values()}:
            self.store.audit(self.config.board, email, "host_event", event.command)
        name = event.command.encode("ascii")
        arguments = _json_bytes(list(event.args))
        payload = struct.pack("<BHI", len(name), len(arguments), len(event.payload)) + name + arguments + event.payload
        self._sequence = (self._sequence + 1) & 0xFFFFFFFF
        message = encode_message(HOST_EVENT, self._sequence, payload)
        await asyncio.gather(*(session.websocket.send(message) for session in self.sessions.values()), return_exceptions=True)

    async def _broadcast_error(self, code: str, detail: str) -> None:
        self._sequence = (self._sequence + 1) & 0xFFFFFFFF
        message = encode_message(ERROR, self._sequence, _json_bytes({"code": code, "message": detail[:160]}))
        await asyncio.gather(*(session.websocket.send(message) for session in self.sessions.values()), return_exceptions=True)


def _read_key(path: str) -> bytes:
    value = Path(path).read_bytes().strip()
    if len(value) == 64:
        try:
            return bytes.fromhex(value.decode("ascii"))
        except ValueError:
            pass
    return value


def config_from_environment() -> GatewayConfig:
    def required(name: str) -> str:
        value = os.environ.get(name, "").strip()
        if not value:
            raise RuntimeError("%s is required" % name)
        return value

    origins = tuple(value.strip() for value in required("REMOTE_WORKBENCH_ALLOWED_ORIGINS").split(",") if value.strip())
    if not origins:
        raise RuntimeError("REMOTE_WORKBENCH_ALLOWED_ORIGINS is required")
    key = _read_key(required("REMOTE_WORKBENCH_TICKET_KEY_FILE"))
    auth_mode = os.environ.get("REMOTE_WORKBENCH_AUTH_MODE", "trusted-proxy").strip()
    if auth_mode not in {"trusted-proxy", "cloudflare-access"}:
        raise RuntimeError("REMOTE_WORKBENCH_AUTH_MODE must be trusted-proxy or cloudflare-access")
    if auth_mode == "cloudflare-access":
        access_team_domain = required("CF_ACCESS_TEAM_DOMAIN")
        access_audience = required("CF_ACCESS_AUDIENCE")
    else:
        access_team_domain = ""
        access_audience = ""
    ice_json = os.environ.get(
        "REMOTE_WORKBENCH_ICE_SERVERS_JSON",
        json.dumps(DEFAULT_ICE_SERVERS),
    )
    try:
        ice_value = json.loads(ice_json)
        if not isinstance(ice_value, list):
            raise ValueError("ICE server configuration must be an array")
        ice_servers = tuple(ice_server_payload(ice_value))
    except (json.JSONDecodeError, ValueError) as error:
        raise RuntimeError("REMOTE_WORKBENCH_ICE_SERVERS_JSON is invalid") from error
    return GatewayConfig(
        board=required("REMOTE_WORKBENCH_BOARD"),
        audience=required("REMOTE_WORKBENCH_TICKET_AUDIENCE"),
        ticket_key=key,
        state_path=Path(required("REMOTE_WORKBENCH_STATE_DB")),
        workbench_host=os.environ.get("REMOTE_WORKBENCH_HOST", "ventilastation-workbench.local"),
        workbench_port=int(os.environ.get("REMOTE_WORKBENCH_PORT", "5005")),
        serial_port=required("REMOTE_WORKBENCH_SERIAL_PORT"),
        allowed_origins=origins,
        auth_mode=auth_mode,
        access_team_domain=access_team_domain,
        access_audience=access_audience,
        trusted_email_header=os.environ.get("REMOTE_WORKBENCH_TRUSTED_EMAIL_HEADER", "X-Remote-Email").strip(),
        trusted_subject_header=os.environ.get("REMOTE_WORKBENCH_TRUSTED_SUBJECT_HEADER", "X-Remote-Subject").strip(),
        bind_host=os.environ.get("REMOTE_WORKBENCH_BIND", "127.0.0.1"),
        bind_port=int(os.environ.get("REMOTE_WORKBENCH_BIND_PORT", "8765")),
        ice_servers=ice_servers,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve_parser = subparsers.add_parser("serve", help="run the loopback remote gateway")
    serve_parser.add_argument("--check-config", action="store_true", help="validate environment and exit")
    acl_parser = subparsers.add_parser("acl", help="manage the local default-deny board ACL")
    acl_subparsers = acl_parser.add_subparsers(dest="acl_command", required=True)
    for name in ("grant", "revoke"):
        command = acl_subparsers.add_parser(name)
        command.add_argument("email")
        if name == "grant":
            command.add_argument("role", choices=ROLES)

    args = parser.parse_args(argv)
    config = config_from_environment()
    if args.command == "serve":
        if args.check_config:
            print("remote gateway configuration is valid")
            return 0
        asyncio.run(RemoteGatewayService(config).serve_forever())
        return 0
    store = GatewayStore(config.state_path)
    try:
        if args.acl_command == "grant":
            store.grant(config.board, args.email, args.role)
            print("granted %s on %s to %s" % (args.role, config.board, args.email))
        else:
            store.revoke(config.board, args.email)
            print("revoked access on %s from %s" % (config.board, args.email))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
