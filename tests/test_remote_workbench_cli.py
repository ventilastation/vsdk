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


if __name__ == "__main__":
    unittest.main()
