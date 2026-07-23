"""Policy and wire-protocol tests for the remote workbench gateway."""

import os
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

from remote_gateway import (  # noqa: E402
    AuthenticationError,
    AuthorizationError,
    GatewayStore,
    HELLO,
    LeaseManager,
    Principal,
    ProtocolError,
    RemoteGatewayCore,
    TicketSigner,
    TrustedProxyIdentityVerifier,
    config_from_environment,
    decode_message,
    encode_message,
)


class RemoteGatewayTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = GatewayStore(os.path.join(self.tempdir.name, "state.sqlite3"))
        self.key = b"k" * 32
        self.core = RemoteGatewayCore("workbench-1", "remote-browser", self.key, self.store)
        self.store.grant("workbench-1", "owner@example.com", "admin", now=100)
        self.store.grant("workbench-1", "player@example.com", "controller", now=100)

    def tearDown(self):
        self.store.close()
        self.tempdir.cleanup()

    def test_binary_protocol_rejects_length_and_version_mismatches(self):
        encoded = encode_message(HELLO, 7, b"hello", timestamp_ms=123)
        message = decode_message(encoded)
        self.assertEqual((message.message_type, message.sequence, message.timestamp_ms, message.payload), (HELLO, 7, 123, b"hello"))
        with self.assertRaises(ProtocolError):
            decode_message(encoded[:-1])
        malformed = bytearray(encoded)
        malformed[4] = 99
        with self.assertRaises(ProtocolError):
            decode_message(bytes(malformed))

    def test_ticket_is_single_use_and_acl_is_rechecked_on_upgrade(self):
        ticket = self.core.ticket_for("google-subject", "player@example.com", now=100)
        principal = self.core.accept_ticket(ticket, now=101)
        self.assertEqual((principal.email, principal.role), ("player@example.com", "controller"))
        with self.assertRaises(AuthenticationError):
            self.core.accept_ticket(ticket, now=101)

        revoked_ticket = self.core.ticket_for("google-subject", "owner@example.com", now=102)
        self.store.revoke("workbench-1", "owner@example.com", now=103)
        with self.assertRaises(AuthorizationError):
            self.core.accept_ticket(revoked_ticket, now=104)

    def test_ticket_rejects_wrong_audience_and_expiry(self):
        signer = TicketSigner(self.key, "audience-a", "workbench-1")
        token = signer.issue(Principal("subject", "owner@example.com", "admin"), lifetime_s=10, now=100)
        with self.assertRaises(AuthenticationError):
            TicketSigner(self.key, "audience-b", "workbench-1").verify(token, now=101)
        with self.assertRaises(AuthenticationError):
            signer.verify(token, now=110)
        with self.assertRaises(ValueError):
            signer.issue(Principal("subject", "owner@example.com", "admin"), lifetime_s=61, now=100)

    def test_exclusive_lease_requires_current_generation_and_expires(self):
        manager = LeaseManager(duration_s=600, heartbeat_timeout_s=10)
        owner = Principal("owner", "owner@example.com", "admin")
        player = Principal("player", "player@example.com", "controller")
        lease = manager.request("workbench-1", player, "session-a", now=100.0)
        manager.validate("workbench-1", "session-a", lease.generation, now=101.0)
        with self.assertRaises(AuthorizationError):
            manager.request("workbench-1", owner, "session-b", now=101.0)
        with self.assertRaises(AuthorizationError):
            manager.validate("workbench-1", "session-a", lease.generation + 1, now=101.0)
        self.assertEqual(manager.expired(now=111.0), [lease])
        reassigned = manager.request("workbench-1", owner, "session-b", now=112.0)
        self.assertGreater(reassigned.generation, lease.generation)

    def test_viewer_cannot_acquire_control(self):
        manager = LeaseManager()
        with self.assertRaises(AuthorizationError):
            manager.request("workbench-1", Principal("viewer", "viewer@example.com", "viewer"), "session", now=0)

    def test_trusted_proxy_identity_requires_injected_headers(self):
        verifier = TrustedProxyIdentityVerifier("X-Remote-Email", "X-Remote-Subject")
        self.assertEqual(
            verifier.verify({"X-Remote-Email": "Player@Example.com", "X-Remote-Subject": "google-subject"}),
            ("google-subject", "player@example.com"),
        )
        self.assertEqual(
            verifier.verify({"X-Remote-Email": "Player@Example.com"}),
            ("player@example.com", "player@example.com"),
        )
        with self.assertRaises(AuthenticationError):
            verifier.verify({"X-Remote-Subject": "google-subject"})


class GatewayConfigurationTests(unittest.TestCase):
    def required_environment(self, directory):
        key_path = os.path.join(directory, "ticket.key")
        with open(key_path, "wb") as key_file:
            key_file.write(b"t" * 32)
        return {
            "REMOTE_WORKBENCH_BOARD": "workbench-1",
            "REMOTE_WORKBENCH_TICKET_AUDIENCE": "remote-browser",
            "REMOTE_WORKBENCH_TICKET_KEY_FILE": key_path,
            "REMOTE_WORKBENCH_STATE_DB": os.path.join(directory, "state.sqlite3"),
            "REMOTE_WORKBENCH_SERIAL_PORT": "/dev/test-board",
            "REMOTE_WORKBENCH_ALLOWED_ORIGINS": "https://emulator.example.test",
            "REMOTE_WORKBENCH_AUTH_MODE": "trusted-proxy",
        }

    def test_default_ice_configuration_uses_public_stun(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, self.required_environment(directory), clear=True):
                config = config_from_environment()
        self.assertEqual(config.ice_servers, ({
            "urls": ["stun:stun.l.google.com:19302"],
        },))

    def test_turn_configuration_preserves_credentials_for_authenticated_hello(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.required_environment(directory)
            environment["REMOTE_WORKBENCH_ICE_SERVERS_JSON"] = (
                '[{"urls":"turns:relay.example.test:5349",'
                '"username":"workbench","credential":"secret"}]'
            )
            with mock.patch.dict(os.environ, environment, clear=True):
                config = config_from_environment()
        self.assertEqual(config.ice_servers[0]["username"], "workbench")
        self.assertEqual(config.ice_servers[0]["credential"], "secret")


if __name__ == "__main__":
    unittest.main()
