#!/usr/bin/env python3
"""Compare the native host against the original C display and game behavior.

--trace emits a deterministic replay for the production WASM comparison.
"""
import ctypes
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'emulator'))
from build_ventilagon import build
from ventilagon_native import Ventilagon, FRAME_BYTES


def commands(engine):
    return [line.decode() for line in engine.commands()]


def frame(engine):
    return ctypes.string_at(engine.lib.ventilagon_host_frame(), FRAME_BYTES)


def trace(engine):
    engine.lib.ventilagon_host_enter(123)
    records = [{'commands': commands(engine)}]
    for n in range(200):
        buttons = 2 if (n // 20) % 2 else 1
        engine.lib.ventilagon_host_update(30000, buttons)
        lines = commands(engine)
        if n % 20 == 0 or lines or n == 199:
            records.append({'step': n, 'commands': lines,
                'idle': bool(engine.lib.ventilagon_host_is_idle()),
                'frame': hashlib.sha256(frame(engine)).hexdigest()})
    engine.lib.ventilagon_host_exit()
    records.append({'commands': commands(engine), 'idle': bool(engine.lib.ventilagon_host_is_idle())})
    return records


class NativeParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.engine = Ventilagon(build(output_dir=cls.temp.name, testing=True))
        cls.c = cls.engine.lib
        for name, args in [('play', [ctypes.c_int]), ('empty', []), ('state', [ctypes.c_int]),
                ('wall', [ctypes.c_int, ctypes.c_int]), ('set_drift', [ctypes.c_int]),
                ('reference_frame', [ctypes.c_void_p])]:
            fn = getattr(cls.c, 'ventilagon_test_' + name)
            fn.argtypes, fn.restype = args, None
        for name, args in [('position', []), ('section', []), ('drift', []), ('row', [ctypes.c_int])]:
            fn = getattr(cls.c, 'ventilagon_test_' + name)
            fn.argtypes, fn.restype = args, ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.c.ventilagon_host_enter(123)
        commands(self.engine)

    def update(self, elapsed, buttons=0):
        self.c.ventilagon_host_update(elapsed, buttons)
        return commands(self.engine)

    def play_empty(self, level=0):
        self.c.ventilagon_test_play(level)
        self.c.ventilagon_test_empty()
        commands(self.engine)

    def advance(self, total, cadence=30000, buttons=0):
        lines = []
        while total:
            dt = min(total, cadence)
            lines.extend(self.update(dt, buttons))
            total -= dt
        return lines

    def test_speed_is_independent_of_frame_rate_and_keeps_remainder(self):
        results = []
        for cadence in (100, 6944, 16667, 30000, 50000, 100000):
            self.c.ventilagon_host_enter(123)
            self.play_empty()
            self.advance(990000, cadence, 2)
            results.append(self.c.ventilagon_test_position())
        self.assertEqual(results, [4485] * len(results))

    def test_collision_cannot_be_skipped_by_a_slow_frame(self):
        self.play_empty()
        self.c.ventilagon_test_wall(3, 1)
        lines = self.advance(100000, buttons=2)
        self.assertEqual(self.c.ventilagon_test_position(), 360)
        self.assertTrue(self.c.ventilagon_host_is_idle())
        self.assertIn('sound ventilagon/audio/die', lines)
        self.assertIn('sound ventilagon/audio/es/perdiste', lines)

    def test_original_reset_and_restart_lifecycle(self):
        self.assertFalse(self.c.ventilagon_host_is_idle())
        lines = self.advance(1100000)
        self.assertIn('arduino start', lines)
        self.c.ventilagon_test_state(2)
        self.assertTrue(self.c.ventilagon_host_is_idle())
        self.update(1000, 0)  # release before restarting
        lines = self.update(1000, 16)
        self.assertFalse(self.c.ventilagon_host_is_idle())
        self.assertIn('arduino reset', lines)
        self.assertIn('arduino start', self.advance(1100000, buttons=0))
        self.c.ventilagon_host_exit()
        self.assertEqual(commands(self.engine), ['arduino stop'])
        self.assertFalse(self.c.ventilagon_host_is_idle())
        self.assertEqual(frame(self.engine), bytes(FRAME_BYTES))

    def test_full_frame_matches_original_spi_mapping(self):
        reference = (ctypes.c_uint8 * FRAME_BYTES)()
        for state in range(5):
            self.c.ventilagon_host_enter(123)
            self.c.ventilagon_test_state(state)
            # A known asymmetric board detects mirroring/sector mistakes.
            for row in range(48):
                self.c.ventilagon_test_wall(row, (row * 7) % 64)
            for drift in (0, 32, 1234, 8191):
                self.c.ventilagon_test_set_drift(drift)
                expected = frame(self.engine)
                self.c.ventilagon_test_reference_frame(reference)
                actual = bytes(reference)
                self.assertEqual(expected, actual, 'state=%d drift=%d' % (state, drift))
                self.assertEqual(expected[:18], bytes(18), 'six-LED hub gap')

    def test_sections_credits_and_win_use_original_audio_and_durations(self):
        self.play_empty()
        lines = self.advance(119251000)
        self.assertIn('sound ventilagon/audio/es/linea', lines)
        self.assertIn('sound ventilagon/audio/es/ventilagono', lines)
        self.assertIn('sound ventilagon/audio/es/buenisimo', lines)
        self.assertIn('servo stop', lines)
        self.assertEqual(self.c.ventilagon_test_section(), 6)
        # Credits are visible only on the upper half and outer sixteen LEDs.
        self.advance(5000000)
        pixels = frame(self.engine)
        self.assertTrue(any(pixels[64*54*3:192*54*3]))
        self.assertFalse(any(pixels[:64*54*3] + pixels[192*54*3:]))
        for col in range(256):
            self.assertFalse(any(pixels[col*54*3:(col*54+38)*3]))
        self.advance(15000000)  # credits transition into the colored win board
        self.assertTrue(any(frame(self.engine)))
        self.advance(45100000)
        self.assertTrue(self.c.ventilagon_host_is_idle())

    def test_seeded_reentry_resets_all_host_state(self):
        first = trace(self.engine)
        self.assertEqual(trace(self.engine), first)

    def test_suspending_a_tab_bounds_catchup(self):
        self.play_empty()
        self.update(10000000, 2)
        first = self.c.ventilagon_test_position()
        self.c.ventilagon_host_enter(123)
        self.play_empty()
        self.update(250000, 2)
        self.assertEqual(self.c.ventilagon_test_position(), first)


if __name__ == '__main__':
    if '--trace' in sys.argv:
        with tempfile.TemporaryDirectory() as output:
            print(json.dumps(trace(Ventilagon(build(output_dir=output)))))
    else:
        unittest.main()
