"""Serial Stress: measures the serial link between the base and the rotor.

The app drives a plan of load phases (ventilastation/serial_stress.py):
each phase streams verifiable frames up to the base at a set rate while the
base streams verifiable lines down, then both ends exchange their counters.
The base prints a per-phase report and a verdict -- hardware, rotor
software, base software -- and sends the verdict back for this screen.
See docs/internals/serial-stress-test.md.

A: run the plan.  B: repeat the selected phase (soak test, e.g. while the
rotor spins).  LEFT/RIGHT: select the phase.  Y/BACK: leave.  While a run is
going, hold A or B for a second to stop it after the current phase: a lossy
link can fake single presses (see joystick_changes below), never a hold.
"""

import gc
import utime

import vs2
from vs2.controls import A, B, LEFT, RIGHT, joy1

from ventilastation import serial_stress as sst
from ventilastation.director import director
from ventilastation.runtime import get_platform


HELLO_EVERY_MS = 2000
# After a phase, wait for the base's "downlink sent" marker. It queues behind
# every line still in flight, and the director hands over one line per tick,
# so keep waiting while lines keep coming; give up only after a silence (the
# marker itself may be lost), or at the cap. A fixed wait would report a
# backlog as lost lines.
SETTLE_QUIET_MS = 1500
SETTLE_MAX_MS = 20000
RESULT_MS = 2500
VERDICT_MS = 3000
# Catch-up bound: after a stall, don't burst more than this many frames in one
# tick (an over-capacity phase blocks in write() instead).
MAX_FRAMES_PER_TICK = 4
DEFAULT_BAUD = 115200
STOP_HOLD_MS = 1000

WAITING, READY, RUNNING, SETTLING, REPORTING, FINISHING, DONE = range(7)

VERDICT_LABELS = {
    "clean": "CLEAN, NO ERRORS",
    "hardware": "HARDWARE (WIRE)",
    "rotor_software": "ROTOR SOFTWARE",
    "base_software": "BASE SOFTWARE",
    "mixed": "HARDWARE+SOFTWARE",
    "inconclusive": "INCONCLUSIVE",
}


def _link_baud():
    platform = get_platform()
    if platform.name == "hardware":
        from ventilastation import board_config
        return board_config.get("serial_baud")
    return DEFAULT_BAUD


class RotorTester:
    """The rotor's end of the test, independent of the screen."""

    def __init__(self, comms, baud):
        self.comms = comms
        self.baud = baud
        self.state = WAITING
        self.last_hello = None
        self.queue = []
        self.loop_phase = None
        self.stop_requested = False
        self.run_count = 0
        self.phase = None
        self.down = None
        self.verdict = None
        self.totals = {"up_ok": 0, "up_err": 0, "dn_ok": 0, "dn_err": 0,
                       "junk": 0, "nonascii": 0, "rx_hwm": None, "rx_buf": None}
        self._link_stats = getattr(comms, "link_stats", None)

    # --- Commands from the base (via the scene's on_command) ---------------

    def on_command(self, line):
        if not line.startswith("serialtest_"):
            if self.state in (RUNNING, SETTLING):
                # Mid-run, an unknown line is a test line whose start got
                # corrupted. Count it instead of logging it upstream, which
                # would add traffic to the link being measured.
                self.down_junk += 1
                return True
            return False
        if line.startswith(sst.DOWN + " "):
            self._on_down(line)
            return True
        parts = line.split()
        command = parts[0]
        if command == sst.READY:
            if self.state == WAITING:
                self.state = READY
        elif command == sst.RUN and len(parts) >= 2:
            self._on_run(parts[1], "loop" in parts[2:])
        elif command == sst.SENT and len(parts) >= 2:
            if self._is_current(parts[1]):
                self.down_sent = sst.parse_fields(parts[2:]).get("frames")
        elif command == sst.RESULT and len(parts) >= 2:
            if self._is_current(parts[1]):
                self.host_result = sst.parse_fields(parts[2:])
        elif command == sst.VERDICT and len(parts) >= 2:
            self.verdict = parts[1]
        elif self.state in (RUNNING, SETTLING):
            self.down_junk += 1
        return True

    def _on_run(self, what, loop):
        if what == "stop":
            if self.state not in (WAITING, READY, DONE):
                self.request_stop()
            return
        # A remote start also proves a base is listening.
        if self.state not in (WAITING, READY, DONE):
            return
        if what == "plan":
            self.start_plan()
            return
        index = sst.phase_index(what)
        if index is None:
            return
        if loop:
            self.start_loop(index)
        else:
            self.start_queue([index])

    def _is_current(self, text):
        try:
            return self.phase is not None and int(text) == self.phase
        except ValueError:
            return False

    def _on_down(self, line):
        if self.down is None:
            return
        self.last_down = utime.ticks_ms()
        parts = line.split(" ", 3)
        try:
            phase = int(parts[1])
            seq = int(parts[2])
            payload = parts[3]
        except (IndexError, ValueError):
            self.down_junk += 1
            return
        expected = sst.down_payload(phase, seq, self.down_chars)
        self.down.check(phase, seq, expected, payload)

    # --- Starting and stopping ------------------------------------------------

    def start_plan(self):
        self.start_queue(list(sst.PLAN))

    def start_queue(self, phases):
        self._begin_run()
        self.queue = phases
        self._next_phase()

    def start_loop(self, index):
        self._begin_run()
        self.loop_phase = index
        self.queue = [index]
        self._next_phase()

    def request_stop(self):
        self.stop_requested = True

    def _begin_run(self):
        self.run_count = 0
        self.loop_phase = None
        self.stop_requested = False
        self.verdict = None
        for key in self.totals:
            self.totals[key] = 0
        self.totals["rx_hwm"] = None
        self.totals["rx_buf"] = None

    def abort(self):
        """Leaving mid-run: tell the base so it stops its downlink load."""
        if self.state in (RUNNING, SETTLING, REPORTING, FINISHING):
            self._send(sst.DONE + " aborted=1")
            self.state = DONE

    def _next_phase(self):
        if not self.queue and self.loop_phase is not None and not self.stop_requested:
            self.queue = [self.loop_phase]
        if not self.queue or self.stop_requested:
            self.queue = []
            self._send(sst.DONE)
            self.state = FINISHING
            self.state_since = utime.ticks_ms()
            return
        # Garbage collection is off on hardware; reclaim between phases, while
        # only joystick frames are on the wire.
        gc.collect()
        self._start_phase(self.queue.pop(0))

    def _start_phase(self, index):
        self.phase = index
        self.run_count += 1
        self.up_bps, self.up_frame, self.down_bps, self.down_chars = sst.phase_load(index, self.baud)
        self.down = sst.PhaseCounter(index)
        self.down_sent = None
        self.down_junk = 0
        self.host_result = None
        self.up_seq = 0
        self.up_bytes = 0
        self.tx_us = 0
        self.ticks = 0
        self.tick_max = 0
        self.last_tick = None
        self.joystick_changes = 0
        self.last_joystick = self._joystick()
        self.link_start = self._read_link_stats(reset=True)
        self._send("%s %d %s" % (sst.PHASE, index, sst.format_fields((
            ("name", sst.PHASES[index][0]),
            ("up_bps", self.up_bps), ("up_frame", self.up_frame),
            ("down_bps", self.down_bps), ("down_chars", self.down_chars),
            ("ms", sst.PHASE_MS), ("baud", self.baud),
        ))))
        self.t0 = utime.ticks_ms()
        self.state = RUNNING

    # --- Per tick --------------------------------------------------------------

    def tick(self):
        now = utime.ticks_ms()
        if self.state == WAITING:
            if self.last_hello is None or utime.ticks_diff(now, self.last_hello) >= HELLO_EVERY_MS:
                self._send("%s %d" % (sst.HELLO, sst.PROTOCOL_VERSION))
                self.last_hello = now
        elif self.state == RUNNING:
            self._count_tick(now)
            self._pump_uplink(now)
            if utime.ticks_diff(now, self.t0) >= sst.PHASE_MS:
                self.state = SETTLING
                self.state_since = now
                self.last_down = now
        elif self.state == SETTLING:
            if (self.down_sent is not None
                    or utime.ticks_diff(now, self.last_down) >= SETTLE_QUIET_MS
                    or utime.ticks_diff(now, self.state_since) >= SETTLE_MAX_MS):
                self._end_phase()
                self.state = REPORTING
                self.state_since = now
        elif self.state == REPORTING:
            if (self.host_result is not None
                    or utime.ticks_diff(now, self.state_since) >= RESULT_MS):
                self._add_host_result()
                self._next_phase()
        elif self.state == FINISHING:
            if self.verdict is not None or utime.ticks_diff(now, self.state_since) >= VERDICT_MS:
                self.state = DONE

    def _count_tick(self, now):
        self.ticks += 1
        if self.last_tick is not None:
            gap = utime.ticks_diff(now, self.last_tick)
            if gap > self.tick_max:
                self.tick_max = gap
        self.last_tick = now
        # The base sends the controllers' state 30 times a second. With
        # nobody touching them, every change is a corrupted joystick frame:
        # the phantom presses a player would see.
        joystick = self._joystick()
        if joystick != self.last_joystick:
            self.joystick_changes += 1
            self.last_joystick = joystick

    @staticmethod
    def _joystick():
        return (director.buttons, director.buttons2, director.extra_buttons)

    def _pump_uplink(self, now):
        if not self.up_bps:
            return
        target = self.up_bps * utime.ticks_diff(now, self.t0) // 1000
        frames = 0
        while self.up_bytes < target and frames < MAX_FRAMES_PER_TICK:
            seq = self.up_seq
            started = utime.ticks_us()
            self.comms.send(sst.up_header(self.up_frame, self.phase, seq),
                            sst.up_payload(self.phase, seq, self.up_frame))
            self.tx_us += utime.ticks_diff(utime.ticks_us(), started)
            self.up_seq += 1
            self.up_bytes += self.up_frame
            frames += 1

    def _end_phase(self):
        down = self.down
        lost = down.lost(self.down_sent)
        pairs = [
            ("frames", self.up_seq), ("bytes", self.up_bytes),
            ("dn_sent", -1 if self.down_sent is None else self.down_sent),
            ("dn_ok", down.ok), ("dn_bad", down.bad), ("dn_lost", lost),
            ("dn_dup", down.dup), ("dn_stale", down.stale),
            ("dn_junk", self.down_junk), ("dn_bits", down.bits),
        ]
        for kind in sst.KINDS:
            if down.kinds.get(kind):
                pairs.append(("dn_" + kind, down.kinds[kind]))
        link = self._read_link_stats()
        if link is not None:
            nonascii = link["nonascii"] - self.link_start["nonascii"]
            overlong = link["overlong"] - self.link_start["overlong"]
            pairs.append(("nonascii", nonascii))
            pairs.append(("overlong", overlong))
            self.totals["nonascii"] += nonascii
            if link["rx_hwm"] is not None:
                pairs.append(("rx_hwm", link["rx_hwm"]))
                self.totals["rx_hwm"] = max(self.totals["rx_hwm"] or 0, link["rx_hwm"])
            if link["rx_buf"] is not None:
                pairs.append(("rx_buf", link["rx_buf"]))
                self.totals["rx_buf"] = link["rx_buf"]
        pairs.append(("joy", self.joystick_changes))
        pairs.append(("ticks", self.ticks))
        pairs.append(("tick_max", self.tick_max))
        pairs.append(("tx_ms", self.tx_us // 1000))
        self._send("%s %d %s" % (sst.END, self.phase, sst.format_fields(pairs)))
        self.phase_down = (down.ok, down.bad, lost)
        self.totals["junk"] += self.down_junk
        # The base prints these: what exactly went wrong in the bad lines.
        for example in down.examples:
            print("serialtest: rotor DOWN phase %d %s" % (self.phase, sst.describe_example(example)))

    def _add_host_result(self):
        result = self.host_result or {}
        self.totals["up_ok"] += result.get("ok", 0)
        self.totals["up_err"] += result.get("bad", 0) + result.get("lost", 0)
        self.totals["junk"] += result.get("junk", 0)
        ok, bad, lost = self.phase_down
        # The base knows how many lines it sent even when its SENT marker
        # never made it here.
        self.totals["dn_ok"] += ok
        self.totals["dn_err"] += bad + result.get("dn_lost", lost)

    def _read_link_stats(self, reset=False):
        if self._link_stats is None:
            return None
        return self._link_stats(reset)

    def _send(self, line):
        self.comms.send(line.encode())


FONT = "tinyfont_menu.png"
FONT_WIDTH = 4
COLUMNS = 21
ROWS = 5
RED = 0x80


class SerialStress(vs2.Scene):
    asset_pack = "other"
    idle_timeout = None

    def __init__(self):
        vs2.Scene.__init__(self)
        self.tester = RotorTester(get_platform().comms, _link_baud())
        self.selected = sst.PLAN[0]
        self.hold_ms = 0
        self.last_update = None

    def build(self):
        self.hud = self.layer("serial-stress", projection=vs2.HUD)
        self.text = self.hud.label(FONT, columns=COLUMNS, rows=ROWS,
                                   x=-(COLUMNS * FONT_WIDTH // 2), y=0)
        self.lines = [None] * ROWS
        self.refresh()

    def teardown(self):
        self.tester.abort()

    def on_command(self, cmd_line):
        return self.tester.on_command(cmd_line)

    def update(self):
        tester = self.tester
        now = utime.ticks_ms()
        elapsed = 0 if self.last_update is None else utime.ticks_diff(now, self.last_update)
        self.last_update = now
        if tester.state in (READY, DONE):
            if joy1.just_pressed(LEFT):
                self.selected = (self.selected - 1) % len(sst.PHASES)
            if joy1.just_pressed(RIGHT):
                self.selected = (self.selected + 1) % len(sst.PHASES)
            if joy1.just_pressed(A):
                tester.start_plan()
            elif joy1.just_pressed(B):
                tester.start_loop(self.selected)
        elif tester.state != WAITING:
            if joy1.held(A) or joy1.held(B):
                self.hold_ms += elapsed
                if self.hold_ms >= STOP_HOLD_MS:
                    tester.request_stop()
            else:
                self.hold_ms = 0
        tester.tick()
        # Mid-run, a phantom Y or BACK must not walk out of the test.
        self.back_button = tester.state in (WAITING, READY, DONE)
        self.refresh()

    def set_line(self, row, value, red=False):
        value = value[:COLUMNS]
        key = (value, red)
        if key == self.lines[row]:
            return
        self.lines[row] = key
        self.text.write(0, row, value, frame_offset=RED if red else 0)

    def refresh(self):
        tester = self.tester
        totals = tester.totals
        state = tester.state
        self.set_line(0, "SERIAL STRESS %d" % tester.baud)
        selected = sst.PHASES[self.selected][0]
        if state == WAITING:
            self.set_line(1, "NO BASE ANSWER YET", red=True)
        elif state == READY:
            self.set_line(1, "A:PLAN B:LOOP <%s>" % selected)
        elif state == DONE:
            label = VERDICT_LABELS.get(tester.verdict, tester.verdict or "NO VERDICT")
            self.set_line(1, label, red=tester.verdict != "clean")
        else:
            name = sst.PHASES[tester.phase][0]
            if tester.stop_requested:
                where = "STOP"
            elif tester.loop_phase is not None:
                where = "#%d" % tester.run_count
            else:
                where = "%d/%d" % (tester.run_count, tester.run_count + len(tester.queue))
            left = 0
            if state == RUNNING:
                left = max(0, sst.PHASE_MS - utime.ticks_diff(utime.ticks_ms(), tester.t0)) // 1000 + 1
            self.set_line(1, "%s %s %s" % (where, name, ("%ds" % left) if left else "..."))
        self.set_line(2, "UP ok%d err%d" % (totals["up_ok"], totals["up_err"]), red=totals["up_err"] > 0)
        self.set_line(3, "DN ok%d err%d" % (totals["dn_ok"], totals["dn_err"]), red=totals["dn_err"] > 0)
        if totals["rx_buf"]:
            rx = "RX%d/%d" % (totals["rx_hwm"] or 0, totals["rx_buf"])
        else:
            rx = "RX -"
        bad = totals["junk"] + totals["nonascii"]
        self.set_line(4, "%s JK%d B7:%d" % (rx, totals["junk"], totals["nonascii"]), red=bad > 0)


def main():
    return SerialStress()
