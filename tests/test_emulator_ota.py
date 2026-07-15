import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "emulator"))

import config
from emu import parse_args
from ota_controls import OTA_SERVER_URL, ota_start_command


class EmulatorOtaTests(unittest.TestCase):
    def test_ota_command_uses_the_stable_mdns_hostname(self):
        self.assertEqual(OTA_SERVER_URL, "http://ventilastation-base.local:5653")
        self.assertEqual(ota_start_command(), "ota_start " + OTA_SERVER_URL)
        with open(os.path.join(ROOT, "emulator", "comms.py")) as source_file:
            self.assertIn("send_command(ota_start_command())", source_file.read())

    def test_no_ota_server_option_leaves_a_development_server_in_charge(self):
        self.assertTrue(parse_args([]).ota_server)
        args = parse_args(["--no-ota-server"])
        self.assertFalse(args.ota_server)
        config.configure(args)
        self.assertFalse(config.OTA_SERVER_ENABLED)
        with open(os.path.join(ROOT, "emulator", "comms.py")) as source_file:
            source = source_file.read()
        self.assertIn("if config.OTA_SERVER_ENABLED:", source)
        self.assertIn("upgrade_server.start(port=5653)", source)

    def test_both_pyglet_backends_use_the_shared_ota_shortcut(self):
        for backend in ("pyglet1x", "pyglet2x"):
            path = os.path.join(ROOT, "emulator", backend, "inputs.py")
            with open(path) as source_file:
                source = source_file.read()
            self.assertIn("ota_shortcut_pressed(symbol, modifiers)", source)
            self.assertIn("comms.trigger_ota()", source)


if __name__ == "__main__":
    unittest.main()
