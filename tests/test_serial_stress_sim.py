"""End-to-end serial stress test over a simulated link (CPython).

The real rotor app runs on the headless director with the real input
parser; the real base-side StressHost and the tool's stream parser sit at
the other end. Between them, a simulated 115200-baud wire with the rotor's
256-byte UART receive buffer (which drops what doesn't fit, like the ESP32
driver) and blocking uplink writes. Faults injected on the wire must come
out as a hardware verdict; overrunning the rotor must come out as rotor
software; a clean wire must come out clean.
"""

import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "micropython"))
sys.path.insert(0, os.path.join(ROOT, "emulator"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
sys.modules.setdefault("uos", os)
sys.modules.setdefault("urandom", random)


class FakeClock:
    """Stands in for utime: simulated milliseconds."""

    def __init__(self):
        self.ms = 0

    def ticks_ms(self):
        return int(self.ms)

    def ticks_us(self):
        return int(self.ms * 1000)

    @staticmethod
    def ticks_add(value, delta):
        return value + delta

    @staticmethod
    def ticks_diff(end, start):
        return end - start

    def sleep_ms(self, ms):
        self.ms += ms


CLOCK = FakeClock()
if "utime" not in sys.modules:
    sys.modules["utime"] = CLOCK

from ventilastation import api_guard  # noqa: E402
from ventilastation import serial_stress as rotor_sst  # noqa: E402
from ventilastation.app_loader import load_app  # noqa: E402
from ventilastation.director import configure_runtime, director, reset_runtime, stripes  # noqa: E402
from ventilastation.input_parser import InputParser  # noqa: E402

import serial_stress as tool  # noqa: E402
import serial_stress_host  # noqa: E402
from serial_stress_host import StressHost  # noqa: E402

LINE_RATE = 11520  # bytes/s at 115200 8N1
TICK_MS = 30
RX_BUFFER = 256
# What uart.write() can hand to the driver before blocking: its 256-byte TX
# ring plus the 128-byte hardware FIFO.
TX_ROOM = 384


class Wire:
    """One direction of the link: a FIFO drained at the line rate."""

    def __init__(self, fault=None):
        self.queue = bytearray()
        self.credit = 0.0
        self.fault = fault
        self.delivered = 0

    def put(self, data):
        self.queue += data

    def take(self, ms):
        if not self.queue:
            self.credit = 0.0
            return b""
        self.credit += LINE_RATE * ms / 1000
        count = min(int(self.credit), len(self.queue))
        self.credit -= count
        chunk = bytes(self.queue[:count])
        del self.queue[:count]
        if self.fault is not None:
            chunk = self.fault(self.delivered, chunk)
        self.delivered += count
        return chunk


def flip_bits(every, bit=0x08):
    def fault(position, chunk):
        data = bytearray(chunk)
        for index in range(len(data)):
            if (position + index) % every == every - 1:
                data[index] ^= bit
        return bytes(data)
    return fault


def drop_bytes(every):
    def fault(position, chunk):
        return bytes(byte for index, byte in enumerate(chunk)
                     if (position + index) % every != every - 1)
    return fault


class Link:
    def __init__(self, up_fault=None, down_fault=None):
        self.up = Wire(up_fault)
        self.down = Wire(down_fault)
        self.rotor_rx = bytearray()
        self.rotor_dropped = 0
        self.parser = tool.StreamParser()
        self.log = []
        self.host = StressHost(self.send_down, log=self.log.append, clock=lambda: CLOCK.ms / 1000)

    def send_down(self, text):
        self.down.put(text.encode("ascii") + b"\n")

    def advance(self, ms):
        """Everything but the rotor's main loop: wire, base reader, base pump
        (whose real thread runs every 5 ms), a millisecond at a time."""
        for _ in range(ms):
            CLOCK.ms += 1
            arrived = self.down.take(1)
            room = RX_BUFFER - len(self.rotor_rx)
            self.rotor_rx += arrived[:room]
            self.rotor_dropped += max(0, len(arrived) - room)
            for command, args, payload in self.parser.feed(self.up.take(1)):
                if not command or not self.host.handle(command, args, payload):
                    self.host.note_junk()
            self.host.pump()


class SimComms:
    """The rotor's serialcomms over the simulated link."""

    def __init__(self, link):
        self.link = link
        self.parser = InputParser()
        self.rx_hwm = 0

    def _drain(self):
        rx = self.link.rotor_rx
        if len(rx) > self.rx_hwm:
            self.rx_hwm = len(rx)
        chunk = bytes(rx[:64])
        del rx[:64]
        self.parser.feed(chunk)

    def receive(self, _bufsize):
        self._drain()
        return bytes([self.parser.joy1])

    def next_joy2(self):
        return self.parser.joy2

    def next_extra(self):
        return self.parser.extra

    def next_resync(self):
        # serialcomms drains here too: three 64-byte reads per tick in all.
        self._drain()
        return self.parser.pop_resync()

    def next_command(self):
        self._drain()
        return self.parser.pop_command()

    def send(self, line, data=b""):
        self.link.up.put(bytes(line) + b"\n" + bytes(data))
        while len(self.link.up.queue) > TX_ROOM:
            self.link.advance(1)  # uart.write() blocks while the wire drains

    def link_stats(self, reset=False):
        stats = {"rx_hwm": self.rx_hwm, "rx_buf": RX_BUFFER,
                 "nonascii": self.parser.dropped_nonascii,
                 "overlong": self.parser.dropped_overlong}
        if reset:
            self.rx_hwm = 0
        return stats


class SerialStressSimTests(unittest.TestCase):
    PHASE_MS = 2000

    def setUp(self):
        reset_runtime()
        api_guard.reset()
        CLOCK.ms = 0
        self.saved_phase_ms = rotor_sst.PHASE_MS
        rotor_sst.PHASE_MS = self.PHASE_MS
        self.runtime = configure_runtime("headless")
        stripes.clear()

        def fake_load_rom(_filename):
            stripes["tinyfont_menu.png"] = 0
            self.runtime.platform.sprites.stripes[0] = {
                "width": 4, "height": 6, "frames": 255, "palette": 0}

        self.runtime.load_rom = fake_load_rom

    def tearDown(self):
        rotor_sst.PHASE_MS = self.saved_phase_ms
        reset_runtime()
        api_guard.reset()

    def start(self, link):
        self.runtime.platform.comms = SimComms(link)
        scene = load_app("demos.serialstress")
        sys.modules[scene.__class__.__module__].utime = CLOCK
        return scene

    def run_until(self, link, done, limit_s=200):
        deadline = CLOCK.ms + limit_s * 1000
        while not done():
            self.assertLess(CLOCK.ms, deadline, "simulation did not finish:\n" + "\n".join(link.log))
            link.down.put(b"*\x00\x00\x00")  # the base's idle joystick frame
            link.advance(TICK_MS)
            director.step_once()

    def run_plan(self, link, phases=None, loop=False):
        scene = self.start(link)
        self.run_until(link, lambda: scene.tester.state == 1)  # READY
        if phases is None:
            scene.tester.start_plan()
        elif loop:
            scene.tester.start_loop(rotor_sst.phase_index(phases))
        else:
            scene.tester.start_queue([rotor_sst.phase_index(name) for name in phases])
        self.run_until(link, lambda: scene.tester.state == 6)  # DONE
        return scene

    def test_clean_link_passes_every_phase(self):
        link = Link()
        scene = self.run_plan(link)
        self.assertEqual(link.host.verdict, "clean", "\n".join(link.log))
        self.assertEqual(scene.tester.verdict, "clean")
        self.assertEqual(len(link.host.records), len(rotor_sst.PLAN))
        totals = scene.tester.totals
        self.assertGreater(totals["up_ok"], 100)
        self.assertGreater(totals["dn_ok"], 50)
        self.assertEqual((totals["up_err"], totals["dn_err"], totals["junk"]), (0, 0, 0))
        self.assertEqual(link.rotor_dropped, 0)
        for record in link.host.records:
            self.assertIsNotNone(record.rotor, record.name)
            self.assertEqual(record.up.bad + record.up_lost(), 0, record.name)
        upmax = next(r for r in link.host.records if r.name == "upmax")
        # Offered above capacity: the wire, not the offer, sets the pace.
        self.assertGreater(upmax.up_rate(), LINE_RATE * 0.8)
        self.assertLessEqual(upmax.up_rate(), LINE_RATE)
        self.assertGreater(upmax.rotor["tx_ms"], 0)
        self.assertEqual(scene.lines[1][0], "CLEAN, NO ERRORS")
        self.assertTrue(any("VERDICT CLEAN" in line for line in link.log))

    def test_bit_errors_on_the_uplink_are_hardware(self):
        link = Link(up_fault=flip_bits(4001))
        self.run_plan(link, ["up10", "up50"])
        self.assertEqual(link.host.verdict, "hardware", "\n".join(link.log))
        texts = [text for _category, _name, text in link.host.findings]
        self.assertTrue(any("bits changed in place" in text for text in texts), texts)

    def test_lost_downlink_bytes_with_room_to_spare_are_hardware(self):
        link = Link(down_fault=drop_bytes(1500))
        scene = self.run_plan(link, ["down10"])
        self.assertEqual(link.rotor_dropped, 0)
        self.assertEqual(link.host.verdict, "hardware", "\n".join(link.log))
        self.assertGreater(scene.tester.totals["dn_err"], 0)
        texts = [text for _category, _name, text in link.host.findings]
        self.assertTrue(any("never filled" in text for text in texts), texts)

    def test_bit7_flips_on_the_downlink_are_counted_not_fatal(self):
        link = Link(down_fault=flip_bits(997, bit=0x80))
        scene = self.run_plan(link, ["down20"])
        self.assertEqual(link.host.verdict, "hardware", "\n".join(link.log))
        self.assertGreater(scene.tester.totals["nonascii"], 0)

    def test_overrunning_the_rotor_is_rotor_software(self):
        # down60 is the positive control: more than the main loop drains.
        link = Link()
        self.run_plan(link, ["down60"])
        self.assertGreater(link.rotor_dropped, 0)
        self.assertEqual(link.host.verdict, "rotor_software", "\n".join(link.log))

    def test_soak_loop_stops_cleanly(self):
        link = Link()
        scene = self.start(link)
        self.run_until(link, lambda: scene.tester.state == 1)
        scene.tester.start_loop(rotor_sst.phase_index("up50"))
        self.run_until(link, lambda: scene.tester.run_count >= 3)
        scene.tester.on_command("serialtest_run stop")
        self.run_until(link, lambda: scene.tester.state == 6)
        self.assertEqual(link.host.verdict, "clean", "\n".join(link.log))
        self.assertEqual([r.name for r in link.host.records], ["up50"] * 3)

    def test_leaving_mid_phase_tells_the_base(self):
        link = Link()
        scene = self.start(link)
        self.run_until(link, lambda: scene.tester.state == 1)
        scene.tester.start_plan()
        self.run_until(link, lambda: scene.tester.phase == rotor_sst.phase_index("up10"))
        director.pop()
        self.run_until(link, lambda: link.host.run_closed)
        self.assertTrue(any("aborted" in line for line in link.log), link.log)

    def test_no_base_shows_it(self):
        link = Link()
        link.host.handle = lambda *args: False  # an old base: ignores the app
        scene = self.start(link)
        for _ in range(100):
            link.advance(TICK_MS)
            director.step_once()
        self.assertEqual(scene.tester.state, 0)
        self.assertEqual(scene.lines[1][0], "NO BASE ANSWER YET")


class StreamParserTests(unittest.TestCase):
    def frame(self, phase, seq, size=64):
        return (rotor_sst.up_header(size, phase, seq) + b"\n"
                + bytes(rotor_sst.up_payload(phase, seq, size)))

    def test_short_payload_ends_at_the_next_header(self):
        parser = tool.StreamParser()
        first = self.frame(1, 0)
        damaged = first[:40] + first[50:]  # ten payload bytes lost
        events = parser.feed(damaged + self.frame(1, 1) + b"music off\n")
        self.assertEqual([(e[0], e[1]) for e in events],
                         [("serialtest_up", ["64", "1", "0"]), ("serialtest_up", ["64", "1", "1"]),
                          ("music", ["off"])])
        self.assertEqual(len(events[0][2]), 54)
        self.assertEqual(events[1][2], bytes(rotor_sst.up_payload(1, 1, 64)))

    def test_garbage_before_a_header_is_junk(self):
        parser = tool.StreamParser()
        events = parser.feed(b"\x93\x00zz" + self.frame(2, 5) + b"\xff\xfe\n" + self.frame(2, 6))
        # The last payload is held back until it can't be a short one.
        events += parser.feed(b"", flush=True)
        commands = [e[0] for e in events]
        self.assertEqual(commands, ["", "serialtest_up", "", "serialtest_up"])
        self.assertEqual(parser.junk, 2)


class EmulatorReaderTests(unittest.TestCase):
    """The emulator's own reader (comms._receive_loop): readline(), split,
    then dispatch_command, which hands test lines to dispatch_line() and
    unknown ones to recover_line()."""

    def run_reader(self, stream, host):
        position = [0]

        def read(count):
            chunk = stream[position[0]:position[0] + count]
            position[0] += len(chunk)
            return chunk

        while position[0] < len(stream):
            end = stream.find(b"\n", position[0])
            end = len(stream) if end < 0 else end + 1
            line = stream[position[0]:end].strip()
            position[0] = end
            if not line:
                continue
            command, *args = line.split()
            if command.startswith(b"serialtest_"):
                serial_stress_host.dispatch_line(host, read, command, args)
            elif not serial_stress_host.recover_line(host, read, command, args):
                host.log("unknown %r" % command)

    def test_a_lost_byte_costs_the_damaged_frames_not_the_rest(self):
        log = []
        host = StressHost(lambda _line: None, log=log.append, clock=lambda: 0.0)
        frames = []
        for seq in range(40):
            frame = (rotor_sst.up_header(256, 2, seq) + b"\n"
                     + bytes(rotor_sst.up_payload(2, seq, 256)))
            if seq == 10:
                frame = frame[:100] + frame[101:]  # one byte lost on the wire
            frames.append(frame)
        stream = (b"serialtest_phase 2 name=up50 up_bps=5760 up_frame=256 ms=2000 baud=115200\n"
                  + b"".join(frames)
                  + b"serialtest_end 2 frames=40 bytes=10240\n")
        self.run_reader(stream, host)
        record = host.records[-1]
        # Frame 10 comes up a byte short (padded from frame 11's header), and
        # frame 11's header is lost with it; everything after realigns.
        self.assertEqual(record.up.kinds, {rotor_sst.DROPPED: 1})
        self.assertEqual(record.up.ok, 38)
        self.assertEqual(record.up_lost(), 1)
        self.assertGreaterEqual(record.up_junk, 1)
        self.assertFalse(any(line.startswith("unknown") for line in log), log)


if __name__ == "__main__":
    unittest.main()
