"""The Serial Stress app on the MicroPython unix runtime itself.

The end-to-end simulation (test_serial_stress_sim.py) runs on CPython; this
drives the same app through one short phase of each direction on the
interpreter the rotor actually runs, with a scripted base on the other end.

    micropython tests/test_serialstress_app_micropython.py
"""

import sys

sys.path.insert(0, "apps/micropython")

from ventilastation import api_guard
from ventilastation import serial_stress as sst
from ventilastation.app_loader import load_app
from ventilastation.director import configure_runtime, director, reset_runtime, stripes
from ventilastation.input_parser import InputParser

APP_MODULE = "games.demos.serialstress.code.serialstress"


class Clock:
    def __init__(self):
        self.ms = 0

    def ticks_ms(self):
        return self.ms

    def ticks_us(self):
        return self.ms * 1000

    def ticks_diff(self, end, start):
        return end - start

    def ticks_add(self, value, delta):
        return value + delta


class ScriptedBase:
    """Answers the app like serial_stress_host would, minus the checking."""

    def __init__(self):
        self.parser = InputParser()
        self.inbox = bytearray()
        self.lines = []
        self.phase_fields = None

    def receive(self, _bufsize):
        self.parser.feed(bytes(self.inbox))
        self.inbox = bytearray()
        return bytes([self.parser.joy1])

    def next_joy2(self):
        return 0

    def next_extra(self):
        return 0

    def next_command(self):
        return self.parser.pop_command()

    def link_stats(self, reset=False):
        return {"rx_hwm": 12, "rx_buf": 256, "nonascii": self.parser.dropped_nonascii,
                "overlong": self.parser.dropped_overlong}

    def to_rotor(self, line):
        self.inbox.extend(line.encode() + b"\n")

    def send(self, line, data=b""):
        line = bytes(line).decode()
        self.lines.append((line, bytes(data)))
        parts = line.split()
        command = parts[0]
        if command == sst.HELLO:
            self.to_rotor(sst.READY + " 1")
        elif command == sst.PHASE:
            self.phase = int(parts[1])
            self.phase_fields = sst.parse_fields(parts[2:])
            self.down_sent = 0
            chars = self.phase_fields["down_chars"]
            if chars:
                for seq in range(5):
                    self.to_rotor(sst.down_line(self.phase, seq, chars))
                # One corrupted line: a payload character changed in place.
                bad = sst.down_line(self.phase, 5, chars)
                self.to_rotor(bad[:-3] + ("A" if bad[-3] != "A" else "B") + bad[-2:])
                self.down_sent = 6
            self.to_rotor("%s %d frames=%d" % (sst.SENT, self.phase, self.down_sent))
        elif command == sst.END:
            self.end_fields = sst.parse_fields(parts[2:])
            self.to_rotor("%s %s ok=%d bad=0 lost=0 junk=0" % (
                sst.RESULT, parts[1], self.end_fields["frames"]))
        elif command == sst.DONE:
            self.to_rotor(sst.VERDICT + " clean")


def setup():
    reset_runtime()
    api_guard.reset()
    runtime = configure_runtime("headless")
    stripes.clear()

    def fake_load_rom(_filename):
        stripes["tinyfont_menu.png"] = 0
        runtime.platform.sprites.stripes[0] = {"width": 4, "height": 6, "frames": 255, "palette": 0}

    runtime.load_rom = fake_load_rom
    base = ScriptedBase()
    runtime.platform.comms = base
    return base


def run(scene, clock, until, limit=2000):
    for _ in range(limit):
        if until():
            return
        clock.ms += 30
        director.step_once()
    raise AssertionError("app did not get there; state %d" % scene.tester.state)


def test_one_phase_each_way():
    base = setup()
    saved = sst.PHASE_MS
    sst.PHASE_MS = 600
    try:
        scene = load_app("demos.serialstress")
        clock = Clock()
        sys.modules[APP_MODULE].utime = clock
        run(scene, clock, lambda: scene.tester.state == 1)
        assert scene.lines[1][0].startswith("A:PLAN B:LOOP"), scene.lines

        scene.on_command("serialtest_run up50")
        run(scene, clock, lambda: scene.tester.state == 6)
        ups = [(line, data) for line, data in base.lines if line.startswith(sst.UP + " ")]
        assert len(ups) == base.end_fields["frames"] > 0, base.end_fields
        for line, data in ups:
            _command, nbytes, phase, seq = line.split()
            assert data == bytes(sst.up_payload(int(phase), int(seq), int(nbytes)))
        assert scene.tester.verdict == "clean"
        assert scene.lines[1][0] == "CLEAN, NO ERRORS", scene.lines

        scene.on_command("serialtest_run down10")
        run(scene, clock, lambda: scene.tester.state == 6 and scene.tester.phase == sst.phase_index("down10"))
        fields = base.end_fields
        assert (fields["dn_ok"], fields["dn_bad"], fields["dn_lost"]) == (5, 1, 0), fields
        assert fields["dn_" + sst.BITFLIP] == 1, fields
        assert fields["rx_hwm"] == 12 and fields["rx_buf"] == 256, fields
    finally:
        sst.PHASE_MS = saved
        reset_runtime()
        api_guard.reset()


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("serial stress app (micropython): %d checks passed" % len(tests))


if __name__ == "__main__":
    main()
