import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import remote_workbench as cli  # noqa: E402


class RemoteWorkbenchCliTests(unittest.TestCase):
    def test_absent_serial_device_keeps_auto_detection_enabled(self):
        with mock.patch.object(cli.glob, "glob", return_value=[]):
            self.assertEqual(cli.find_serial_port(), "auto")

    def test_environment_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_dir = Path(temporary) / "private config"
            config_dir.mkdir()
            path = config_dir / "gateway.env"
            path.write_text(
                cli.render_environment(config_dir, "/dev/test board", "192.0.2.4", cli.DEFAULT_ORIGIN),
                encoding="utf-8",
            )
            environment = cli.load_environment(path)
            self.assertEqual(environment["REMOTE_WORKBENCH_SERIAL_PORT"], "/dev/test board")
            self.assertEqual(environment["REMOTE_WORKBENCH_HOST"], "192.0.2.4")
            self.assertEqual(environment["REMOTE_WORKBENCH_AUTH_MODE"], "trusted-proxy")

    def test_emulator_url_carries_the_current_tunnel(self):
        url = cli.emulator_url("https://new-tunnel.example/")
        parsed = urlsplit(url)
        self.assertEqual(parsed.path, "/emulator/")
        self.assertEqual(parse_qs(parsed.query), {
            "remote": ["1"],
            "gateway": ["https://new-tunnel.example"],
        })

    def test_smoke_milestones(self):
        completed = set()
        newly_completed = cli.update_milestones(completed, (
            ("websocket_accept", ""),
            ("video_state", "connected"),
            ("lease_grant", ""),
            ("input", ""),
            ("host_event", "sound"),
        ))
        self.assertEqual(set(newly_completed), {name for name, _predicate in cli.MILESTONES})

    def test_policy_contains_only_validated_identity(self):
        email = cli.validate_email("Test.User@example.com")
        policy = cli.render_ngrok_policy(email, cli.validate_auth_id("vsdk-test_1"))
        self.assertIn("test.user@example.com", policy)
        self.assertIn("auth_id: vsdk-test_1", policy)
        with self.assertRaises(ValueError):
            cli.validate_auth_id("unsafe value")

    def test_auto_transport_prefers_configured_frp(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_dir = Path(temporary)
            (config_dir / "bin").mkdir()
            (config_dir / "frpc.toml").touch()
            (config_dir / "bin" / "frpc").touch()
            self.assertEqual(cli.select_transport(config_dir), "frp")

    def test_auto_transport_falls_back_to_ngrok(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(cli.select_transport(Path(temporary)), "ngrok")

    def test_ngrok_discovery_reports_missing_endpoint(self):
        with self.assertRaisesRegex(RuntimeError, "ngrok did not publish"):
            cli.discover_ngrok_url(timeout=0)

    def test_public_gateway_requires_an_https_origin(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_dir = Path(temporary)
            self.assertEqual(cli.public_gateway_url(config_dir), cli.DEFAULT_RELAY_GATEWAY)
            with self.assertRaises(ValueError):
                cli.public_gateway_url(config_dir, "http://relay.example")
            with self.assertRaises(ValueError):
                cli.public_gateway_url(config_dir, "https://relay.example/path")

    def test_frpc_config_uses_a_separate_token_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_dir = Path(temporary)
            rendered = cli.render_frpc_config(config_dir, "2001:db8::1", 7000, 18765)
            self.assertIn('serverAddr = "2001:db8::1"', rendered)
            self.assertIn("loginFailExit = false", rendered)
            self.assertIn('tokenSource.type = "file"', rendered)
            self.assertIn(str(config_dir / "frp.token"), rendered)
            self.assertNotIn("secret-token", rendered)

    def test_frp_endpoint_and_reachability_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "frpc.toml"
            config_path.write_text(
                cli.render_frpc_config(Path(temporary), "relay.example.test", 7000, 18765),
                encoding="utf-8",
            )
            self.assertEqual(
                cli.frp_endpoint(config_path),
                ("relay.example.test", 7000),
            )
            fake_connection = mock.MagicMock()
            with mock.patch.object(
                cli.socket,
                "create_connection",
                return_value=fake_connection,
            ) as create_connection:
                cli.check_tcp_endpoint("relay.example.test", 7000)
            create_connection.assert_called_once_with(
                ("relay.example.test", 7000), timeout=5.0
            )

    def test_frp_reachability_error_is_actionable(self):
        with mock.patch.object(
            cli.socket,
            "create_connection",
            side_effect=OSError("no route to host"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "FRP relay relay.example.test:7000 is unreachable: no route to host",
            ):
                cli.check_tcp_endpoint("relay.example.test", 7000)


if __name__ == "__main__":
    unittest.main()
